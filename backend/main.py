from contextlib import asynccontextmanager
from typing import Any
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query, status
from database import transactions_collection, close_database
from schemas import TransactionCreate, TransactionUpdate


# Reusable error messages
INVALID_TRANSACTION_ID = "Invalid transaction ID"
TRANSACTION_NOT_FOUND = "Transaction not found"
NO_CHANGES_PROVIDED = "No changes provided"
NULL_UPDATE_FIELDS = "Updated fields cannot be null"

# Reusable HTTP response documentation
INVALID_ID_RESPONSE = {400: {"description": INVALID_TRANSACTION_ID},}
NOT_FOUND_RESPONSE = {404: {"description": TRANSACTION_NOT_FOUND},}
TRANSACTION_ERROR_RESPONSES = {**INVALID_ID_RESPONSE,**NOT_FOUND_RESPONSE,}
UPDATE_ERROR_RESPONSES = {400: {"description": "Invalid transaction ID or no changes provided"},
    404: {"description": TRANSACTION_NOT_FOUND},
    422: {"description": NULL_UPDATE_FIELDS},}

# Application startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    await transactions_collection.database.command("ping")
    yield
    await close_database()

app = FastAPI(
    title="FinSight AI API",
    description="Personal Finance and Spending Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Convert MongoDB ObjectId into a JSON-compatible string
def serialize_transaction(document: dict[str, Any],) -> dict[str, Any]:
    document["_id"] = str(document["_id"])
    return document

#  Home endpoint
@app.get("/")
async def home():
    return {
        "message": "Welcome to FinSight AI",
        "status": "running",
        "version": "1.0.0",
    }


# Health endpoint
@app.get("/health")
async def health_check():
    await transactions_collection.database.command("ping")
    return {"status": "healthy","database": "connected",}

# Create a transaction
@app.post("/transactions",status_code=status.HTTP_201_CREATED,)
async def create_transaction(transaction: TransactionCreate):
    data = transaction.model_dump(mode="json")
    result = await transactions_collection.insert_one(data)
    saved = await transactions_collection.find_one({"_id": result.inserted_id})

    return serialize_transaction(saved)


# Get transactions with optional filters and pagination
@app.get("/transactions")
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
@app.get("/transactions/{transaction_id}",responses=TRANSACTION_ERROR_RESPONSES,)
async def get_transaction(transaction_id: str):
    if not ObjectId.is_valid(transaction_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=INVALID_TRANSACTION_ID,)

    transaction = await transactions_collection.find_one({"_id": ObjectId(transaction_id)})

    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=TRANSACTION_NOT_FOUND,)

    return serialize_transaction(transaction)


# Update selected transaction fields (PATCH)
@app.patch("/transactions/{transaction_id}",responses=UPDATE_ERROR_RESPONSES,)
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

    return serialize_transaction(updated)


#  Replace an entire transaction (PUT)
@app.put("/transactions/{transaction_id}",responses=TRANSACTION_ERROR_RESPONSES,)
async def replace_transaction(transaction_id: str,transaction: TransactionCreate,):
    if not ObjectId.is_valid(transaction_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=INVALID_TRANSACTION_ID,)

    data = transaction.model_dump(mode="json")
    result = await transactions_collection.replace_one({"_id": ObjectId(transaction_id)},data,)

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=TRANSACTION_NOT_FOUND,)

    updated = await transactions_collection.find_one({"_id": ObjectId(transaction_id)})
    return serialize_transaction(updated)


# Delete a transaction
@app.delete("/transactions/{transaction_id}",responses=TRANSACTION_ERROR_RESPONSES,)
async def delete_transaction(transaction_id: str):
    if not ObjectId.is_valid(transaction_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=INVALID_TRANSACTION_ID,)

    result = await transactions_collection.delete_one({"_id": ObjectId(transaction_id)})

    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=TRANSACTION_NOT_FOUND,)

    return {"message": "Transaction deleted successfully",}


#  Monthly income, expenses, balance, and category breakdown
@app.get("/analytics/summary")
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
