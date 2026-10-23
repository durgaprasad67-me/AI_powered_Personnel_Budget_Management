import re
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.core.database import next_sequence, transactions_collection
from app.schemas.transaction import TransactionCreate, TransactionUpdate, clean_lower


router = APIRouter(tags=["Transactions"])

# Reusable error messages
TRANSACTION_NOT_FOUND = "Transaction not found"
NO_CHANGES_PROVIDED = "No changes provided"
NULL_UPDATE_FIELDS = "Updated fields cannot be null"

# Reusable HTTP response documentation
NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {"description": TRANSACTION_NOT_FOUND},
}
UPDATE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": NO_CHANGES_PROVIDED},
    404: {"description": TRANSACTION_NOT_FOUND},
    422: {"description": NULL_UPDATE_FIELDS},
}

# Simple transaction number used in URLs: 1, 2, 3...
TransactionId = Annotated[int, Path(ge=1, description="Transaction number (1, 2, 3...)")]


# MongoDB's _id is our simple number (1, 2, 3...); clients see it as "id"
def serialize_transaction(document: dict[str, Any]) -> dict[str, Any]:
    transaction_id = document.pop("_id", None)
    return {"id": transaction_id, **document}


# Match saved text ignoring letter case and extra spaces ("  FOOD " finds "food")
def loose_match(text: str) -> dict[str, str]:
    words = clean_lower(text).split()
    pattern = r"^\s*" + r"\s+".join(re.escape(word) for word in words) + r"\s*$"
    return {"$regex": pattern, "$options": "i"}


# Create a transaction
@router.post("/transactions", status_code=status.HTTP_201_CREATED)
async def create_transaction(transaction: TransactionCreate):
    data = transaction.model_dump(mode="json")
    data["_id"] = await next_sequence()

    await transactions_collection.insert_one(data)
    saved = await transactions_collection.find_one(
        {"_id": data["_id"]}
    )

    if saved is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve created transaction",
        )

    return serialize_transaction(saved)


# Get transactions with optional filters and pagination
@router.get("/transactions")
async def get_transactions(
    transaction_type: str | None = Query(default=None),
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
):
    filters: dict[str, Any] = {}

    if transaction_type:
        clean_type = clean_lower(transaction_type)
        if clean_type not in ("income", "expense"):
            raise HTTPException(
                status_code=422,
                detail="transaction_type must be income or expense",
            )
        filters["transaction_type"] = clean_type

    clean_category = clean_lower(category) if category else ""
    if clean_category:
        filters["category"] = loose_match(clean_category)

    cursor = (
        transactions_collection.find(filters)
        .sort([("date", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )
    transactions = []

    async for document in cursor:
        transactions.append(serialize_transaction(document))

    return {"count": len(transactions), "transactions": transactions}


# Get one transaction by its number
@router.get("/transactions/{transaction_id}", responses=NOT_FOUND_RESPONSE)
async def get_transaction(transaction_id: TransactionId):
    transaction = await transactions_collection.find_one({"_id": transaction_id})

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )

    return serialize_transaction(transaction)


# Update selected transaction fields (PATCH)
@router.patch("/transactions/{transaction_id}", responses=UPDATE_ERROR_RESPONSES)
async def update_transaction(transaction_id: TransactionId, updates: TransactionUpdate):
    changes = updates.model_dump(mode="json", exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=NO_CHANGES_PROVIDED,
        )
    if any(value is None for value in changes.values()):
        raise HTTPException(
            status_code=422,
            detail=NULL_UPDATE_FIELDS,
        )

    result = await transactions_collection.update_one(
        {"_id": transaction_id},
        {"$set": changes},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )

    updated = await transactions_collection.find_one({"_id": transaction_id})

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )

    return serialize_transaction(updated)


# Replace an entire transaction (PUT)
@router.put("/transactions/{transaction_id}", responses=NOT_FOUND_RESPONSE)
async def replace_transaction(transaction_id: TransactionId, transaction: TransactionCreate):
    data = transaction.model_dump(mode="json")
    result = await transactions_collection.replace_one({"_id": transaction_id}, data)

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )

    updated = await transactions_collection.find_one({"_id": transaction_id})

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )

    return serialize_transaction(updated)


# Delete a transaction
@router.delete("/transactions/{transaction_id}", responses=NOT_FOUND_RESPONSE)
async def delete_transaction(transaction_id: TransactionId):
    result = await transactions_collection.delete_one({"_id": transaction_id})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )

    return {"message": "Transaction deleted successfully"}