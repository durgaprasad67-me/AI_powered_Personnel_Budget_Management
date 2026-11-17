from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id, get_insight_service
from app.schemas.insights import (
    ChatRequest,
    ChatResponse,
    SpendingInsightRequest,
    SpendingInsightResponse,
    TransactionExtractionResponse,
    TransactionTextRequest,
)
from app.services.insights import InsightService

router = APIRouter(
    prefix="/ai",
    tags=["AI Financial Insights"],
)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: InsightService = Depends(get_insight_service),
    user_id: str = Depends(get_current_user_id),
) -> ChatResponse:
    return await service.chat(request, user_id=user_id)


@router.post("/spending-insights", response_model=SpendingInsightResponse)
async def generate_spending_insights(
    request: SpendingInsightRequest,
    service: InsightService = Depends(get_insight_service),
    user_id: str = Depends(get_current_user_id),
) -> SpendingInsightResponse:
    return await service.spending_insights(request, user_id=user_id)


@router.post("/extract-transaction", response_model=TransactionExtractionResponse)
async def extract_transaction(
    request: TransactionTextRequest,
    service: InsightService = Depends(get_insight_service),
) -> TransactionExtractionResponse:
    return await service.extract_transaction(request)
