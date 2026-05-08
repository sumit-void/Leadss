"""
Website model — stores crawled page data for each business.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.database import Base
import enum


class PageType(str, enum.Enum):
    HOMEPAGE = "homepage"
    CONTACT = "contact"
    ABOUT = "about"
    SERVICES = "services"
    OTHER = "other"


class Website(Base):
    __tablename__ = "websites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(2000), nullable=False)
    domain = Column(String(500), nullable=True, index=True)
    page_type = Column(
        SAEnum(PageType, name="page_type", create_constraint=True),
        default=PageType.HOMEPAGE,
    )
    title = Column(String(500), nullable=True)
    meta_description = Column(Text, nullable=True)
    headings = Column(JSONB, nullable=True)       # {"h1": [...], "h2": [...], ...}
    has_ssl = Column(Boolean, default=False)
    cms_detected = Column(String(100), nullable=True)  # wordpress, shopify, wix, etc.
    has_forms = Column(Boolean, default=False)
    social_links = Column(JSONB, nullable=True)    # {"facebook": url, "twitter": url, ...}
    phone_numbers = Column(JSONB, nullable=True)   # ["+1-...", ...]
    load_time_ms = Column(Integer, nullable=True)
    is_mobile_friendly = Column(Boolean, nullable=True)
    status_code = Column(Integer, nullable=True)
    raw_html_hash = Column(String(64), nullable=True)
    crawled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationship
    business = relationship("Business", back_populates="websites")

    def __repr__(self):
        return f"<Website(url='{self.url}', type='{self.page_type}')>"
