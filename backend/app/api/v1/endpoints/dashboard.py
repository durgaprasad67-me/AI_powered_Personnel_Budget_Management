import asyncio
from calendar import monthrange
from datetime import date as Date

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_analytics_service,
    get_budget_service,
    get_goal_service,
    get_transaction_service,
)
from app.schemas.analytics import DashboardResponse, MonthlyAnalyticsSummary
from app.services.budgets import BudgetService
from app.services.goals import GoalService
from app.services.analytics import AnalyticsService
from app.services.transactions import TransactionService

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


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Dashboard month in YYYY-MM format",
    ),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
    transaction_service: TransactionService = Depends(get_transaction_service),
    budget_service: BudgetService = Depends(get_budget_service),
    goal_service: GoalService = Depends(get_goal_service),
):
    year, month_number = (int(part) for part in month.split("-"))
    start_date = Date(year, month_number, 1)
    end_date = Date(year, month_number, monthrange(year, month_number)[1])

    summary, transactions, budgets, goals = await asyncio.gather(
        analytics_service.monthly_summary(month),
        transaction_service.list(
            transaction_type=None,
            category=None,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            limit=100,
            skip=0,
        ),
        budget_service.list(limit=100, skip=0),
        goal_service.list(status_filter=None, limit=100, skip=0),
    )

    return {
        **summary,
        "transactions": transactions["items"],
        "budgets": budgets["items"],
        "goals": goals["items"],
    }
