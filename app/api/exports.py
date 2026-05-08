"""
LeadGen Pro — Exports API
CSV/Excel export + search trigger endpoint.
"""

import io
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

import pandas as pd

from app.models.database import get_db
from app.models.business import Business
from app.models.email_model import Email
from app.models.audit import Audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Exports & Search"])


class SearchRequest(BaseModel):
    query: str
    max_pages: int = 3


@router.get("/exports/csv")
async def export_csv(
    status: Optional[str] = None,
    niche: Optional[str] = None,
    min_score: Optional[float] = None,
    has_email: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """Export leads as CSV with filters."""
    query = select(Business)

    conditions = []
    if status:
        conditions.append(Business.status == status)
    if niche:
        conditions.append(Business.niche.ilike(f"%{niche}%"))
    if min_score is not None:
        conditions.append(Business.lead_score >= min_score)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(Business.lead_score.desc().nullslast())
    result = await db.execute(query)
    businesses = result.scalars().all()

    rows = []
    for b in businesses:
        email_result = await db.execute(
            select(Email).where(Email.business_id == b.id).order_by(Email.confidence.desc())
        )
        emails = email_result.scalars().all()

        if has_email is True and not emails:
            continue

        # Get audit
        audit_result = await db.execute(
            select(Audit).where(Audit.business_id == b.id).order_by(Audit.created_at.desc()).limit(1)
        )
        audit = audit_result.scalar_one_or_none()

        rows.append({
            "Name": b.name,
            "Website": b.website_url or "",
            "Email": emails[0].email if emails else "",
            "All Emails": "; ".join(e.email for e in emails),
            "Niche": b.niche or "",
            "Location": b.location or "",
            "Lead Score": b.lead_score or 0,
            "Status": b.status.value if hasattr(b.status, 'value') else str(b.status),
            "Audit Summary": audit.summary if audit else "",
            "Outreach Opener": audit.outreach_opener if audit else "",
            "Source Query": b.source_query or "",
            "Batch": b.batch_id or "",
        })

    df = pd.DataFrame(rows)
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    filename = f"leads_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([csv_buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/exports/excel")
async def export_excel(
    status: Optional[str] = None,
    niche: Optional[str] = None,
    min_score: Optional[float] = None,
    has_email: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """Export leads as Excel with tabs."""
    query = select(Business)

    conditions = []
    if status:
        conditions.append(Business.status == status)
    if niche:
        conditions.append(Business.niche.ilike(f"%{niche}%"))
    if min_score is not None:
        conditions.append(Business.lead_score >= min_score)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(Business.lead_score.desc().nullslast())
    result = await db.execute(query)
    businesses = result.scalars().all()

    rows = []
    for b in businesses:
        email_result = await db.execute(
            select(Email).where(Email.business_id == b.id).order_by(Email.confidence.desc())
        )
        emails = email_result.scalars().all()

        if has_email is True and not emails:
            continue

        audit_result = await db.execute(
            select(Audit).where(Audit.business_id == b.id).order_by(Audit.created_at.desc()).limit(1)
        )
        audit = audit_result.scalar_one_or_none()

        rows.append({
            "Name": b.name,
            "Website": b.website_url or "",
            "Email": emails[0].email if emails else "",
            "Niche": b.niche or "",
            "Location": b.location or "",
            "Score": b.lead_score or 0,
            "Status": b.status.value if hasattr(b.status, 'value') else str(b.status),
            "Summary": audit.summary if audit else "",
            "Opener": audit.outreach_opener if audit else "",
        })

    df = pd.DataFrame(rows)

    # Write to Excel with tabs of 25
    output = io.BytesIO()
    tab_size = 25
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        total = len(df)
        num_tabs = max(1, (total + tab_size - 1) // tab_size)
        for i in range(num_tabs):
            start = i * tab_size
            end = min(start + tab_size, total)
            chunk = df.iloc[start:end].reset_index(drop=True)
            chunk.index += 1
            sheet_name = f"Leads {start+1}-{end}" if total > 0 else "No Leads"
            chunk.to_excel(writer, index=True, index_label="Sr", sheet_name=sheet_name)

    output.seek(0)
    filename = f"leads_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/search")
async def trigger_search(body: SearchRequest):
    """Trigger a new Google Search scraping task."""
    from app.workers.search_worker import search_and_discover

    batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    task = search_and_discover.delay(body.query, body.max_pages, batch_id)

    return {
        "message": "Search enqueued",
        "task_id": task.id,
        "query": body.query,
        "batch_id": batch_id,
    }
