from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from app.core.user_context import DEFAULT_CURRENT_USER_ID


class FakeTransactionRepository:
    def __init__(self, documents: list[dict[str, Any]] | None = None):
        self.documents = {
            int(document["id"]): deepcopy(document) for document in (documents or [])
        }
        self.next_id = max(self.documents, default=0) + 1

    async def create(
        self,
        document: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any]:
        saved = deepcopy(document)
        saved["user_id"] = user_id
        saved["vector_index_status"] = "pending"
        saved.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        saved["id"] = self.next_id
        self.next_id += 1
        self.documents[saved["id"]] = saved
        return deepcopy(saved)

    async def find_recent_identical(
        self,
        *,
        user_id: str,
        amount: float,
        category: str,
        date: str,
        transaction_type: str,
        within_seconds: float,
    ) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
        for doc in self.documents.values():
            if self._belongs_to_user(doc, user_id):
                if (
                    float(doc.get("amount", 0)) == float(amount)
                    and doc.get("category") == category
                    and str(doc.get("date")) == str(date)
                    and doc.get("transaction_type") == transaction_type
                    and doc.get("created_at", "") >= cutoff
                ):
                    return True
        return False

    async def list(
        self,
        filters: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
        limit: int,
        skip: int,
        sort_descending: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        items = [
            deepcopy(document)
            for document in self.documents.values()
            if self._belongs_to_user(document, user_id)
            and all(
                self._matches(document, key, value) for key, value in filters.items()
            )
        ]
        items.sort(
            key=lambda document: (
                str(document.get("date", "")),
                int(document["id"]),
            ),
            reverse=sort_descending,
        )
        return items[skip : skip + limit], len(items)

    async def get(
        self,
        transaction_id: int,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any] | None:
        document = self.documents.get(transaction_id)
        if document is not None and not self._belongs_to_user(document, user_id):
            return None
        return deepcopy(document) if document is not None else None

    async def update(
        self,
        transaction_id: int,
        changes: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any] | None:
        if transaction_id not in self.documents:
            return None
        if not self._belongs_to_user(self.documents[transaction_id], user_id):
            return None
        self.documents[transaction_id].update(deepcopy(changes))
        self.documents[transaction_id].update(
            {"user_id": user_id, "vector_index_status": "pending"}
        )
        self.documents[transaction_id].pop("vector_indexed_at", None)
        self.documents[transaction_id].pop("vector_text_hash", None)
        return await self.get(transaction_id, user_id=user_id)

    async def replace(
        self,
        transaction_id: int,
        document: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any] | None:
        if transaction_id not in self.documents:
            return None
        if not self._belongs_to_user(self.documents[transaction_id], user_id):
            return None
        replacement = deepcopy(document)
        replacement["user_id"] = user_id
        replacement["vector_index_status"] = "pending"
        replacement["id"] = transaction_id
        self.documents[transaction_id] = replacement
        return await self.get(transaction_id, user_id=user_id)

    async def delete(
        self,
        transaction_id: int,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> bool:
        if transaction_id in self.documents and not self._belongs_to_user(
            self.documents[transaction_id], user_id
        ):
            return False
        return self.documents.pop(transaction_id, None) is not None

    async def mark_vector_indexed(
        self,
        *,
        transaction_id: str | int,
        user_id: str,
        text_hash: str,
        indexed_at: str,
    ) -> bool:
        try:
            identifier = int(transaction_id)
        except (TypeError, ValueError):
            return False
        document = self.documents.get(identifier)
        if document is None or not self._belongs_to_user(document, user_id):
            return False
        document.update(
            {
                "vector_index_status": "indexed",
                "vector_text_hash": text_hash,
                "vector_indexed_at": indexed_at,
            }
        )
        return True

    @staticmethod
    def _belongs_to_user(document: dict[str, Any], user_id: str) -> bool:
        actual = document.get("user_id")
        if user_id == DEFAULT_CURRENT_USER_ID:
            return actual in (None, user_id)
        return actual == user_id

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
    def __init__(
        self,
        documents: list[dict[str, Any]] | None = None,
        *,
        spent_amount_value: float = 0.0,
        transaction_repository: FakeTransactionRepository | None = None,
    ):
        self.documents = {
            str(document.get("id", ObjectId())): deepcopy(document)
            for document in (documents or [])
        }
        self.spent_amount_value = spent_amount_value
        self.transaction_repository = transaction_repository

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

    async def allocation_conflict(
        self,
        budget: dict[str, Any],
        *,
        exclude_budget_id: str | None = None,
    ) -> dict[str, Any] | None:
        candidate_is_global = (
            budget.get("transaction_type") == "all" and not budget.get("category")
        )
        existing = [
            item
            for item in self.documents.values()
            if item.get("id") != exclude_budget_id
        ]
        globals_ = [
            item
            for item in existing
            if item.get("transaction_type") == "all" and not item.get("category")
        ]
        if candidate_is_global:
            globals_.append(budget)
        for global_budget in globals_:
            specific = [
                item
                for item in existing
                if not (
                    item.get("transaction_type") == "all"
                    and not item.get("category")
                )
            ]
            if not candidate_is_global:
                specific.append(budget)
            allocated = round(sum(float(item["amount"]) for item in specific), 2)
            limit = float(global_budget["amount"])
            if allocated > limit:
                return {
                    "limit": limit,
                    "allocated": allocated,
                    "budgets": [
                        {
                            "name": item.get("name")
                            or item.get("category")
                            or "Budget",
                            "amount": float(item["amount"]),
                        }
                        for item in specific
                    ],
                }
        return None

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
        transaction_type: str = "expense",
        user_id: str = DEFAULT_CURRENT_USER_ID,
        exclude_transaction_id: int | None = None,
    ) -> float:
        if self.transaction_repository is not None:
            from app.repositories.budgets import _category_values

            cat_vals = _category_values(category)
            total = 0.0
            for tx in self.transaction_repository.documents.values():
                tx_id = tx.get("id") or tx.get("_id")
                if exclude_transaction_id is not None and tx_id == exclude_transaction_id:
                    continue
                tx_date = str(tx.get("date", ""))
                if not (start_date <= tx_date <= end_date):
                    continue
                tx_type = tx.get("transaction_type")
                if transaction_type != "all" and tx_type != transaction_type:
                    continue
                tx_cat = tx.get("category")
                if cat_vals and (not tx_cat or tx_cat not in cat_vals):
                    continue
                total += float(tx.get("amount", 0.0))
            return round(total, 2)
        return self.spent_amount_value

    async def get_monthly_budget_status(
        self,
        *,
        date: str,
        category: str | None,
        transaction_type: str,
        user_id: str = DEFAULT_CURRENT_USER_ID,
        exclude_transaction_id: int | None = None,
    ) -> dict[str, Any]:
        from datetime import date as Date
        from app.core.config import get_settings
        from app.repositories.budgets import _category_values, period_end

        dt = Date.fromisoformat(str(date)[:10])
        month_start = Date(dt.year, dt.month, 1).isoformat()
        month_end = period_end(Date(dt.year, dt.month, 1), "monthly").isoformat()
        month_name = dt.strftime("%B %Y")

        matching_budgets = []
        for b in self.documents.values():
            b_start = str(b.get("start_date", ""))
            b_end = str(
                b.get("end_date")
                or period_end(Date.fromisoformat(b_start)).isoformat()
            )
            if not (b_start <= month_end and b_end >= month_start):
                continue
            b_type = b.get("transaction_type", "expense")
            if b_type != "all" and b_type != transaction_type:
                continue
            cat_vals = _category_values(b.get("category"))
            if cat_vals and (not category or category not in cat_vals):
                continue
            matching_budgets.append(b)

        if not matching_budgets:
            settings = get_settings()
            return {
                "has_budget": False,
                "month": month_name,
                "allocated_budget": None,
                "spent_amount": 0.0,
                "remaining_budget": None,
                "max_allowed": settings.max_outflow_amount_without_budget,
                "warning": f"No budget set for {month_name}.",
            }

        candidate_statuses = []
        for budget in matching_budgets:
            b_start = str(budget.get("start_date", ""))
            b_end = str(
                budget.get("end_date")
                or period_end(Date.fromisoformat(b_start)).isoformat()
            )
            eff_start = max(b_start, month_start)
            eff_end = min(b_end, month_end)
            spent = await self.spent_amount(
                start_date=eff_start,
                end_date=eff_end,
                category=budget.get("category"),
                transaction_type=budget.get("transaction_type", "expense"),
                user_id=user_id,
                exclude_transaction_id=exclude_transaction_id,
            )
            alloc = float(budget["amount"])
            rem = round(alloc - spent, 2)
            candidate_statuses.append(
                {
                    "budget": budget,
                    "allocated_budget": alloc,
                    "spent_amount": spent,
                    "remaining_budget": rem,
                    "max_allowed": max(0.0, rem),
                }
            )
        candidate_statuses.sort(key=lambda x: x["remaining_budget"])
        most = candidate_statuses[0]
        return {
            "has_budget": True,
            "month": month_name,
            "allocated_budget": most["allocated_budget"],
            "spent_amount": most["spent_amount"],
            "remaining_budget": most["remaining_budget"],
            "max_allowed": most["max_allowed"],
            "warning": None,
            "budget_name": most["budget"].get("name", "Budget"),
        }

    async def budget_violations(
        self,
        *,
        date: str,
        category: str,
        transaction_type: str,
        amount: float,
        user_id: str = DEFAULT_CURRENT_USER_ID,
        exclude_transaction_id: int | None = None,
        additional_transactions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        status = await self.get_monthly_budget_status(
            date=date,
            category=category,
            transaction_type=transaction_type,
            user_id=user_id,
            exclude_transaction_id=exclude_transaction_id,
        )
        if not status["has_budget"]:
            return []
        projected = round(status["spent_amount"] + amount, 2)
        if projected > status["allocated_budget"]:
            return [
                {
                    "name": status.get("budget_name", "Budget"),
                    "amount": status["allocated_budget"],
                    "projected": projected,
                }
            ]
        return []


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
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> list[dict[str, Any]]:
        return deepcopy(self.rows)


class FakeRAGDocumentRepository:
    def __init__(self):
        self.documents: dict[tuple[str, str], dict[str, Any]] = {}

    async def upsert_source(self, document: dict[str, Any]):
        key = (document["user_id"], document["normalized_filename"])
        saved = deepcopy(document)
        self.documents[key] = saved
        return deepcopy(saved)

    async def get(self, *, user_id: str, doc_id: str):
        return next(
            (
                deepcopy(item)
                for item in self.documents.values()
                if item["user_id"] == user_id and item["doc_id"] == doc_id
            ),
            None,
        )

    async def mark_indexed(
        self,
        *,
        user_id: str,
        doc_id: str,
        content_hash: str,
        indexed_at: str,
        embedding_model: str,
        chunks_created: int,
    ) -> bool:
        for item in self.documents.values():
            if (
                item["user_id"] == user_id
                and item["doc_id"] == doc_id
                and item["content_hash"] == content_hash
            ):
                item.update(
                    {
                        "vector_index_status": "indexed",
                        "vector_indexed_at": indexed_at,
                        "embedding_model": embedding_model,
                        "chunks_created": chunks_created,
                    }
                )
                return True
        return False

    async def delete(self, *, user_id: str, doc_id: str) -> bool:
        key = next(
            (
                key
                for key, item in self.documents.items()
                if item["user_id"] == user_id and item["doc_id"] == doc_id
            ),
            None,
        )
        if key is None:
            return False
        del self.documents[key]
        return True

    async def list_for_user(self, user_id: str):
        return [
            deepcopy(item)
            for item in self.documents.values()
            if item["user_id"] == user_id
        ]
