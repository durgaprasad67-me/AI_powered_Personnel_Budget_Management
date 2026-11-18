from fastapi import APIRouter

from app.api.v1.endpoints import (
    budgets,
    dashboard,
    goals,
    health,
    insights,
    rag,
    reports,
    transactions,
)
from app.api.v1.endpoints.imports import router as imports_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(transactions.router)
api_router.include_router(dashboard.router)
api_router.include_router(budgets.router)
api_router.include_router(goals.router)
api_router.include_router(insights.router)
api_router.include_router(imports_router)
api_router.include_router(rag.router)
api_router.include_router(reports.router)
