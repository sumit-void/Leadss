"""
LeadGen Pro — Email Worker
Celery task: extracts emails from crawled website pages.
"""

import logging

from app.workers.celery_app import celery_app
from app.models.database import get_sync_db
from app.models.business import Business
from app.models.website import Website
from app.models.email_model import Email
from app.scrapers.email_extractor import extract_emails_from_html

import httpx
from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.email_worker.extract_emails_task", bind=True, max_retries=2)
@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=20))
def extract_emails_task(self, business_id: str):
    """
    Extract emails from all crawled pages of a business.
    Uses multi-method extraction and stores with confidence scores.
    """
    db = get_sync_db()

    try:
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one_or_none()

        if not business:
            return {"error": "Business not found"}

        # Get all crawled pages
        websites = db.execute(
            select(Website).where(Website.business_id == business_id)
        ).scalars().all()

        if not websites:
            logger.info(f"[Email] No pages to extract from: {business.name}")
            return {"business_id": business_id, "emails_found": 0}

        total_emails = 0

        for page in websites:
            try:
                # Re-fetch page content for email extraction
                with httpx.Client(
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"},
                    follow_redirects=True,
                    timeout=15.0,
                ) as client:
                    response = client.get(page.url)
                    if response.status_code != 200:
                        continue

                    html = response.text

                # Extract emails
                extracted = extract_emails_from_html(html, page.url, page.page_type)

                for e in extracted:
                    # Check for duplicates
                    existing = db.execute(
                        select(Email).where(
                            Email.business_id == business_id,
                            Email.email == e.email,
                        )
                    ).scalar_one_or_none()

                    if existing:
                        # Update confidence if higher
                        if e.confidence > existing.confidence:
                            existing.confidence = e.confidence
                            existing.extraction_method = e.method
                        continue

                    email_record = Email(
                        business_id=business.id,
                        email=e.email,
                        source_url=e.source_url,
                        extraction_method=e.method,
                        confidence=e.confidence,
                        is_valid=True,
                        is_generic=e.is_generic,
                    )
                    db.add(email_record)
                    total_emails += 1
                    logger.info(f"  ✉ {e.email} (conf: {e.confidence}, method: {e.method})")

            except Exception as e:
                logger.debug(f"[Email] Page error {page.url}: {e}")
                continue

        db.commit()
        logger.info(f"[Email] Done: {business.name} — {total_emails} new emails")
        return {"business_id": business_id, "emails_found": total_emails}

    except Exception as e:
        db.rollback()
        logger.error(f"[Email] Error for {business_id}: {e}")
        raise
    finally:
        db.close()
