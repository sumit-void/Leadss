"""
LeadGen Pro — Celery Application Configuration
Central Celery app with task routing to separate queues.
"""

from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "leadgen",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Task routing
    task_routes={
        "app.workers.search_worker.*": {"queue": "search"},
        "app.workers.crawl_worker.*": {"queue": "crawl"},
        "app.workers.email_worker.*": {"queue": "email"},
        "app.workers.audit_worker.*": {"queue": "audit"},
    },

    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Results
    result_expires=3600,  # 1 hour

    # Rate limiting
    worker_max_tasks_per_child=100,
    worker_max_memory_per_child=512000,  # 512MB
)

# Auto-discover tasks
celery_app.autodiscover_tasks([
    "app.workers.search_worker",
    "app.workers.crawl_worker",
    "app.workers.email_worker",
    "app.workers.audit_worker",
])
