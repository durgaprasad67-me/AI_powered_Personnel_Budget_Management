from fastapi import APIRouter
from app.routes.v1 import (ai_insights,budgets,dashboard,financial_goals,health,transactions,)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(transactions.router)
api_router.include_router(dashboard.router)
api_router.include_router(budgets.router)
api_router.include_router(financial_goals.router)
api_router.include_router(ai_insights.router)