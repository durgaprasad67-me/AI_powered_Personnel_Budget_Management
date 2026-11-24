from contextlib import asynccontextmanager
from math import ceil
from pathlib import Path

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    database = get_database()
    await database.command("ping")
    await ensure_indexes(database)
    yield
    await close_database()


app = FastAPI(
    title="FinSight AI API",
    description="Personal Finance and Spending Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)


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
async def home():
    return {
        "message": "Welcome to FinSight AI",
        "status": "running",
        "version": "1.0.0",
    }


app.include_router(health_router)
app.include_router(api_router)

# Mount frontend static directories (assets, css, js) - HTML directory is NEVER mounted publicly
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
STATIC_ASSETS_DIR = FRONTEND_DIR / "assets"
STATIC_CSS_DIR = FRONTEND_DIR / "css"
STATIC_JS_DIR = FRONTEND_DIR / "js"
HTML_DIR = FRONTEND_DIR / "html"

if STATIC_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_ASSETS_DIR), name="assets")
    app.mount("/frontend/assets", StaticFiles(directory=STATIC_ASSETS_DIR), name="frontend_assets")
if STATIC_CSS_DIR.exists():
    app.mount("/css", StaticFiles(directory=STATIC_CSS_DIR), name="css")
    app.mount("/frontend/css", StaticFiles(directory=STATIC_CSS_DIR), name="frontend_css")
if STATIC_JS_DIR.exists():
    app.mount("/js", StaticFiles(directory=STATIC_JS_DIR), name="js")
    app.mount("/frontend/js", StaticFiles(directory=STATIC_JS_DIR), name="frontend_js")


# Public Auth UI Page Routes
@app.get("/login", include_in_schema=False)
async def login_page():
    return FileResponse(HTML_DIR / "login.html")


@app.get("/register", include_in_schema=False)
async def register_page():
    return FileResponse(HTML_DIR / "register.html")


@app.get("/forgot-password", include_in_schema=False)
async def forgot_password_page():
    return FileResponse(HTML_DIR / "forgot-password.html")

