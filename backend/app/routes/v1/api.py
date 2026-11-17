from fastapi import APIRouter
from app.routes.v1 import (
    rag,
    ai_insights,
    budgets,
    dashboard,
    financial_goals,
    health,
<<<<<<< HEAD:backend/app/routes/v1/api.py
=======
    insights,
    rag,
    reports,
>>>>>>> 3d11468 (updated the some backend and frontend files):backend/app/api/v1/router.py
    transactions,
)
from app.routes.v1.imports.router import router as imports_router

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(transactions.router)
api_router.include_router(dashboard.router)
api_router.include_router(budgets.router)
api_router.include_router(financial_goals.router)
api_router.include_router(ai_insights.router)
api_router.include_router(imports_router)
api_router.include_router(rag.router)
api_router.include_router(reports.router)
