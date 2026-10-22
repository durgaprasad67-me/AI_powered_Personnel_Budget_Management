from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import close_database, transactions_collection
from app.routes.v1.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await transactions_collection.database.command("ping")
    yield
    await close_database()


app = FastAPI(
    title="FinSight AI API",
    description="Personal Finance and Spending Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def home():
    return {
        "message": "Welcome to FinSight AI",
        "status": "running",
        "version": "1.0.0",
    }


app.include_router(api_router)
