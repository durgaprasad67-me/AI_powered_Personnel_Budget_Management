from datetime import date as Date
from datetime import timedelta
from typing import Any

from app.core.exceptions import InvalidInputError
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.domain.transaction_types import (
    CASH_IN_TYPES,
    CASH_OUT_TYPES,
    TRANSACTION_TYPES,
)
from app.repositories.analytics import AnalyticsRepository
from app.schemas.insights import CategorySpending, SpendingSummary


def build_monthly_summary(month: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    categories_by_type: dict[str, dict[str, float]] = {
        kind: {} for kind in TRANSACTION_TYPES
    }
    spending_by_category: dict[str, float] = {}
    outflow_by_category: dict[str, float] = {}
    inflow_by_category: dict[str, float] = {}

    for row in rows:
        kind = row["_id"]["type"]
        category = row["_id"].get("category") or "uncategorized"
        total = float(row.get("total") or 0.0)
        count = int(row.get("count") or 1)

        totals[kind] = totals.get(kind, 0.0) + total
        counts[kind] = counts.get(kind, 0) + count

        if kind in categories_by_type:
            categories_by_type[kind][category] = (
                categories_by_type[kind].get(category, 0.0) + total
            )

        if kind == "expense":
            spending_by_category[category] = (
                spending_by_category.get(category, 0.0) + total
            )

        if kind in CASH_OUT_TYPES:
            outflow_by_category[category] = (
                outflow_by_category.get(category, 0.0) + total
            )
        elif kind in CASH_IN_TYPES:
            inflow_by_category[category] = (
                inflow_by_category.get(category, 0.0) + total
            )

    def amount(kind: str) -> float:
        return round(totals.get(kind, 0.0), 2)

    income = totals.get("income", 0.0)
    expenses = totals.get("expense", 0.0)
    cash_in = sum(totals.get(kind, 0.0) for kind in CASH_IN_TYPES)
    cash_out = sum(totals.get(kind, 0.0) for kind in CASH_OUT_TYPES)

    type_breakdown = {kind: amount(kind) for kind in TRANSACTION_TYPES}
    type_details = [
        {
            "type": kind,
            "stream": "inflow" if kind in CASH_IN_TYPES else "outflow",
            "total": amount(kind),
            "count": counts.get(kind, 0),
            "categories": {
                cat: round(val, 2)
                for cat, val in sorted(
                    categories_by_type.get(kind, {}).items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            },
        }
        for kind in TRANSACTION_TYPES
    ]

    return {
        "month": month,
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "balance": round(income - expenses, 2),
        "total_cash_inflow": round(cash_in, 2),
        "total_cash_outflow": round(cash_out, 2),
        "net_cash_flow": round(cash_in - cash_out, 2),
        "investments": {
            "invested": amount("investment"),
            "returned": amount("investment_return"),
            "net_invested": round(
                totals.get("investment", 0.0) - totals.get("investment_return", 0.0),
                2,
            ),
        },
        "loans": {
            "borrowed": amount("loan_taken"),
            "repaid": amount("loan_repaid"),
            "lent": amount("loan_given"),
            "collected": amount("loan_collected"),
        },
        "type_breakdown": type_breakdown,
        "type_details": type_details,
        "category_breakdown": {
            category: round(total, 2)
            for category, total in sorted(
                spending_by_category.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        },
        "outflow_categories": {
            category: round(total, 2)
            for category, total in sorted(
                outflow_by_category.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        },
        "inflow_categories": {
            category: round(total, 2)
            for category, total in sorted(
                inflow_by_category.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        },
    }


class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository):
        self.repository = repository

    async def monthly_summary(
        self,
        month: str,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any]:
        year, month_number = int(month[:4]), int(month[5:])
        next_year, next_month = (
            (year + 1, 1) if month_number == 12 else (year, month_number + 1)
        )
        rows = await self.repository.grouped_rows(
            start_date=Date(year, month_number, 1),
            end_date=Date(next_year, next_month, 1) - timedelta(days=1),
            user_id=user_id,
        )
        return build_monthly_summary(month, rows)

    async def spending_summary(
        self,
        start_date: Date,
        end_date: Date,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> SpendingSummary:
        if start_date > end_date:
            raise InvalidInputError("start_date must not be after end_date.")

        rows = await self.repository.grouped_rows(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
        )
        totals = dict.fromkeys(TRANSACTION_TYPES, 0.0)
        categories: dict[str, dict[str, float | int]] = {}

        for row in rows:
            group = row["_id"]
            transaction_type = group.get("type")
            category = group.get("category") or "uncategorized"
            amount = float(row.get("total") or 0)
            count = int(row.get("count") or 0)

            if transaction_type in totals:
                totals[transaction_type] += amount
            if transaction_type == "expense":
                entry = categories.setdefault(
                    category,
                    {"amount": 0.0, "count": 0},
                )
                entry["amount"] += amount
                entry["count"] += count

        category_breakdown = [
            CategorySpending(
                category=category,
                total_amount=round(float(values["amount"]), 2),
                transaction_count=int(values["count"]),
            )
            for category, values in sorted(
                categories.items(),
                key=lambda item: float(item[1]["amount"]),
                reverse=True,
            )
        ]
        return SpendingSummary(
            start_date=start_date,
            end_date=end_date,
            total_income=round(totals["income"], 2),
            total_expenses=round(totals["expense"], 2),
            total_investments=round(totals["investment"], 2),
            total_loan_repayments=round(totals["loan_repaid"], 2),
            category_breakdown=category_breakdown,
        )
