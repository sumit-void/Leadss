"""
Business model — represents a discovered business/lead.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Text, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.database import Base
import enum


class BusinessStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    CRAWLING = "crawling"
    CRAWLED = "crawled"
    AUDITING = "auditing"
    AUDITED = "audited"
    OUTREACH_READY = "outreach_ready"
    CONTACTED = "contacted"
    REPLIED = "replied"
    NOT_INTERESTED = "not_interested"


class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(500), nullable=False, index=True)
    website_url = Column(String(2000), unique=True, nullable=True, index=True)
    snippet = Column(Text, nullable=True)
    title = Column(String(500), nullable=True)
    source_query = Column(String(500), nullable=True, index=True)
    source_engine = Column(String(50), default="google_search")
    niche = Column(String(200), nullable=True, index=True)
    location = Column(String(200), nullable=True, index=True)
    status = Column(
        SAEnum(BusinessStatus, name="business_status", create_constraint=True),
        default=BusinessStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    lead_score = Column(Float, nullable=True, default=0.0, index=True)
    batch_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    websites = relationship("Website", back_populates="business", cascade="all, delete-orphan")
    emails = relationship("Email", back_populates="business", cascade="all, delete-orphan")
    audits = relationship("Audit", back_populates="business", cascade="all, delete-orphan")
    campaigns = relationship("OutreachCampaign", back_populates="business", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Business(name='{self.name}', url='{self.website_url}', score={self.lead_score})>"
