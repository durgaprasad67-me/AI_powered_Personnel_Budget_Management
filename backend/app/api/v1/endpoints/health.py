from fastapi import APIRouter

from app.db.client import get_database

router = APIRouter(tags=["Health"])


# Health endpoint
@router.get("/health")
async def health_check():
    await get_database().command("ping")
    return {"status": "healthy","database": "connected",}
