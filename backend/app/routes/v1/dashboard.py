from fastapi import APIRouter, Query
from app.core.database import transactions_collection
from app.schemas.common import CASH_IN_TYPES, CASH_OUT_TYPES

router = APIRouter(tags=["Analytics"])


def build_summary(month: str, rows: list[dict]) -> dict:
    """Turn grouped database rows into the monthly summary (no database needed)."""
    totals: dict[str, float] = {}
    spending_by_category: dict[str, float] = {}

    for row in rows:
        kind = row["_id"]["type"]
        total = row["total"]
        totals[kind] = totals.get(kind, 0) + total
        if kind == "expense":
            category = row["_id"]["category"]
            spending_by_category[category] = spending_by_category.get(category, 0) + total

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
        "balance": round(income - expenses, 2),  # income minus spending
        "investments": {
            "invested": amount("investment"),
            "returned": amount("investment_return"),
            "net_invested": round(totals.get("investment", 0) - totals.get("investment_return", 0), 2),
        },
        "loans": {
            "borrowed": amount("loan_taken"),
            "repaid": amount("loan_repaid"),
            "lent": amount("loan_given"),
            "collected": amount("loan_collected"),
        },
        "net_cash_flow": round(cash_in - cash_out, 2),  # all money in minus all money out
        "category_breakdown": {
            category: round(total, 2)
            for category, total in spending_by_category.items()
        },
    }


# Monthly income, spending, investments, loans and category breakdown
@router.get("/analytics/summary")
async def spending_summary(
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Month in YYYY-MM format",
    ),
):
    # Dates are stored as YYYY-MM-DD text, so a range finds the month
    # (and can use the date index, unlike a regex).
    year, month_number = int(month[:4]), int(month[5:])
    next_year, next_month = (year + 1, 1) if month_number == 12 else (year, month_number + 1)
    match = {"date": {"$gte": f"{month}-01", "$lt": f"{next_year}-{next_month:02d}-01"}}

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {
                    "type": "$transaction_type",
                    "category": "$category",
                },
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
            }
        },
    ]

    # PyMongo's async aggregate() must be awaited first to get the cursor.
    cursor = await transactions_collection.aggregate(pipeline)
    rows = await cursor.to_list(length=None)
    return build_summary(month, rows)