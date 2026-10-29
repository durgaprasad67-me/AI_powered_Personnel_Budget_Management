from typing import Any

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection


def serialize_goal(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["id"] = str(result.pop("_id"))
    return result


class GoalRepository:
    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    @staticmethod
    def parse_id(goal_id: str) -> ObjectId | None:
        if not ObjectId.is_valid(goal_id):
            return None
        return ObjectId(goal_id)

    async def create(self, document: dict[str, Any]) -> dict[str, Any] | None:
        result = await self.collection.insert_one(document)
        saved = await self.collection.find_one({"_id": result.inserted_id})
        return serialize_goal(saved) if saved is not None else None

    async def get(self, goal_id: str) -> dict[str, Any] | None:
        object_id = self.parse_id(goal_id)
        if object_id is None:
            return None
        document = await self.collection.find_one({"_id": object_id})
        return serialize_goal(document) if document is not None else None

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
            .sort("_id", -1)
            .skip(skip)
            .limit(limit)
        )
        items = [serialize_goal(document) async for document in cursor]
        return items, total

    async def update(
        self,
        goal_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        object_id = self.parse_id(goal_id)
        if object_id is None:
            return None
        result = await self.collection.update_one(
            {"_id": object_id},
            {"$set": changes},
        )
        if result.matched_count == 0:
            return None
        return await self.get(goal_id)

    async def delete(self, goal_id: str) -> bool:
        object_id = self.parse_id(goal_id)
        if object_id is None:
            return False
        result = await self.collection.delete_one({"_id": object_id})
        return result.deleted_count > 0
