"""
LeadGen Pro — FastAPI Application
Main entry point for the REST API server.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.models.database import create_tables
from app.config import get_settings

# ── Logging Setup ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting LeadGen Pro API...")

    # Import all models so they're registered with Base
    import app.models  # noqa: F401

    # Create database tables
    await create_tables()
    logger.info("Database initialized")

    yield

    logger.info("Shutting down LeadGen Pro API...")


# ── App Factory ────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title="LeadGen Pro",
    description=(
        "Lead Generation & Website Audit System. "
        "Discovers businesses via Google Search, crawls websites, "
        "extracts emails, runs quality audits, and prepares outreach campaigns."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


# ── Health Check ───────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "LeadGen Pro",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
