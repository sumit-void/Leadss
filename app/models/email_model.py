"""
Email model — extracted email addresses with source tracking.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.database import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(500), nullable=False, index=True)
    source_url = Column(String(2000), nullable=True)
    extraction_method = Column(String(50), nullable=True)  # regex, mailto, schema, html_parse, js_render
    confidence = Column(Float, default=0.5)                 # 0.0 to 1.0
    is_valid = Column(Boolean, default=True)
    is_generic = Column(Boolean, default=False)             # info@, contact@, hello@, etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationship
    business = relationship("Business", back_populates="emails")

    # Unique constraint: one email per business
    __table_args__ = (
        UniqueConstraint("business_id", "email", name="uq_business_email"),
    )

    def __repr__(self):
        return f"<Email(email='{self.email}', confidence={self.confidence})>"
