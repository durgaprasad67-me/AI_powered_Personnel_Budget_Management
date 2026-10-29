from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db.client import close_database, get_database
from app.db.indexes import ensure_indexes
from app.routes.v1.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_database().command("ping")
    await ensure_indexes()
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
