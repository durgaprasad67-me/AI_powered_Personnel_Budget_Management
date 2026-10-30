from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analytics_service
from app.schemas.analytics import MonthlyAnalyticsSummary
from app.services.analytics import AnalyticsService

router = APIRouter(tags=["Analytics"])


@router.get("/analytics/summary", response_model=MonthlyAnalyticsSummary)
async def spending_summary(
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Month in YYYY-MM format",
    ),
    service: AnalyticsService = Depends(get_analytics_service),
):
    return await service.monthly_summary(month)
