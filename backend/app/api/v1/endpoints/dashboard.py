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
from app.domain.transaction_types import CASH_OUT_TYPES
from app.repositories.budgets import budget_category_values, period_end
from app.schemas.analytics import DashboardResponse, MonthlyAnalyticsSummary
from app.services.analytics import AnalyticsService
from app.services.budgets import BudgetService
from app.services.goals import GoalService
from app.services.transactions import TransactionService

router = APIRouter(tags=["Analytics"])


def _budget_range(budget: dict) -> tuple[Date, Date]:
    start = Date.fromisoformat(str(budget["start_date"]))
    raw_end = budget.get("end_date")
    end = (
        Date.fromisoformat(str(raw_end))
        if raw_end
        else period_end(start)
    )
    return start, end


def _budget_covers(parent: dict, child: dict) -> bool:
    """Return whether a broader allocation already includes this budget."""
    parent_start, parent_end = _budget_range(parent)
    child_start, child_end = _budget_range(child)
    if parent_start > child_start or parent_end < child_end:
        return False

    parent_type = parent.get("transaction_type", "expense")
    child_type = child.get("transaction_type", "expense")
    if parent_type != "all" and parent_type != child_type:
        return False

    parent_categories = budget_category_values(parent.get("category"))
    child_categories = budget_category_values(child.get("category"))
    if parent_categories and (
        not child_categories or not set(child_categories).issubset(parent_categories)
    ):
        return False

    return (
        parent_start != child_start
        or parent_end != child_end
        or parent_type != child_type
        or (parent_categories or []) != (child_categories or [])
    )


def _transaction_matches_budget(transaction: dict, budget: dict) -> bool:
    tx_type = transaction.get("transaction_type")
    # Cash inflows never follow or count towards budget rules
    if tx_type not in CASH_OUT_TYPES:
        return False
    budget_type = budget.get("transaction_type", "expense")
    if budget_type != "all" and tx_type != budget_type:
        return False
    categories = budget_category_values(budget.get("category"))
    tx_cat = (transaction.get("category") or "").strip().lower()
    return not categories or tx_cat in categories


def _active_budget_roots(
    budgets: list[dict], start_date: Date, end_date: Date
) -> list[dict]:
    active = []
    for budget in budgets:
        budget_start, budget_end = _budget_range(budget)
        if budget_start <= end_date and budget_end >= start_date:
            active.append(budget)
    return [
        budget
        for budget in active
        if not any(
            other is not budget and _budget_covers(other, budget)
            for other in active
        )
    ]


async def _list_all_transactions(
    service: TransactionService,
    *,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Load every transaction in a month, not only the first API page."""
    limit = 100
    items: list[dict] = []
    skip = 0

    while True:
        page = await service.list(
            transaction_type=None,
            category=None,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            skip=skip,
        )
        page_items = page["items"]
        items.extend(page_items)

        if not page_items or len(items) >= page["total"]:
            return items
        skip += len(page_items)


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
        _list_all_transactions(
            transaction_service,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        ),
        budget_service.list(limit=100, skip=0),
        goal_service.list(status_filter=None, limit=100, skip=0),
    )

    # A category budget under an All budget is a sub-allocation, not a second
    # independent allocation. Count only the broadest active budgets.
    top_level_budgets = _active_budget_roots(
        budgets["items"], start_date, end_date
    )
    allocated_budget = 0.0
    available_allocated_budget = 0.0
    for budget in top_level_budgets:
        budget_start, budget_end = _budget_range(budget)
        usage_start = max(budget_start, start_date)
        usage_end = min(budget_end, end_date)
        spent = sum(
            float(transaction["amount"])
            for transaction in transactions
            if usage_start.isoformat() <= str(transaction["date"]) <= usage_end.isoformat()
            and _transaction_matches_budget(transaction, budget)
        )
        limit = float(budget["amount"])
        allocated_budget += limit
        available_allocated_budget += max(0.0, limit - spent)

    return {
        **summary,
        "transactions": transactions,
        "budgets": budgets["items"],
        "allocated_budget": round(allocated_budget, 2),
        "available_allocated_budget": round(available_allocated_budget, 2),
        "goals": goals["items"],
    }
