"""
LeadGen Pro — Audits API
Endpoints for viewing and triggering website audits.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.database import get_db
from app.models.audit import Audit
from app.models.business import Business

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/audits", tags=["Audits"])


class AuditSummary(BaseModel):
    id: str
    business_id: str
    business_name: str = ""
    overall_score: Optional[float] = None
    summary: Optional[str] = None
    outreach_opener: Optional[str] = None
    audit_method: Optional[str] = None
    issues_count: int = 0
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class AuditTrigger(BaseModel):
    business_id: str


@router.get("", response_model=list[AuditSummary])
async def list_audits(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all audits with optional score filtering."""
    query = select(Audit, Business.name).join(Business, Audit.business_id == Business.id)

    if min_score is not None:
        query = query.where(Audit.overall_score >= min_score)
    if max_score is not None:
        query = query.where(Audit.overall_score <= max_score)

    query = query.order_by(Audit.overall_score.desc()).offset(skip).limit(limit)
    result = await db.execute(query)

    audits = []
    for audit, biz_name in result:
        audits.append(AuditSummary(
            id=str(audit.id),
            business_id=str(audit.business_id),
            business_name=biz_name or "",
            overall_score=audit.overall_score,
            summary=audit.summary,
            outreach_opener=audit.outreach_opener,
            audit_method=audit.audit_method,
            issues_count=len(audit.issues) if audit.issues else 0,
            created_at=audit.created_at.isoformat() if audit.created_at else None,
        ))

    return audits


@router.get("/{audit_id}")
async def get_audit(audit_id: str, db: AsyncSession = Depends(get_db)):
    """Get full audit details."""
    result = await db.execute(select(Audit).where(Audit.id == audit_id))
    audit = result.scalar_one_or_none()

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return {
        "id": str(audit.id),
        "business_id": str(audit.business_id),
        "overall_score": audit.overall_score,
        "design_score": audit.design_score,
        "seo_score": audit.seo_score,
        "mobile_score": audit.mobile_score,
        "speed_score": audit.speed_score,
        "trust_score": audit.trust_score,
        "cta_score": audit.cta_score,
        "issues": audit.issues,
        "summary": audit.summary,
        "outreach_opener": audit.outreach_opener,
        "audit_method": audit.audit_method,
        "created_at": audit.created_at.isoformat() if audit.created_at else None,
    }


@router.post("/run")
async def trigger_audit(body: AuditTrigger, db: AsyncSession = Depends(get_db)):
    """Trigger a new audit for a business."""
    result = await db.execute(select(Business).where(Business.id == body.business_id))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    from app.workers.audit_worker import run_audit_task
    task = run_audit_task.delay(body.business_id)

    return {"message": "Audit enqueued", "task_id": task.id, "business_id": body.business_id}
