from fastapi import APIRouter

from app.api.v1.endpoints import (
    budgets,
    dashboard,
    health,
    rag,
    transactions,
)
from app.api.v1.endpoints import (
    goals as financial_goals,
)
from app.api.v1.endpoints import (
    insights as ai_insights,
)
from app.api.v1.endpoints.imports import router as imports_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(transactions.router)
api_router.include_router(dashboard.router)
api_router.include_router(budgets.router)
api_router.include_router(financial_goals.router)
api_router.include_router(ai_insights.router)
api_router.include_router(imports_router)
api_router.include_router(rag.router)
