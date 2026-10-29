from fastapi import APIRouter

from app.core.database import transactions_collection

router = APIRouter(tags=["Health"])


# Health endpoint
@router.get("/health")
async def health_check():
    await transactions_collection.database.command("ping")
    return {"status": "healthy","database": "connected",}

