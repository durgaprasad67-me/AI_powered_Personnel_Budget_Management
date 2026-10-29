from datetime import date as Date
from datetime import timedelta
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection


def serialize_budget(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["id"] = str(result.pop("_id"))
    return result


class BudgetRepository:
    def __init__(
        self,
        budgets: AsyncCollection,
        transactions: AsyncCollection,
    ):
        self.budgets = budgets
        self.transactions = transactions

    @staticmethod
    def parse_id(budget_id: str) -> ObjectId | None:
        if not ObjectId.is_valid(budget_id):
            return None
        return ObjectId(budget_id)

    async def create(self, document: dict[str, Any]) -> dict[str, Any] | None:
        result = await self.budgets.insert_one(document)
        saved = await self.budgets.find_one({"_id": result.inserted_id})
        return serialize_budget(saved) if saved is not None else None

    async def get(self, budget_id: str) -> dict[str, Any] | None:
        object_id = self.parse_id(budget_id)
        if object_id is None:
            return None
        document = await self.budgets.find_one({"_id": object_id})
        return serialize_budget(document) if document is not None else None

    async def list(
        self,
        *,
        limit: int,
        skip: int,
    ) -> tuple[list[dict[str, Any]], int]:
        total = await self.budgets.count_documents({})
        cursor = (
            self.budgets.find({})
            .sort("_id", -1)
            .skip(skip)
            .limit(limit)
        )
        items = [serialize_budget(document) async for document in cursor]
        return items, total

    async def update(
        self,
        budget_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        object_id = self.parse_id(budget_id)
        if object_id is None:
            return None
        result = await self.budgets.update_one(
            {"_id": object_id},
            {"$set": changes},
        )
        if result.matched_count == 0:
            return None
        return await self.get(budget_id)

    async def delete(self, budget_id: str) -> bool:
        object_id = self.parse_id(budget_id)
        if object_id is None:
            return False
        result = await self.budgets.delete_one({"_id": object_id})
        return result.deleted_count > 0

    async def spent_amount(
        self,
        *,
        start_date: str,
        end_date: str,
        category: str | None,
    ) -> float:
        query: dict[str, Any] = {
            "date": {"$gte": start_date, "$lte": end_date},
            "transaction_type": "expense",
        }
        if category:
            query["category"] = category

        spent_amount = 0.0
        cursor = self.transactions.find(query, {"amount": 1})
        async for transaction in cursor:
            spent_amount += float(transaction["amount"])
        return round(spent_amount, 2)


def period_end(start: Date, period: str) -> Date:
    if period == "weekly":
        return start + timedelta(days=6)
    if period == "monthly":
        next_month = (
            Date(start.year + 1, 1, 1)
            if start.month == 12
            else Date(start.year, start.month + 1, 1)
        )
        return next_month - timedelta(days=1)
    if period == "quarterly":
        month = start.month + 3
        year = start.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return Date(year, month, 1) - timedelta(days=1)
    return Date(start.year, 12, 31)
