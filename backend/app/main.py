from contextlib import asynccontextmanager
<<<<<<< HEAD
from fastapi import FastAPI
from app.core.database import close_database, transactions_collection
from app.routes.v1.api import api_router
=======
from math import ceil

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.exceptions import (
    ExternalServiceError,
    InvalidInputError,
    NotFoundError,
)
from app.db.client import close_database, get_database
from app.db.indexes import ensure_indexes
from app.integrations.gemini_key_pool import AllKeysExhausted
from app.schemas.common import HomeResponse
>>>>>>> 3d11468 (updated the some backend and frontend files)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await transactions_collection.database.command("ping")
    await transactions_collection.create_index([("date", -1), ("_id", -1)])
    await transactions_collection.create_index([("category", 1), ("date", -1), ("_id", -1)])
    yield
    await close_database()


app = FastAPI(
    title="FinSight AI API",
    description="Personal Finance and Spending Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)

<<<<<<< HEAD

@app.get("/")
=======

@app.exception_handler(AllKeysExhausted)
async def gemini_keys_exhausted_handler(request, exc: AllKeysExhausted):
    retry_after = max(1, ceil(exc.retry_in))
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": str(retry_after)},
        content={
            "detail": "Gemini is temporarily unavailable. Please retry later.",
            "retry_after": retry_after,
        },
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
async def not_found_handler(request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    errors: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc", [])
        field = str(loc[-1]) if loc else "non_field_errors"
        msg = err.get("msg", "Invalid value")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        errors[field] = msg
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "errors": errors},
    )


@app.exception_handler(InvalidInputError)
async def invalid_input_handler(request, exc: InvalidInputError):
    if exc.status_code == 422:
        field = exc.field or "non_field_errors"
        return JSONResponse(
            status_code=422,
            content={
                "detail": exc.detail,
                "errors": {field: exc.detail},
            },
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(ExternalServiceError)
async def external_service_handler(request, exc: ExternalServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/", response_model=HomeResponse)
>>>>>>> 3d11468 (updated the some backend and frontend files)
async def home():
    return {
        "message": "Welcome to FinSight AI",
        "status": "running",
        "version": "1.0.0",
    }


app.include_router(api_router)
