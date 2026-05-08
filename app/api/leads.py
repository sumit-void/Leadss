"""
LeadGen Pro — Leads API
CRUD endpoints for viewing, filtering, and managing leads.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.models.database import get_db
from app.models.business import Business, BusinessStatus
from app.models.email_model import Email
from app.models.audit import Audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leads", tags=["Leads"])


# ── Response Schemas ───────────────────────────────────

class LeadSummary(BaseModel):
    id: str
    name: str
    website_url: Optional[str] = None
    niche: Optional[str] = None
    location: Optional[str] = None
    status: str
    lead_score: Optional[float] = None
    email_count: int = 0
    best_email: Optional[str] = None
    batch_id: Optional[str] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class LeadDetail(BaseModel):
    id: str
    name: str
    website_url: Optional[str] = None
    snippet: Optional[str] = None
    title: Optional[str] = None
    source_query: Optional[str] = None
    niche: Optional[str] = None
    location: Optional[str] = None
    status: str
    lead_score: Optional[float] = None
    batch_id: Optional[str] = None
    emails: list = []
    audit: Optional[dict] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class StatsResponse(BaseModel):
    total_leads: int = 0
    with_email: int = 0
    with_audit: int = 0
    avg_score: float = 0.0
    by_status: dict = {}
    by_niche: dict = {}


class StatusUpdate(BaseModel):
    status: str


# ── Endpoints ──────────────────────────────────────────

@router.get("", response_model=list[LeadSummary])
async def list_leads(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    niche: Optional[str] = None,
    location: Optional[str] = None,
    min_score: Optional[float] = None,
    has_email: Optional[bool] = None,
    search: Optional[str] = None,
    batch_id: Optional[str] = None,
    sort_by: str = Query("created_at", enum=["created_at", "lead_score", "name"]),
    sort_order: str = Query("desc", enum=["asc", "desc"]),
    db: AsyncSession = Depends(get_db),
):
    """List leads with filtering, sorting, and pagination."""
    query = select(Business)

    # Filters
    conditions = []
    if status:
        conditions.append(Business.status == status)
    if niche:
        conditions.append(Business.niche.ilike(f"%{niche}%"))
    if location:
        conditions.append(Business.location.ilike(f"%{location}%"))
    if min_score is not None:
        conditions.append(Business.lead_score >= min_score)
    if batch_id:
        conditions.append(Business.batch_id == batch_id)
    if search:
        conditions.append(
            or_(
                Business.name.ilike(f"%{search}%"),
                Business.website_url.ilike(f"%{search}%"),
                Business.niche.ilike(f"%{search}%"),
            )
        )

    if conditions:
        query = query.where(and_(*conditions))

    # Sorting
    sort_col = getattr(Business, sort_by, Business.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    businesses = result.scalars().all()

    # Build response with email counts
    leads = []
    for b in businesses:
        email_result = await db.execute(
            select(Email).where(Email.business_id == b.id).order_by(Email.confidence.desc())
        )
        emails = email_result.scalars().all()

        # Filter has_email if needed
        if has_email is True and not emails:
            continue
        if has_email is False and emails:
            continue

        leads.append(LeadSummary(
            id=str(b.id),
            name=b.name,
            website_url=b.website_url,
            niche=b.niche,
            location=b.location,
            status=b.status.value if hasattr(b.status, 'value') else str(b.status),
            lead_score=b.lead_score,
            email_count=len(emails),
            best_email=emails[0].email if emails else None,
            batch_id=b.batch_id,
            created_at=b.created_at.isoformat() if b.created_at else None,
        ))

    return leads


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics."""
    # Total leads
    total = (await db.execute(select(func.count(Business.id)))).scalar() or 0

    # With email
    email_subq = select(Email.business_id).distinct()
    with_email = (await db.execute(
        select(func.count(Business.id)).where(Business.id.in_(email_subq))
    )).scalar() or 0

    # With audit
    audit_subq = select(Audit.business_id).distinct()
    with_audit = (await db.execute(
        select(func.count(Business.id)).where(Business.id.in_(audit_subq))
    )).scalar() or 0

    # Avg score
    avg_score = (await db.execute(
        select(func.avg(Business.lead_score)).where(Business.lead_score.isnot(None))
    )).scalar() or 0.0

    # By status
    status_result = await db.execute(
        select(Business.status, func.count(Business.id)).group_by(Business.status)
    )
    by_status = {str(row[0].value if hasattr(row[0], 'value') else row[0]): row[1] for row in status_result}

    # By niche
    niche_result = await db.execute(
        select(Business.niche, func.count(Business.id))
        .where(Business.niche.isnot(None))
        .group_by(Business.niche)
        .order_by(func.count(Business.id).desc())
        .limit(20)
    )
    by_niche = {row[0]: row[1] for row in niche_result}

    return StatsResponse(
        total_leads=total,
        with_email=with_email,
        with_audit=with_audit,
        avg_score=round(avg_score, 1),
        by_status=by_status,
        by_niche=by_niche,
    )


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: str, db: AsyncSession = Depends(get_db)):
    """Get full lead detail including emails and audit."""
    result = await db.execute(
        select(Business).where(Business.id == lead_id)
    )
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get emails
    email_result = await db.execute(
        select(Email).where(Email.business_id == lead_id).order_by(Email.confidence.desc())
    )
    emails = [
        {"email": e.email, "confidence": e.confidence, "method": e.extraction_method,
         "is_generic": e.is_generic, "source_url": e.source_url}
        for e in email_result.scalars().all()
    ]

    # Get latest audit
    audit_result = await db.execute(
        select(Audit).where(Audit.business_id == lead_id).order_by(Audit.created_at.desc()).limit(1)
    )
    audit_obj = audit_result.scalar_one_or_none()
    audit = None
    if audit_obj:
        audit = {
            "overall_score": audit_obj.overall_score,
            "design_score": audit_obj.design_score,
            "seo_score": audit_obj.seo_score,
            "mobile_score": audit_obj.mobile_score,
            "speed_score": audit_obj.speed_score,
            "trust_score": audit_obj.trust_score,
            "cta_score": audit_obj.cta_score,
            "issues": audit_obj.issues,
            "summary": audit_obj.summary,
            "outreach_opener": audit_obj.outreach_opener,
            "method": audit_obj.audit_method,
        }

    return LeadDetail(
        id=str(business.id),
        name=business.name,
        website_url=business.website_url,
        snippet=business.snippet,
        title=business.title,
        source_query=business.source_query,
        niche=business.niche,
        location=business.location,
        status=business.status.value if hasattr(business.status, 'value') else str(business.status),
        lead_score=business.lead_score,
        batch_id=business.batch_id,
        emails=emails,
        audit=audit,
        created_at=business.created_at.isoformat() if business.created_at else None,
    )


@router.patch("/{lead_id}")
async def update_lead_status(lead_id: str, update: StatusUpdate, db: AsyncSession = Depends(get_db)):
    """Update a lead's status."""
    result = await db.execute(select(Business).where(Business.id == lead_id))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        business.status = BusinessStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    await db.commit()
    return {"id": str(business.id), "status": business.status.value}
