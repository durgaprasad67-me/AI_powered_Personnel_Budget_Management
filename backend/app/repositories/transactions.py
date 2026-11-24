from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import InvalidInputError
from app.core.user_context import DEFAULT_CURRENT_USER_ID


def _user_scope(user_id: str) -> dict[str, Any]:
    user_id = user_id.strip()
    if not user_id:
        raise ValueError("user_id is required.")
    if user_id == DEFAULT_CURRENT_USER_ID:
        # Treat old, untagged records as belonging to the existing dashboard.
        return {
            "$or": [
                {"user_id": DEFAULT_CURRENT_USER_ID},
                {"user_id": {"$exists": False}},
            ]
        }
    return {"user_id": user_id}


def _scoped_filter(filters: dict[str, Any], user_id: str) -> dict[str, Any]:
    scope = _user_scope(user_id)
    if "$or" in scope:
        clauses = [scope, filters] if filters else [scope]
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}
    return {**filters, **scope}

def serialize_transaction(document: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB's _id to a JSON-compatible public id field."""
    result = dict(document)
    identifier = result.pop("_id")
    result["id"] = identifier if isinstance(identifier, int) else str(identifier)
    return result


async def insert_with_next_id(
    collection: AsyncCollection,
    document: dict[str, Any],
) -> int:
    """Save a transaction with _id = highest number in use + 1."""
    for _ in range(5):
        last = await collection.find_one(
            {"_id": {"$type": "number"}},
            projection={"_id": 1},
            sort=[("_id", -1)],
        )
        document["_id"] = last["_id"] + 1 if last else 1
        try:
            await collection.insert_one(document)
            return document["_id"]
        except DuplicateKeyError:
            continue
    raise RuntimeError("Could not assign a transaction number, please retry")


class TransactionRepository:
    def __init__(self, collection: AsyncCollection, budget_repository=None):
        self.collection = collection
        self.budget_repository = budget_repository

    async def create(
        self,
        document: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any] | None:
        document = dict(document)
        document["user_id"] = user_id
        document["vector_index_status"] = "pending"
        document.setdefault("created_at", datetime.now(timezone.utc).isoformat())

        # Ensure fingerprint is computed and stored on every transaction (imports and Add Transaction)
        if "fingerprint" not in document:
            from app.services.importing.deduplication import (
                compute_row_fingerprint,
                compute_row_fingerprint_base,
            )
            base_key = compute_row_fingerprint_base(
                user_id=user_id,
                date_str=str(document.get("date", "")),
                description=str(document.get("description", "")),
                amount=float(document.get("amount", 0.0)),
                tx_type=str(document.get("transaction_type", "expense")),
            )
            count = await self.collection.count_documents(
                {"user_id": user_id, "fingerprint_base": base_key}
            )
            document["fingerprint_base"] = base_key
            document["occurrence"] = count + 1
            document["fingerprint"] = compute_row_fingerprint(base_key, count + 1)

        new_id = await insert_with_next_id(self.collection, document)
        saved = await self.collection.find_one({"_id": new_id})
        return serialize_transaction(saved) if saved is not None else None

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
        """Check if an identical transaction was saved within the duplicate window."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
        query = _scoped_filter(
            {
                "amount": amount,
                "category": category,
                "date": str(date),
                "transaction_type": transaction_type,
                "created_at": {"$gte": cutoff},
            },
            user_id,
        )
        found = await self.collection.find_one(query)
        return found is not None

    async def list(
        self,
        filters: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
        limit: int,
        skip: int,
        sort_descending: bool = True,
        sort_by: list[tuple[str, int]] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query = _scoped_filter(filters, user_id)
        total = await self.collection.count_documents(query)
        direction = -1 if sort_descending else 1
        sort_clause = sort_by if sort_by is not None else [("date", direction), ("_id", direction)]
        cursor = (
            self.collection.find(query)
            .sort(sort_clause)
            .skip(skip)
            .limit(limit)
        )
        items = [serialize_transaction(document) async for document in cursor]
        return items, total

    async def get(
        self,
        transaction_id: int,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any] | None:
        query = _scoped_filter({"_id": transaction_id}, user_id)
        document = await self.collection.find_one(query)
        return serialize_transaction(document) if document is not None else None

    async def update(
        self,
        transaction_id: int,
        changes: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any] | None:
        result = await self.collection.update_one(
            _scoped_filter({"_id": transaction_id}, user_id),
            {
                "$set": {
                    **changes,
                    "user_id": user_id,
                    "vector_index_status": "pending",
                },
                "$unset": {
                    "vector_indexed_at": "",
                    "vector_text_hash": "",
                },
                "$pull": {"auto_filled": {"$in": list(changes)}},
            },
        )
        if result.matched_count == 0:
            return None
        return await self.get(transaction_id, user_id=user_id)

    async def replace(
        self,
        transaction_id: int,
        document: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any] | None:
        replacement = {
            **document,
            "user_id": user_id,
            "vector_index_status": "pending",
        }
        result = await self.collection.replace_one(
            _scoped_filter({"_id": transaction_id}, user_id),
            replacement,
        )
        if result.matched_count == 0:
            return None
        return await self.get(transaction_id, user_id=user_id)

    async def delete(
        self,
        transaction_id: int,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> bool:
        result = await self.collection.delete_one(
            _scoped_filter({"_id": transaction_id}, user_id)
        )
        return result.deleted_count > 0

    async def mark_vector_indexed(
        self,
        *,
        transaction_id: str | int,
        user_id: str,
        text_hash: str,
        indexed_at: str,
    ) -> bool:
        try:
            mongo_id: Any = int(transaction_id)
        except (TypeError, ValueError):
            mongo_id = transaction_id
        result = await self.collection.update_one(
            _scoped_filter({"_id": mongo_id}, user_id),
            {
                "$set": {
                    "vector_index_status": "indexed",
                    "vector_indexed_at": indexed_at,
                    "vector_text_hash": text_hash,
                }
            },
        )
        return result.matched_count > 0
