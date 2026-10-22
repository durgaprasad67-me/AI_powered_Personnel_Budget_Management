from fastapi import APIRouter, Query

from app.core.database import transactions_collection

router = APIRouter(tags=["Analytics"])


#  Monthly income, expenses, balance, and category breakdown
@router.get("/analytics/summary")
async def spending_summary(month: str = Query(...,pattern=r"^\d{4}-(0[1-9]|1[0-2])$",description="Month in YYYY-MM format",),):
    # Dates are stored as YYYY-MM-DD strings.
    match = {"date": {"$regex": f"^{month}-"}}

    pipeline = [{"$match": match},
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

    results = await transactions_collection.aggregate(pipeline).to_list(length=None)
    income = 0.0
    expenses = 0.0
    categories = {}

    for row in results:
        transaction_type = row["_id"]["type"]
        category = row["_id"]["category"]
        total = row["total"]
        if transaction_type == "income":
            income += total
        else:
            expenses += total
            categories[category] = (categories.get(category, 0) + total)

    return {
        "month": month,
        "total_income": round(income, 2),
        "total_expenses": round(expenses, 2),
        "balance": round(income - expenses, 2),
        "category_breakdown": {
            category: round(total, 2)
            for category, total in categories.items()
        },
    }
