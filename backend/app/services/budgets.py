from datetime import date as Date
from typing import Any

from app.core.exceptions import InvalidInputError, NotFoundError
from app.repositories.budgets import BudgetRepository, period_end
from app.schemas.budgets import BudgetCreate, BudgetProgress, BudgetUpdate


class BudgetService:
    def __init__(self, repository: BudgetRepository):
        self.repository = repository

    async def create(self, budget: BudgetCreate) -> dict[str, Any]:
        saved = await self.repository.create(budget.model_dump(mode="json"))
        if saved is None:
            raise RuntimeError("Unable to retrieve the created budget.")
        return saved

    async def list(self, *, limit: int, skip: int) -> dict[str, Any]:
        items, total = await self.repository.list(limit=limit, skip=skip)
        return {"items": items, "total": total, "limit": limit, "skip": skip}

    async def get(self, budget_id: str) -> dict[str, Any]:
        if self.repository.parse_id(budget_id) is None:
            raise InvalidInputError("Invalid budget ID.", status_code=400)
        budget = await self.repository.get(budget_id)
        if budget is None:
            raise NotFoundError("Budget not found.")
        return budget

    async def update(
        self,
        budget_id: str,
        updates: BudgetUpdate,
    ) -> dict[str, Any]:
        changes = updates.model_dump(mode="json", exclude_unset=True)
        if not changes:
            raise InvalidInputError("No changes provided.", status_code=400)

        current = await self.get(budget_id)
        merged = {**current, **changes}
        start_date = Date.fromisoformat(merged["start_date"])
        end_date = (
            Date.fromisoformat(merged["end_date"]) if merged.get("end_date") else None
        )
        if end_date is not None and end_date < start_date:
            raise InvalidInputError("end_date must be on or after start_date.")
        if merged.get("period") == "custom" and end_date is None:
            raise InvalidInputError("Custom budgets require an end_date.")

        updated = await self.repository.update(budget_id, changes)
        if updated is None:
            raise NotFoundError("Budget not found.")
        return updated

    async def delete(self, budget_id: str) -> None:
        await self.get(budget_id)
        if not await self.repository.delete(budget_id):
            raise NotFoundError("Budget not found.")

    async def progress(self, budget_id: str) -> BudgetProgress:
        budget = await self.get(budget_id)
        start_date = budget["start_date"]
        end_date = budget.get("end_date")
        if end_date is None:
            end_date = period_end(
                Date.fromisoformat(start_date),
                budget["period"],
            ).isoformat()

        spent_amount = await self.repository.spent_amount(
            start_date=start_date,
            end_date=end_date,
            category=budget.get("category"),
        )
        budget_amount = float(budget["amount"])
        return BudgetProgress(
            budget_id=budget_id,
            budget_amount=budget_amount,
            spent_amount=spent_amount,
            remaining_amount=round(budget_amount - spent_amount, 2),
            percentage_used=round(spent_amount / budget_amount * 100, 2),
            is_over_budget=spent_amount > budget_amount,
        )
