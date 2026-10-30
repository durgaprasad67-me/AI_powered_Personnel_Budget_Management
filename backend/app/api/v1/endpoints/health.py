from fastapi import APIRouter, Depends

from app.db.client import get_database
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Health"])


# Health endpoint
@router.get("/health", response_model=HealthResponse)
async def health_check(database=Depends(get_database)):
    await database.command("ping")
    return {"status": "healthy","database": "connected",}
