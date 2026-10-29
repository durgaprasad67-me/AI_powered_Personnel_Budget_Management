from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analytics_service
from app.services.analytics import AnalyticsService, build_monthly_summary as build_summary


router = APIRouter(tags=["Analytics"])


@router.get("/analytics/summary")
async def spending_summary(
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Month in YYYY-MM format",
    ),
    service: AnalyticsService = Depends(get_analytics_service),
):
    return await service.monthly_summary(month)
