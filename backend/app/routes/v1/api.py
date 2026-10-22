from fastapi import APIRouter

from app.routes.v1 import dashboard, health, transactions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(transactions.router)
api_router.include_router(dashboard.router)
