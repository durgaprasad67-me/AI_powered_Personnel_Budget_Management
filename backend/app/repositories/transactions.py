from typing import Any

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError


def serialize_transaction(document: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB's numeric _id to the public id field."""
    result = dict(document)
    result["id"] = result.pop("_id")
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
    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def create(self, document: dict[str, Any]) -> dict[str, Any] | None:
        new_id = await insert_with_next_id(self.collection, document)
        saved = await self.collection.find_one({"_id": new_id})
        return serialize_transaction(saved) if saved is not None else None

    async def list(
        self,
        filters: dict[str, Any],
        *,
        limit: int,
        skip: int,
    ) -> tuple[list[dict[str, Any]], int]:
        total = await self.collection.count_documents(filters)
        cursor = (
            self.collection.find(filters)
            .sort([("date", -1), ("_id", -1)])
            .skip(skip)
            .limit(limit)
        )
        items = [serialize_transaction(document) async for document in cursor]
        return items, total

    async def get(self, transaction_id: int) -> dict[str, Any] | None:
        document = await self.collection.find_one({"_id": transaction_id})
        return serialize_transaction(document) if document is not None else None

    async def update(
        self,
        transaction_id: int,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = await self.collection.update_one(
            {"_id": transaction_id},
            {
                "$set": changes,
                "$pull": {"auto_filled": {"$in": list(changes)}},
            },
        )
        if result.matched_count == 0:
            return None
        return await self.get(transaction_id)

    async def replace(
        self,
        transaction_id: int,
        document: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = await self.collection.replace_one(
            {"_id": transaction_id},
            document,
        )
        if result.matched_count == 0:
            return None
        return await self.get(transaction_id)

    async def delete(self, transaction_id: int) -> bool:
        result = await self.collection.delete_one({"_id": transaction_id})
        return result.deleted_count > 0
