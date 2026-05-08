"""
Audit model — website quality audit results.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.database import Base


class Audit(Base):
    __tablename__ = "audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)

    # Scores (0.0 - 10.0)
    overall_score = Column(Float, nullable=True)
    design_score = Column(Float, nullable=True)
    seo_score = Column(Float, nullable=True)
    mobile_score = Column(Float, nullable=True)
    speed_score = Column(Float, nullable=True)
    trust_score = Column(Float, nullable=True)
    cta_score = Column(Float, nullable=True)

    # Detailed findings
    issues = Column(JSONB, nullable=True)    # [{category, severity, description}, ...]
    summary = Column(Text, nullable=True)
    outreach_opener = Column(Text, nullable=True)

    # Metadata
    audit_method = Column(String(50), default="rule_based")  # rule_based, ollama, etc.
    ai_model = Column(String(100), nullable=True)
    raw_response = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationship
    business = relationship("Business", back_populates="audits")

    def __repr__(self):
        return f"<Audit(business_id='{self.business_id}', score={self.overall_score})>"
