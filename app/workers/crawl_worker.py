"""
LeadGen Pro — Crawl Worker
Celery task: crawls discovered business websites and stores page data.
"""

import asyncio
import logging

from app.workers.celery_app import celery_app
from app.models.database import get_sync_db
from app.models.business import Business, BusinessStatus
from app.models.website import Website
from app.scrapers.website_crawler import crawl_website

from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.crawl_worker.crawl_website_task", bind=True, max_retries=2)
@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=4, max=30))
def crawl_website_task(self, business_id: str):
    """
    Crawl a business website: homepage + internal pages.
    Stores results and enqueues email extraction + audit.
    """
    db = get_sync_db()

    try:
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one_or_none()

        if not business:
            logger.warning(f"[Crawl] Business not found: {business_id}")
            return {"error": "Business not found"}

        if not business.website_url:
            logger.warning(f"[Crawl] No URL for: {business.name}")
            return {"error": "No URL"}

        # Update status
        business.status = BusinessStatus.CRAWLING
        db.commit()

        logger.info(f"[Crawl] Starting: {business.name} ({business.website_url})")

        # Run async crawl
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(
                crawl_website(business.website_url, concurrency=3)
            )
        finally:
            loop.close()

        # Store crawl results
        for r in results:
            website = Website(
                business_id=business.id,
                url=r.url,
                domain=business.website_url.split("//")[-1].split("/")[0].replace("www.", ""),
                page_type=r.page_type,
                title=r.title,
                meta_description=r.meta_description,
                headings=r.headings,
                has_ssl=r.has_ssl,
                cms_detected=r.cms_detected,
                has_forms=r.has_forms,
                social_links=r.social_links,
                phone_numbers=r.phone_numbers,
                load_time_ms=r.load_time_ms,
                is_mobile_friendly=r.is_mobile_friendly,
                status_code=r.status_code,
                raw_html_hash=r.raw_html_hash,
            )
            db.add(website)

        business.status = BusinessStatus.CRAWLED
        db.commit()

        # Enqueue email extraction
        from app.workers.email_worker import extract_emails_task
        extract_emails_task.delay(str(business.id))

        # Enqueue audit
        from app.workers.audit_worker import run_audit_task
        run_audit_task.delay(str(business.id))

        logger.info(f"[Crawl] Done: {business.name} — {len(results)} pages")
        return {"business_id": business_id, "pages_crawled": len(results)}

    except Exception as e:
        db.rollback()
        logger.error(f"[Crawl] Error for {business_id}: {e}")
        raise
    finally:
        db.close()
