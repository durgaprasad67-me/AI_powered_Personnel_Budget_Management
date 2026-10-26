from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.core.database import (
    insert_with_next_id,
    transactions_collection,
)
from app.schemas.common import TRANSACTION_TYPES, clean_lower, normalize_type
from app.schemas.transactions import (
    TransactionCreate,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])

TransactionId = Annotated[int, Path(ge=1)]
TRANSACTION_NOT_FOUND = "Transaction not found."


def serialize_transaction(document: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB's numeric _id to the public id field."""
    result = dict(document)
    result["id"] = result.pop("_id")
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_transaction(transaction: TransactionCreate):
    data = transaction.model_dump(mode="json")

    new_id = await insert_with_next_id(data)
    saved = await transactions_collection.find_one({"_id": new_id})

    if saved is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve the created transaction.",
        )

    return serialize_transaction(saved)


@router.get("")
async def get_transactions(
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
):
    filters: dict[str, Any] = {}

    if transaction_type:
        normalized_type = normalize_type(transaction_type)

        if normalized_type not in TRANSACTION_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"transaction_type must be one of: {', '.join(TRANSACTION_TYPES)}",
            )

        filters["transaction_type"] = normalized_type

    if category:
        filters["category"] = clean_lower(category)

    if start_date or end_date:
        date_filter = {}

        if start_date:
            date_filter["$gte"] = start_date

        if end_date:
            date_filter["$lte"] = end_date

        filters["date"] = date_filter

    total = await transactions_collection.count_documents(filters)

    cursor = (
        transactions_collection.find(filters)
        .sort([("date", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )

    items = [serialize_transaction(document) async for document in cursor]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


@router.get("/{transaction_id}")
async def get_transaction(transaction_id: TransactionId):
    document = await transactions_collection.find_one({"_id": transaction_id})

    if document is None:
        raise HTTPException(
            status_code=404,
            detail=TRANSACTION_NOT_FOUND,
        )

    return serialize_transaction(document)


@router.patch("/{transaction_id}")
async def update_transaction(
    transaction_id: TransactionId,
    updates: TransactionUpdate,
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

    result = await transactions_collection.update_one(
        {"_id": transaction_id},
        {
            "$set": changes,
            "$pull": {"auto_filled": {"$in": list(changes)}},
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail=TRANSACTION_NOT_FOUND,
        )

    document = await transactions_collection.find_one({"_id": transaction_id})

    if document is None:
        raise HTTPException(
            status_code=404,
            detail=TRANSACTION_NOT_FOUND,
        )

    return serialize_transaction(document)


@router.put("/{transaction_id}")
async def replace_transaction(
    transaction_id: TransactionId,
    transaction: TransactionCreate,
):
    data = transaction.model_dump(mode="json")

    result = await transactions_collection.replace_one(
        {"_id": transaction_id},
        data,
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail=TRANSACTION_NOT_FOUND,
        )

    document = await transactions_collection.find_one({"_id": transaction_id})

    if document is None:
        raise HTTPException(
            status_code=404,
            detail=TRANSACTION_NOT_FOUND,
        )

    return serialize_transaction(document)


@router.delete("/{transaction_id}")
async def delete_transaction(transaction_id: TransactionId):
    result = await transactions_collection.delete_one({"_id": transaction_id})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail=TRANSACTION_NOT_FOUND,
        )

    return {"message": "Transaction deleted successfully."}