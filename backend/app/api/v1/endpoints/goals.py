from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_goal_service
from app.schemas.financial_goals import (
    FinancialGoalCreate,
    FinancialGoalProgress,
    FinancialGoalUpdate,
)
from app.services.goals import GoalService


router = APIRouter(
    prefix="/financial-goals",
    tags=["Financial Goals"],
)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_financial_goal(
    goal: FinancialGoalCreate,
    service: GoalService = Depends(get_goal_service),
):
    return await service.create(goal)


@router.get("")
async def list_financial_goals(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern="^(active|completed|paused|cancelled)$",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    service: GoalService = Depends(get_goal_service),
):
    return await service.list(
        status_filter=status_filter,
        limit=limit,
        skip=skip,
    )


@router.get("/{goal_id}")
async def get_financial_goal(
    goal_id: str,
    service: GoalService = Depends(get_goal_service),
):
    return await service.get(goal_id)


@router.patch("/{goal_id}")
async def update_financial_goal(
    goal_id: str,
    updates: FinancialGoalUpdate,
    service: GoalService = Depends(get_goal_service),
):
    return await service.update(goal_id, updates)


@router.get("/{goal_id}/progress", response_model=FinancialGoalProgress)
async def get_financial_goal_progress(
    goal_id: str,
    service: GoalService = Depends(get_goal_service),
):
    return await service.progress(goal_id)


@router.delete("/{goal_id}")
async def delete_financial_goal(
    goal_id: str,
    service: GoalService = Depends(get_goal_service),
):
    await service.delete(goal_id)
    return {"message": "Financial goal deleted successfully."}
