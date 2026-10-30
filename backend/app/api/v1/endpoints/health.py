from fastapi import APIRouter

from app.db.client import get_database
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Health"])


# Health endpoint
@router.get("/health", response_model=HealthResponse)
async def health_check():
    await get_database().command("ping")
    return {"status": "healthy","database": "connected",}
