from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.exceptions import InvalidInputError, NotFoundError
from app.db.client import close_database, get_database
from app.db.indexes import ensure_indexes


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


@app.exception_handler(NotFoundError)
async def not_found_handler(request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidInputError)
async def invalid_input_handler(request, exc: InvalidInputError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
async def home():
    return {
        "message": "Welcome to FinSight AI",
        "status": "running",
        "version": "1.0.0",
    }


app.include_router(health_router)
app.include_router(api_router)
