"""
LeadGen Pro — API Router
Combines all sub-routers into the main API.
"""

from fastapi import APIRouter
from app.api.leads import router as leads_router
from app.api.audits import router as audits_router
from app.api.campaigns import router as campaigns_router
from app.api.exports import router as exports_router

api_router = APIRouter()

api_router.include_router(leads_router)
api_router.include_router(audits_router)
api_router.include_router(campaigns_router)
api_router.include_router(exports_router)
