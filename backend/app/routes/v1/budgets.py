from datetime import date as Date, timedelta
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import (
    budgets_collection,
    transactions_collection,
)
from app.schemas.budgets import (
    BudgetCreate,
    BudgetUpdate,
    BudgetProgress,
)


router = APIRouter(prefix="/budgets", tags=["Budgets"])

BUDGET_NOT_FOUND_DETAIL = "Budget not found."


def serialize_budget(document: dict) -> dict:
    result = dict(document)
    result["id"] = str(result.pop("_id"))
    return result


def parse_budget_id(budget_id: str) -> ObjectId:
    if not ObjectId.is_valid(budget_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid budget ID.",
        )

    return ObjectId(budget_id)


async def get_budget_or_404(budget_id: str) -> dict:
    document = await budgets_collection.find_one(
        {"_id": parse_budget_id(budget_id)}
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail=BUDGET_NOT_FOUND_DETAIL,
        )

    return document


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_budget(budget: BudgetCreate):
    data = budget.model_dump(mode="json")

    result = await budgets_collection.insert_one(data)

    saved = await budgets_collection.find_one(
        {"_id": result.inserted_id}
    )

    if saved is None:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve the created budget.",
        )

    return serialize_budget(saved)


@router.get("")
async def list_budgets(
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
):
    total = await budgets_collection.count_documents({})

    cursor = (
        budgets_collection.find({})
        .sort("_id", -1)
        .skip(skip)
        .limit(limit)
    )

    items = [
        serialize_budget(document)
        async for document in cursor
    ]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


@router.get("/{budget_id}")
async def get_budget(budget_id: str):
    document = await get_budget_or_404(budget_id)
    return serialize_budget(document)


@router.patch("/{budget_id}")
async def update_budget(
    budget_id: str,
    updates: BudgetUpdate,
):
    changes = updates.model_dump(
        mode="json",
        exclude_unset=True,
    )

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No changes provided.",
        )

    current = await get_budget_or_404(budget_id)

    merged = {**current, **changes}

    start_date = Date.fromisoformat(merged["start_date"])
    end_date = (
        Date.fromisoformat(merged["end_date"])
        if merged.get("end_date")
        else None
    )

    if end_date is not None and end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="end_date must be on or after start_date.",
        )

    if merged.get("period") == "custom" and end_date is None:
        raise HTTPException(
            status_code=422,
            detail="Custom budgets require an end_date.",
        )

    result = await budgets_collection.update_one(
        {"_id": parse_budget_id(budget_id)},
        {"$set": changes},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail=BUDGET_NOT_FOUND_DETAIL,
        )

    updated = await get_budget_or_404(budget_id)

    return serialize_budget(updated)


@router.delete("/{budget_id}")
async def delete_budget(budget_id: str):
    result = await budgets_collection.delete_one(
        {"_id": parse_budget_id(budget_id)}
    )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail=BUDGET_NOT_FOUND_DETAIL,
        )

    return {"message": "Budget deleted successfully."}


@router.get("/{budget_id}/progress")
async def get_budget_progress(budget_id: str):
    budget = await get_budget_or_404(budget_id)

    start_date = budget["start_date"]
    end_date = budget.get("end_date")

    if end_date is None:
        start = Date.fromisoformat(start_date)

        if budget["period"] == "weekly":
            end = start + timedelta(days=6)
        elif budget["period"] == "monthly":
            next_month = (
                Date(start.year + 1, 1, 1)
                if start.month == 12
                else Date(start.year, start.month + 1, 1)
            )
            end = next_month - timedelta(days=1)
        elif budget["period"] == "quarterly":
            month = start.month + 3
            year = start.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            next_quarter = Date(year, month, 1)
            end = next_quarter - timedelta(days=1)
        else:
            end = Date(start.year, 12, 31)

        end_date = end.isoformat()

    query = {
        "date": {
            "$gte": start_date,
            "$lte": end_date,
        },
        "transaction_type": "expense",
    }

    if budget.get("category"):
        query["category"] = budget["category"]

    spent_amount = 0.0

    cursor = transactions_collection.find(
        query,
        {"amount": 1},
    )

    async for transaction in cursor:
        spent_amount += float(transaction["amount"])

    spent_amount = round(spent_amount, 2)
    budget_amount = float(budget["amount"])

    progress = BudgetProgress(
        budget_id=budget_id,
        budget_amount=budget_amount,
        spent_amount=spent_amount,
        remaining_amount=round(budget_amount - spent_amount, 2),
        percentage_used=round(
            spent_amount / budget_amount * 100,
            2,
        ),
        is_over_budget=spent_amount > budget_amount,
    )

    return progress