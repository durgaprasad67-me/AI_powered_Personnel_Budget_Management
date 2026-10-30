from copy import deepcopy
from datetime import date
from typing import Any

from bson import ObjectId


class FakeTransactionRepository:
    def __init__(self, documents: list[dict[str, Any]] | None = None):
        self.documents = {
            int(document["id"]): deepcopy(document)
            for document in (documents or [])
        }
        self.next_id = max(self.documents, default=0) + 1

    async def create(self, document: dict[str, Any]) -> dict[str, Any]:
        saved = deepcopy(document)
        saved["id"] = self.next_id
        self.next_id += 1
        self.documents[saved["id"]] = saved
        return deepcopy(saved)

    async def list(
        self,
        filters: dict[str, Any],
        *,
        limit: int,
        skip: int,
    ) -> tuple[list[dict[str, Any]], int]:
        items = [
            deepcopy(document)
            for document in self.documents.values()
            if all(
                self._matches(document, key, value)
                for key, value in filters.items()
            )
        ]
        return items[skip : skip + limit], len(items)

    async def get(self, transaction_id: int) -> dict[str, Any] | None:
        document = self.documents.get(transaction_id)
        return deepcopy(document) if document is not None else None

    async def update(
        self,
        transaction_id: int,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        if transaction_id not in self.documents:
            return None
        self.documents[transaction_id].update(deepcopy(changes))
        return await self.get(transaction_id)

    async def replace(
        self,
        transaction_id: int,
        document: dict[str, Any],
    ) -> dict[str, Any] | None:
        if transaction_id not in self.documents:
            return None
        replacement = deepcopy(document)
        replacement["id"] = transaction_id
        self.documents[transaction_id] = replacement
        return await self.get(transaction_id)

    async def delete(self, transaction_id: int) -> bool:
        return self.documents.pop(transaction_id, None) is not None

    @staticmethod
    def _matches(document: dict[str, Any], key: str, value: Any) -> bool:
        if isinstance(value, dict):
            actual = document.get(key)
            return all(
                (actual >= bound if operator == "$gte" else actual <= bound)
                for operator, bound in value.items()
            )
        return document.get(key) == value


class FakeBudgetRepository:
    def __init__(self, documents: list[dict[str, Any]] | None = None):
        self.documents = {
            str(document.get("id", ObjectId())): deepcopy(document)
            for document in (documents or [])
        }

    @staticmethod
    def parse_id(budget_id: str) -> ObjectId | None:
        return ObjectId(budget_id) if ObjectId.is_valid(budget_id) else None

    async def create(self, document: dict[str, Any]) -> dict[str, Any]:
        budget_id = str(ObjectId())
        saved = deepcopy(document)
        saved["id"] = budget_id
        self.documents[budget_id] = saved
        return deepcopy(saved)

    async def get(self, budget_id: str) -> dict[str, Any] | None:
        document = self.documents.get(budget_id)
        return deepcopy(document) if document is not None else None

    async def list(
        self,
        *,
        limit: int,
        skip: int,
    ) -> tuple[list[dict[str, Any]], int]:
        items = list(self.documents.values())
        return deepcopy(items[skip : skip + limit]), len(items)

    async def update(
        self,
        budget_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        if budget_id not in self.documents:
            return None
        self.documents[budget_id].update(deepcopy(changes))
        return await self.get(budget_id)

    async def delete(self, budget_id: str) -> bool:
        return self.documents.pop(budget_id, None) is not None

    async def spent_amount(
        self,
        *,
        start_date: str,
        end_date: str,
        category: str | None,
    ) -> float:
        return 0.0


class FakeGoalRepository:
    def __init__(self, documents: list[dict[str, Any]] | None = None):
        self.documents = {
            str(document.get("id", ObjectId())): deepcopy(document)
            for document in (documents or [])
        }

    @staticmethod
    def parse_id(goal_id: str) -> ObjectId | None:
        return ObjectId(goal_id) if ObjectId.is_valid(goal_id) else None

    async def create(self, document: dict[str, Any]) -> dict[str, Any]:
        goal_id = str(ObjectId())
        saved = deepcopy(document)
        saved["id"] = goal_id
        self.documents[goal_id] = saved
        return deepcopy(saved)

    async def get(self, goal_id: str) -> dict[str, Any] | None:
        document = self.documents.get(goal_id)
        return deepcopy(document) if document is not None else None

    async def list(
        self,
        filters: dict[str, Any],
        *,
        limit: int,
        skip: int,
    ) -> tuple[list[dict[str, Any]], int]:
        items = [
            document
            for document in self.documents.values()
            if all(document.get(key) == value for key, value in filters.items())
        ]
        return deepcopy(items[skip : skip + limit]), len(items)

    async def update(
        self,
        goal_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        if goal_id not in self.documents:
            return None
        self.documents[goal_id].update(deepcopy(changes))
        return await self.get(goal_id)

    async def delete(self, goal_id: str) -> bool:
        return self.documents.pop(goal_id, None) is not None


class FakeAnalyticsRepository:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []

    async def grouped_rows(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        return deepcopy(self.rows)
