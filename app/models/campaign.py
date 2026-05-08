"""
OutreachCampaign model — tracks email outreach to leads.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.database import Base
import enum


class CampaignStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    OPENED = "opened"
    REPLIED = "replied"
    BOUNCED = "bounced"
    OPTED_OUT = "opted_out"


class OutreachCampaign(Base):
    __tablename__ = "outreach_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    email_used = Column(String(500), nullable=True)
    status = Column(
        SAEnum(CampaignStatus, name="campaign_status", create_constraint=True),
        default=CampaignStatus.PENDING,
        index=True,
    )
    subject = Column(String(500), nullable=True)
    body = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    replied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationship
    business = relationship("Business", back_populates="campaigns")

    def __repr__(self):
        return f"<OutreachCampaign(business='{self.business_id}', status='{self.status}')>"
