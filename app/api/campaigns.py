"""
LeadGen Pro — Campaigns API
Endpoints for managing outreach campaigns.
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.database import get_db
from app.models.campaign import OutreachCampaign, CampaignStatus
from app.models.business import Business

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])


class CampaignCreate(BaseModel):
    business_id: str
    email_used: str
    subject: Optional[str] = None
    body: Optional[str] = None


class CampaignStatusUpdate(BaseModel):
    status: str


@router.get("")
async def list_campaigns(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all outreach campaigns."""
    query = select(OutreachCampaign, Business.name).join(
        Business, OutreachCampaign.business_id == Business.id
    )

    if status:
        query = query.where(OutreachCampaign.status == status)

    query = query.order_by(OutreachCampaign.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)

    campaigns = []
    for campaign, biz_name in result:
        campaigns.append({
            "id": str(campaign.id),
            "business_id": str(campaign.business_id),
            "business_name": biz_name,
            "email_used": campaign.email_used,
            "status": campaign.status.value if hasattr(campaign.status, 'value') else str(campaign.status),
            "subject": campaign.subject,
            "sent_at": campaign.sent_at.isoformat() if campaign.sent_at else None,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        })

    return campaigns


@router.post("")
async def create_campaign(body: CampaignCreate, db: AsyncSession = Depends(get_db)):
    """Create a new outreach campaign."""
    result = await db.execute(select(Business).where(Business.id == body.business_id))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    campaign = OutreachCampaign(
        business_id=business.id,
        email_used=body.email_used,
        subject=body.subject,
        body=body.body,
        status=CampaignStatus.PENDING,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return {"id": str(campaign.id), "status": "pending", "message": "Campaign created"}


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    update: CampaignStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update campaign status."""
    result = await db.execute(select(OutreachCampaign).where(OutreachCampaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    try:
        campaign.status = CampaignStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    # Set timestamps based on status
    now = datetime.now(timezone.utc)
    if update.status == "sent":
        campaign.sent_at = now
    elif update.status == "opened":
        campaign.opened_at = now
    elif update.status == "replied":
        campaign.replied_at = now

    await db.commit()
    return {"id": str(campaign.id), "status": campaign.status.value}
