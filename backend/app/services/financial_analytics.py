from datetime import date as Date
from typing import Any

from fastapi import HTTPException

from app.core.database import transactions_collection


SUPPORTED_TRANSACTION_TYPES = {
    "income",
    "expense",
    "investment",
    "investment_return",
    "loan_taken",
    "loan_repaid",
    "loan_given",
    "loan_collected",
}


async def get_financial_summary(
    start_date: Date,
    end_date: Date,
) -> dict[str, Any]:
    """
    Calculate financial totals and category-level expense
    breakdowns for the requested date range.
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must not be after end_date.",
        )

    match = {
        "date": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat(),
        }
    }

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {
                    "type": "$transaction_type",
                    "category": "$category",
                },
                "total_amount": {"$sum": "$amount"},
                "transaction_count": {"$sum": 1},
            }
        },
    ]

    cursor = await transactions_collection.aggregate(pipeline)
    rows = await cursor.to_list(length=None)

    totals = dict.fromkeys(SUPPORTED_TRANSACTION_TYPES, 0.0)

    category_totals: dict[str, dict[str, float | int]] = {}

    for row in rows:
        group = row["_id"]
        transaction_type = group.get("type")
        category = group.get("category") or "uncategorized"

        amount = float(row.get("total_amount") or 0)
        count = int(row.get("transaction_count") or 0)

        if transaction_type in totals:
            totals[transaction_type] += amount

        if transaction_type == "expense":
            category_entry = category_totals.setdefault(
                category,
                {
                    "total_amount": 0.0,
                    "transaction_count": 0,
                },
            )

            category_entry["total_amount"] += amount
            category_entry["transaction_count"] += count

    category_breakdown = [
        {
            "category": category,
            "total_amount": round(
                float(values["total_amount"]),
                2,
            ),
            "transaction_count": int(
                values["transaction_count"]
            ),
        }
        for category, values in sorted(
            category_totals.items(),
            key=lambda item: float(item[1]["total_amount"]),
            reverse=True,
        )
    ]

    total_income = round(totals["income"], 2)
    total_expenses = round(totals["expense"], 2)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_income_after_expenses": round(
            total_income - total_expenses,
            2,
        ),
        "total_investments": round(
            totals["investment"],
            2,
        ),
        "total_investment_returns": round(
            totals["investment_return"],
            2,
        ),
        "total_loan_taken": round(
            totals["loan_taken"],
            2,
        ),
        "total_loan_repaid": round(
            totals["loan_repaid"],
            2,
        ),
        "total_loan_given": round(
            totals["loan_given"],
            2,
        ),
        "total_loan_collected": round(
            totals["loan_collected"],
            2,
        ),
        "category_breakdown": category_breakdown,
    }


async def get_expense_by_category(
    start_date: Date,
    end_date: Date,
) -> list[dict[str, Any]]:
    """Return expense totals grouped by category."""
    summary = await get_financial_summary(
        start_date=start_date,
        end_date=end_date,
    )

    return summary["category_breakdown"]