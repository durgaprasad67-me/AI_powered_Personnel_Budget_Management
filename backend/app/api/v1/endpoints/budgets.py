from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_budget_service
from app.schemas.budgets import BudgetCreate, BudgetProgress, BudgetUpdate
from app.services.budgets import BudgetService

router = APIRouter(prefix="/budgets", tags=["Budgets"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_budget(
    budget: BudgetCreate,
    service: BudgetService = Depends(get_budget_service),
):
    return await service.create(budget)


@router.get("")
async def list_budgets(
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    service: BudgetService = Depends(get_budget_service),
):
    return await service.list(limit=limit, skip=skip)


@router.get("/{budget_id}")
async def get_budget(
    budget_id: str,
    service: BudgetService = Depends(get_budget_service),
):
    return await service.get(budget_id)


@router.patch("/{budget_id}")
async def update_budget(
    budget_id: str,
    updates: BudgetUpdate,
    service: BudgetService = Depends(get_budget_service),
):
    return await service.update(budget_id, updates)


@router.delete("/{budget_id}")
async def delete_budget(
    budget_id: str,
    service: BudgetService = Depends(get_budget_service),
):
    await service.delete(budget_id)
    return {"message": "Budget deleted successfully."}


@router.get("/{budget_id}/progress", response_model=BudgetProgress)
async def get_budget_progress(
    budget_id: str,
    service: BudgetService = Depends(get_budget_service),
):
    return await service.progress(budget_id)
