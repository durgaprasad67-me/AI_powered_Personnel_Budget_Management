from datetime import date as Date

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import financial_goals_collection
from app.schemas.financial_goals import (
    FinancialGoalCreate,
    FinancialGoalUpdate,
    FinancialGoalProgress,
)


router = APIRouter(
    prefix="/financial-goals",
    tags=["Financial Goals"],
)

GOAL_NOT_FOUND_DETAIL = "Financial goal not found."


def serialize_goal(document: dict) -> dict:
    result = dict(document)
    result["id"] = str(result.pop("_id"))
    return result


def parse_goal_id(goal_id: str) -> ObjectId:
    if not ObjectId.is_valid(goal_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid financial goal ID.",
        )
    return ObjectId(goal_id)


async def get_goal_or_404(goal_id: str) -> dict:
    document = await financial_goals_collection.find_one(
        {"_id": parse_goal_id(goal_id)}
    )
    if document is None:
        raise HTTPException(
            status_code=404,
            detail=GOAL_NOT_FOUND_DETAIL,
        )
    return document


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_financial_goal(goal: FinancialGoalCreate):
    data = goal.model_dump(mode="json")

    # A goal that has already reached its target starts completed.
    if data["current_amount"] >= data["target_amount"]:
        data["status"] = "completed"
    else:
        data["status"] = "active"

    result = await financial_goals_collection.insert_one(data)

    saved = await financial_goals_collection.find_one(
        {"_id": result.inserted_id}
    )

    if saved is None:
        raise HTTPException(
            status_code=500,
            detail="Financial goal could not be retrieved after creation.",
        )

    return serialize_goal(saved)


@router.get("")
async def list_financial_goals(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern="^(active|completed|paused|cancelled)$",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
):
    filters = {}

    if status_filter:
        filters["status"] = status_filter

    total = await financial_goals_collection.count_documents(filters)

    cursor = (
        financial_goals_collection.find(filters)
        .sort("_id", -1)
        .skip(skip)
        .limit(limit)
    )

    items = [
        serialize_goal(document)
        async for document in cursor
    ]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


@router.get("/{goal_id}")
async def get_financial_goal(goal_id: str):
    document = await get_goal_or_404(goal_id)
    return serialize_goal(document)


@router.patch("/{goal_id}")
async def update_financial_goal(
    goal_id: str,
    updates: FinancialGoalUpdate,
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

    if any(value is None for value in changes.values()):
        raise HTTPException(
            status_code=422,
            detail="Updated fields cannot be null.",
        )

    current = await get_goal_or_404(goal_id)
    merged = {**current, **changes}

    if merged["current_amount"] > merged["target_amount"]:
        raise HTTPException(
            status_code=422,
            detail="Current amount cannot exceed target amount.",
        )

    # Keep completion status consistent with the target.
    if merged["current_amount"] >= merged["target_amount"]:
        changes["status"] = "completed"
    elif merged.get("status") == "completed":
        changes["status"] = "active"

    result = await financial_goals_collection.update_one(
        {"_id": parse_goal_id(goal_id)},
        {"$set": changes},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail=GOAL_NOT_FOUND_DETAIL,
        )

    updated = await get_goal_or_404(goal_id)

    return serialize_goal(updated)


@router.get("/{goal_id}/progress")
async def get_financial_goal_progress(goal_id: str):
    goal = await get_goal_or_404(goal_id)

    target = float(goal["target_amount"])
    current = float(goal["current_amount"])

    progress = FinancialGoalProgress(
        goal_id=goal_id,
        target_amount=target,
        current_amount=current,
        remaining_amount=round(target - current, 2),
        percentage_completed=round(
            current / target * 100,
            2,
        ),
        is_completed=current >= target,
    )

    return progress


@router.delete("/{goal_id}")
async def delete_financial_goal(goal_id: str):
    result = await financial_goals_collection.delete_one(
        {"_id": parse_goal_id(goal_id)}
    )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail=GOAL_NOT_FOUND_DETAIL,
        )

    return {"message": "Financial goal deleted successfully."}