from __future__ import annotations

from datetime import date as Date
from datetime import timedelta
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection

from app.core.user_context import DEFAULT_CURRENT_USER_ID


def _user_scope(user_id: str) -> dict[str, Any]:
    user_id = (user_id or DEFAULT_CURRENT_USER_ID).strip()
    if user_id == DEFAULT_CURRENT_USER_ID:
        return {
            "$or": [
                {"user_id": DEFAULT_CURRENT_USER_ID},
                {"user_id": {"$exists": False}},
            ]
        }
    return {"user_id": user_id}


def serialize_budget(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["id"] = str(result.pop("_id"))
    return result


def budget_category_values(category: str | None) -> list[str] | None:
    if not category:
        return None
    val = category.strip().lower()
    if val in ("", "all", "all categories"):
        return None
    return [val]


_category_values = budget_category_values


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
        cursor = self.budgets.find({}).sort("_id", -1).skip(skip).limit(limit)
        items = [serialize_budget(document) async for document in cursor]
        return items, total

    async def allocation_conflict(
        self,
        budget: dict[str, Any],
        *,
        exclude_budget_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Return a conflict when detailed allocations exceed a global budget."""
        candidate_is_global = (
            budget.get("transaction_type") == "all" and not budget.get("category")
        )

        def date_range(item: dict[str, Any]) -> tuple[Date, Date]:
            start = Date.fromisoformat(str(item["start_date"]))
            end = Date.fromisoformat(
                str(item.get("end_date") or default_budget_end_date(start))
            )
            return start, end

        candidate_start, candidate_end = date_range(budget)
        existing = []
        cursor = self.budgets.find({})
        async for document in cursor:
            candidate = serialize_budget(document)
            if exclude_budget_id and candidate["id"] == exclude_budget_id:
                continue
            existing.append(candidate)

        global_budgets = list(existing)
        if candidate_is_global:
            global_budgets.append({**budget, "id": "__candidate__"})

        for global_budget in global_budgets:
            if not (
                global_budget.get("transaction_type") == "all"
                and not global_budget.get("category")
            ):
                continue
            global_start, global_end = date_range(global_budget)
            specific_budgets = [
                item
                for item in existing
                if not (
                    item.get("transaction_type") == "all"
                    and not item.get("category")
                )
                and date_range(item)[0] <= global_end
                and global_start <= date_range(item)[1]
            ]
            if not candidate_is_global and (
                candidate_start <= global_end and global_start <= candidate_end
            ):
                specific_budgets.append(budget)
            allocated = round(
                sum(float(item["amount"]) for item in specific_budgets),
                2,
            )
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
                        for item in specific_budgets
                    ],
                }
        return None

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
        transaction_type: str = "expense",
        user_id: str = DEFAULT_CURRENT_USER_ID,
        exclude_transaction_id: int | None = None,
    ) -> float:
        from app.domain.transaction_types import CASH_OUT_TYPES

        query: dict[str, Any] = {
            "date": {"$gte": start_date, "$lte": end_date},
        }
        if transaction_type == "all":
            query["transaction_type"] = {"$in": list(CASH_OUT_TYPES)}
        elif transaction_type in CASH_OUT_TYPES:
            query["transaction_type"] = transaction_type
        else:
            query["transaction_type"] = {"$in": []}
        clean_category = category.strip().lower() if category else None
        category_values = _category_values(clean_category)
        if category_values:
            query["category"] = {
                "$in": list(
                    set(
                        category_values
                        + [c.title() for c in category_values]
                        + [c.upper() for c in category_values]
                    )
                )
            }
        if exclude_transaction_id is not None:
            query["_id"] = {"$ne": exclude_transaction_id}

        scope = _user_scope(user_id)
        if "$or" in scope:
            match_clause = {"$and": [scope, query]}
        else:
            match_clause = {**query, **scope}

        pipeline = [
            {"$match": match_clause},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        cursor = await self.transactions.aggregate(pipeline)
        rows = await cursor.to_list(length=1)
        return round(float(rows[0]["total"]) if rows else 0.0, 2)

    async def get_monthly_budget_status(
        self,
        *,
        date: str,
        category: str | None,
        transaction_type: str,
        user_id: str = DEFAULT_CURRENT_USER_ID,
        exclude_transaction_id: int | None = None,
    ) -> dict[str, Any]:
        """Compute monthly budget status, spending, and remaining amount in IST."""
        from app.domain.transaction_types import CASH_IN_TYPES, CASH_OUT_TYPES
        from app.core.config import get_settings

        settings = get_settings()
        dt = Date.fromisoformat(str(date)[:10])
        month_start = Date(dt.year, dt.month, 1).isoformat()
        month_end = default_budget_end_date(Date(dt.year, dt.month, 1)).isoformat()
        month_name = dt.strftime("%B %Y")

        # Cash inflows do not follow budget rules
        if transaction_type in CASH_IN_TYPES or transaction_type not in CASH_OUT_TYPES:
            return {
                "has_budget": False,
                "month": month_name,
                "allocated_budget": None,
                "spent_amount": 0.0,
                "remaining_budget": None,
                "max_allowed": settings.max_inflow_amount,
                "warning": None,
            }

        matching_budgets: list[dict[str, Any]] = []
        clean_category = category.strip().lower() if category else None
        async for doc in self.budgets.find({}):
            b = serialize_budget(doc)
            b_start = b["start_date"]
            b_end = b.get("end_date") or default_budget_end_date(
                Date.fromisoformat(b_start)
            ).isoformat()
            if not (b_start <= month_end and b_end >= month_start):
                continue
            b_type = b.get("transaction_type", "expense")
            if b_type != "all" and b_type != transaction_type:
                continue
            cat_vals = _category_values(b.get("category"))
            if cat_vals and (not clean_category or clean_category not in cat_vals):
                continue
            matching_budgets.append(b)

        if not matching_budgets:
            from app.core.config import get_settings

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
            b_start = budget["start_date"]
            b_end = budget.get("end_date") or default_budget_end_date(
                Date.fromisoformat(b_start)
            ).isoformat()
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
        most_restrictive = candidate_statuses[0]
        return {
            "has_budget": True,
            "month": month_name,
            "allocated_budget": most_restrictive["allocated_budget"],
            "spent_amount": most_restrictive["spent_amount"],
            "remaining_budget": most_restrictive["remaining_budget"],
            "max_allowed": most_restrictive["max_allowed"],
            "warning": None,
            "budget_name": most_restrictive["budget"].get("name", "Budget"),
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
        """Return budgets that would exceed their limits after a transaction."""
        from app.domain.transaction_types import CASH_IN_TYPES, CASH_OUT_TYPES

        # Cash inflows do not follow budget rules
        if transaction_type in CASH_IN_TYPES or transaction_type not in CASH_OUT_TYPES:
            return []

        clean_category = category.strip().lower() if category else ""
        budgets = [serialize_budget(item) async for item in self.budgets.find({})]
        violations = []
        for budget in budgets:
            start_date = budget["start_date"]
            end_date = budget.get("end_date") or default_budget_end_date(
                Date.fromisoformat(start_date)
            ).isoformat()
            budget_type = budget.get("transaction_type", "expense")
            if not (start_date <= date <= end_date):
                continue
            category_values = _category_values(budget.get("category"))
            if category_values and clean_category not in category_values:
                continue
            if budget_type != "all" and budget_type != transaction_type:
                continue

            query: dict[str, Any] = {
                "date": {"$gte": start_date, "$lte": end_date},
            }
            budget_category_values = _category_values(budget.get("category"))
            if budget_category_values:
                query["category"] = {
                    "$in": list(
                        set(
                            budget_category_values
                            + [c.title() for c in budget_category_values]
                            + [c.upper() for c in budget_category_values]
                        )
                    )
                }
            if budget_type == "all":
                query["transaction_type"] = {"$in": list(CASH_OUT_TYPES)}
            else:
                query["transaction_type"] = budget_type
            if exclude_transaction_id is not None:
                query["_id"] = {"$ne": exclude_transaction_id}

            scope = _user_scope(user_id)
            if "$or" in scope:
                match_clause = {"$and": [scope, query]}
            else:
                match_clause = {**query, **scope}

            cursor = await self.transactions.aggregate(
                [
                    {"$match": match_clause},
                    {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
                ]
            )
            rows = await cursor.to_list(length=1)
            current = float(rows[0]["total"]) if rows else 0.0
            for staged in additional_transactions or []:
                staged_date = str(staged.get("date", ""))
                staged_type = staged.get("transaction_type")
                staged_category = staged.get("category")
                if not start_date <= staged_date <= end_date:
                    continue
                if budget_type == "all":
                    if staged_type not in CASH_OUT_TYPES:
                        continue
                elif staged_type != budget_type:
                    continue
                staged_cat = (staged_category or "").strip().lower()
                if (
                    budget_category_values
                    and staged_cat not in budget_category_values
                ):
                    continue
                current += float(staged.get("amount", 0))
            projected = round(current + amount, 2)
            if projected > float(budget["amount"]):
                violations.append(
                    {
                        "name": budget["name"],
                        "amount": float(budget["amount"]),
                        "projected": projected,
                        "current": current,
                        "remaining": round(float(budget["amount"]) - current, 2),
                    }
                )
        return violations


def default_budget_end_date(start: Date) -> Date:
    """Return the last day of the calendar month for the given start date."""
    next_month = (
        Date(start.year + 1, 1, 1)
        if start.month == 12
        else Date(start.year, start.month + 1, 1)
    )
    return next_month - timedelta(days=1)


def period_end(start: Date, period: str | None = None) -> Date:
    """Backwards-compatible alias for default_budget_end_date."""
    return default_budget_end_date(start)
