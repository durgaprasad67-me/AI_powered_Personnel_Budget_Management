from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import get_current_user_id, get_transaction_service
from app.schemas.common import MessageResponse
from app.schemas.transactions import (
    BudgetLimitResponse,
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)
from app.services.transactions import TransactionService

router = APIRouter(prefix="/transactions", tags=["Transactions"])

TransactionId = Annotated[int, Path(ge=1)]


@router.get("/budget-limit", response_model=BudgetLimitResponse)
async def get_budget_limit(
    transaction_type: str = Query(default="expense"),
    category: str | None = Query(default=None),
    date: str | None = Query(default=None),
    exclude_id: int | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.get_budget_limit(
        transaction_type=transaction_type,
        category=category,
        date=date,
        exclude_id=exclude_id,
        user_id=user_id,
    )


@router.post(
    "", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED
)
async def create_transaction(
    transaction: TransactionCreate,
    user_id: str = Depends(get_current_user_id),
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.create(transaction, user_id=user_id)


@router.get("", response_model=TransactionListResponse)
async def get_transactions(
    transaction_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user_id),
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.list(
        transaction_type=transaction_type,
        category=category,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        skip=skip,
        user_id=user_id,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: TransactionId,
    user_id: str = Depends(get_current_user_id),
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.get(transaction_id, user_id=user_id)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: TransactionId,
    updates: TransactionUpdate,
    user_id: str = Depends(get_current_user_id),
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.update(transaction_id, updates, user_id=user_id)


@router.put("/{transaction_id}", response_model=TransactionResponse)
async def replace_transaction(
    transaction_id: TransactionId,
    transaction: TransactionCreate,
    user_id: str = Depends(get_current_user_id),
    service: TransactionService = Depends(get_transaction_service),
):
    return await service.replace(transaction_id, transaction, user_id=user_id)


@router.delete("/{transaction_id}", response_model=MessageResponse)
async def delete_transaction(
    transaction_id: TransactionId,
    user_id: str = Depends(get_current_user_id),
    service: TransactionService = Depends(get_transaction_service),
):
    await service.delete(transaction_id, user_id=user_id)
    return {"message": "Transaction deleted successfully."}
