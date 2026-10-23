from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import transactions_collection
from app.schemas.transaction import TransactionCreate, TransactionUpdate


router = APIRouter(tags=["Transactions"])

# Reusable error messages
INVALID_TRANSACTION_ID = "Invalid transaction ID"
TRANSACTION_NOT_FOUND = "Transaction not found"
NO_CHANGES_PROVIDED = "No changes provided"
NULL_UPDATE_FIELDS = "Updated fields cannot be null"

# Reusable HTTP response documentation
INVALID_ID_RESPONSE: dict[int | str, dict[str, Any]] = {
    400: {"description": INVALID_TRANSACTION_ID},
}
NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {"description": TRANSACTION_NOT_FOUND},
}
TRANSACTION_ERROR_RESPONSES = {**INVALID_ID_RESPONSE,**NOT_FOUND_RESPONSE,}
UPDATE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid transaction ID or no changes provided"},
    404: {"description": TRANSACTION_NOT_FOUND},
    422: {"description": NULL_UPDATE_FIELDS},
}


# Convert MongoDB ObjectId into a JSON-compatible string
def serialize_transaction(document: dict[str, Any],) -> dict[str, Any]:
    document["_id"] = str(document["_id"])
    return document


# Create a transaction
@router.post("/transactions",status_code=status.HTTP_201_CREATED,)
async def create_transaction(transaction: TransactionCreate):
    data = transaction.model_dump(mode="json")
    result = await transactions_collection.insert_one(data)
    saved = await transactions_collection.find_one({"_id": result.inserted_id})

    if saved is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve created transaction",
        )

    return serialize_transaction(saved)


# Get transactions with optional filters and pagination
@router.get("/transactions")
async def get_transactions(transaction_type: str | None = Query(default=None,pattern="^(income|expense)$",),category: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),skip: int = Query(default=0, ge=0),):

    filters = {}
    if transaction_type:
        filters["transaction_type"] = transaction_type
    if category:
        filters["category"] = category

    cursor = (transactions_collection.find(filters).sort("date", -1).skip(skip).limit(limit))
    transactions = []

    async for document in cursor:
        transactions.append(serialize_transaction(document))

    return {"count": len(transactions),"transactions": transactions,}


# Get one transaction by ID
@router.get("/transactions/{transaction_id}",responses=TRANSACTION_ERROR_RESPONSES,)
async def get_transaction(transaction_id: str):
    if not ObjectId.is_valid(transaction_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=INVALID_TRANSACTION_ID,)

    transaction = await transactions_collection.find_one({"_id": ObjectId(transaction_id)})

    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=TRANSACTION_NOT_FOUND,)

    return serialize_transaction(transaction)


# Update selected transaction fields (PATCH)
@router.patch("/transactions/{transaction_id}",responses=UPDATE_ERROR_RESPONSES,)
async def update_transaction(transaction_id: str,updates: TransactionUpdate,):
    if not ObjectId.is_valid(transaction_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=INVALID_TRANSACTION_ID,)

    changes = updates.model_dump(mode="json",exclude_unset=True,)

    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=NO_CHANGES_PROVIDED,)
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,detail=NULL_UPDATE_FIELDS,)

    result = await transactions_collection.update_one({"_id": ObjectId(transaction_id)},{"$set": changes},)

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=TRANSACTION_NOT_FOUND,)

    updated = await transactions_collection.find_one({"_id": ObjectId(transaction_id)})

    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TRANSACTION_NOT_FOUND)

    return serialize_transaction(updated)


#  Replace an entire transaction (PUT)
@router.put("/transactions/{transaction_id}",responses=TRANSACTION_ERROR_RESPONSES,)
async def replace_transaction(transaction_id: str,transaction: TransactionCreate,):
    if not ObjectId.is_valid(transaction_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=INVALID_TRANSACTION_ID,)

    data = transaction.model_dump(mode="json")
    result = await transactions_collection.replace_one({"_id": ObjectId(transaction_id)},data,)

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=TRANSACTION_NOT_FOUND,)

    updated = await transactions_collection.find_one({"_id": ObjectId(transaction_id)})
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=TRANSACTION_NOT_FOUND,)

    return serialize_transaction(updated)


# Delete a transaction
@router.delete("/transactions/{transaction_id}",responses=TRANSACTION_ERROR_RESPONSES,)
async def delete_transaction(transaction_id: str):
    if not ObjectId.is_valid(transaction_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=INVALID_TRANSACTION_ID,)

    result = await transactions_collection.delete_one({"_id": ObjectId(transaction_id)})

    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=TRANSACTION_NOT_FOUND,)

    return {"message": "Transaction deleted successfully",}


