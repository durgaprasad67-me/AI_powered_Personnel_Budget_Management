from fastapi import APIRouter
from app.api.v1.endpoints import (
    rag,
    insights as ai_insights,
    budgets,
    dashboard,
    goals as financial_goals,
    health,
    transactions,
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
