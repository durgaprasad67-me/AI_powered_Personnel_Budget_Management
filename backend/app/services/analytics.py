from datetime import date as Date
from datetime import timedelta
from typing import Any

from app.core.exceptions import InvalidInputError
from app.domain.transaction_types import (
    CASH_IN_TYPES,
    CASH_OUT_TYPES,
    TRANSACTION_TYPES,
)
from app.repositories.analytics import AnalyticsRepository
from app.schemas.insights import CategorySpending, SpendingSummary


def build_monthly_summary(month: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, float] = {}
    spending_by_category: dict[str, float] = {}

    for row in rows:
        kind = row["_id"]["type"]
        total = row["total"]
        totals[kind] = totals.get(kind, 0) + total
        if kind == "expense":
            category = row["_id"]["category"]
            spending_by_category[category] = (
                spending_by_category.get(category, 0) + total
            )

    def amount(kind: str) -> float:
        return round(totals.get(kind, 0), 2)

    income = totals.get("income", 0)
    expenses = totals.get("expense", 0)
    cash_in = sum(totals.get(kind, 0) for kind in CASH_IN_TYPES)
    cash_out = sum(totals.get(kind, 0) for kind in CASH_OUT_TYPES)

    return {
        "month": month,
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "balance": round(income - expenses, 2),
        "investments": {
            "invested": amount("investment"),
            "returned": amount("investment_return"),
            "net_invested": round(
                totals.get("investment", 0)
                - totals.get("investment_return", 0),
                2,
            ),
        },
        "loans": {
            "borrowed": amount("loan_taken"),
            "repaid": amount("loan_repaid"),
            "lent": amount("loan_given"),
            "collected": amount("loan_collected"),
        },
        "net_cash_flow": round(cash_in - cash_out, 2),
        "category_breakdown": {
            category: round(total, 2)
            for category, total in spending_by_category.items()
        },
    }


class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository):
        self.repository = repository

    async def monthly_summary(self, month: str) -> dict[str, Any]:
        year, month_number = int(month[:4]), int(month[5:])
        next_year, next_month = (
            (year + 1, 1) if month_number == 12 else (year, month_number + 1)
        )
        rows = await self.repository.grouped_rows(
            start_date=Date(year, month_number, 1),
            end_date=Date(next_year, next_month, 1) - timedelta(days=1),
        )
        return build_monthly_summary(month, rows)

    async def spending_summary(
        self,
        start_date: Date,
        end_date: Date,
    ) -> SpendingSummary:
        if start_date > end_date:
            raise InvalidInputError("start_date must not be after end_date.")

        rows = await self.repository.grouped_rows(
            start_date=start_date,
            end_date=end_date,
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
