from typing import Any

from app.core.exceptions import InvalidInputError, NotFoundError
from app.repositories.goals import GoalRepository
from app.schemas.goals import (
    FinancialGoalCreate,
    FinancialGoalProgress,
    FinancialGoalUpdate,
)


class GoalService:
    def __init__(self, repository: GoalRepository):
        self.repository = repository

    async def create(self, goal: FinancialGoalCreate) -> dict[str, Any]:
        data = goal.model_dump(mode="json")
        data["status"] = (
            "completed" if data["current_amount"] >= data["target_amount"] else "active"
        )
        saved = await self.repository.create(data)
        if saved is None:
            raise RuntimeError("Financial goal could not be retrieved after creation.")
        return saved

    async def list(
        self,
        *,
        status_filter: str | None,
        limit: int,
        skip: int,
    ) -> dict[str, Any]:
        filters = {"status": status_filter} if status_filter else {}
        items, total = await self.repository.list(
            filters,
            limit=limit,
            skip=skip,
        )
        return {"items": items, "total": total, "limit": limit, "skip": skip}

    async def get(self, goal_id: str) -> dict[str, Any]:
        if self.repository.parse_id(goal_id) is None:
            raise InvalidInputError(
                "Invalid financial goal ID.",
                status_code=400,
            )
        goal = await self.repository.get(goal_id)
        if goal is None:
            raise NotFoundError("Financial goal not found.")
        return goal

    async def update(
        self,
        goal_id: str,
        updates: FinancialGoalUpdate,
    ) -> dict[str, Any]:
        changes = updates.model_dump(mode="json", exclude_unset=True)
        if not changes:
            raise InvalidInputError("No changes provided.", status_code=400)
        if any(value is None for value in changes.values()):
            raise InvalidInputError("Updated fields cannot be null.")

        current = await self.get(goal_id)
        merged = {**current, **changes}
        if merged["current_amount"] > merged["target_amount"]:
            raise InvalidInputError("Current amount cannot exceed target amount.")

        if merged["current_amount"] >= merged["target_amount"]:
            changes["status"] = "completed"
        elif merged.get("status") == "completed":
            changes["status"] = "active"

        updated = await self.repository.update(goal_id, changes)
        if updated is None:
            raise NotFoundError("Financial goal not found.")
        return updated

    async def progress(self, goal_id: str) -> FinancialGoalProgress:
        goal = await self.get(goal_id)
        target = float(goal["target_amount"])
        current = float(goal["current_amount"])
        return FinancialGoalProgress(
            goal_id=goal_id,
            target_amount=target,
            current_amount=current,
            remaining_amount=round(target - current, 2),
            percentage_completed=round(current / target * 100, 2),
            is_completed=current >= target,
        )

    async def delete(self, goal_id: str) -> None:
        await self.get(goal_id)
        if not await self.repository.delete(goal_id):
            raise NotFoundError("Financial goal not found.")
