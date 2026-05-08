"""
LeadGen Pro — Search Worker
Celery task: scrapes Google Search and stores discovered businesses.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.models.database import get_sync_db, Base, get_sync_engine
from app.models.business import Business, BusinessStatus
from app.scrapers.google_search import search_google, extract_niche_location
from app.config import get_settings

from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.search_worker.search_and_discover", bind=True, max_retries=3)
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=60))
def search_and_discover(self, query: str, max_pages: int = 3, batch_id: str = None):
    """
    Search Google for a query, extract results, store businesses.
    Automatically enqueues crawl tasks for new discoveries.
    """
    settings = get_settings()
    if not batch_id:
        batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    logger.info(f"[Search] Starting: '{query}' (batch: {batch_id})")

    # Ensure tables exist
    Base.metadata.create_all(get_sync_engine())

    # Run async search in sync context
    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(
            search_google(
                query=query,
                max_pages=max_pages,
                delay_min=settings.request_delay_min,
                delay_max=settings.request_delay_max,
                headless=True,
            )
        )
    finally:
        loop.close()

    if not results:
        logger.warning(f"[Search] No results for: '{query}'")
        return {"query": query, "found": 0, "new": 0, "batch_id": batch_id}

    niche, location = extract_niche_location(query)
    db = get_sync_db()
    new_count = 0

    try:
        for r in results:
            # Check if URL already exists
            existing = db.execute(
                select(Business).where(Business.website_url == r.url)
            ).scalar_one_or_none()

            if existing:
                logger.debug(f"  Skip (dup): {r.url}")
                continue

            business = Business(
                name=r.name,
                website_url=r.url,
                snippet=r.snippet,
                title=r.title,
                source_query=query,
                source_engine="google_search",
                niche=niche,
                location=location,
                status=BusinessStatus.DISCOVERED,
                batch_id=batch_id,
            )
            db.add(business)
            db.flush()

            # Enqueue crawl task
            from app.workers.crawl_worker import crawl_website_task
            crawl_website_task.delay(str(business.id))

            new_count += 1
            logger.info(f"  ✓ New: {r.name} ({r.url})")

        db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"[Search] DB error: {e}")
        raise
    finally:
        db.close()

    result = {"query": query, "found": len(results), "new": new_count, "batch_id": batch_id}
    logger.info(f"[Search] Done: {result}")
    return result
