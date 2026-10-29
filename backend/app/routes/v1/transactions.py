from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import get_transaction_service
from app.services.transactions import TransactionService
from app.schemas.transactions import (
    TransactionCreate,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["Transactions"])

TransactionId = Annotated[int, Path(ge=1)]
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_transaction(
    transaction: TransactionCreate,
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.create(transaction)


@router.get("")
async def get_transactions(
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.list(
        transaction_type=transaction_type,
        category=category,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        skip=skip,
    )


@router.get("/{transaction_id}")
async def get_transaction(
    transaction_id: TransactionId,
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.get(transaction_id)


@router.patch("/{transaction_id}")
async def update_transaction(
    transaction_id: TransactionId,
    updates: TransactionUpdate,
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.update(transaction_id, updates)


@router.put("/{transaction_id}")
async def replace_transaction(
    transaction_id: TransactionId,
    transaction: TransactionCreate,
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.replace(transaction_id, transaction)


@router.delete("/{transaction_id}")
async def delete_transaction(
    transaction_id: TransactionId,
    service: TransactionService = Depends(get_transaction_service),
):
    await service.delete(transaction_id)
    return {"message": "Transaction deleted successfully."}