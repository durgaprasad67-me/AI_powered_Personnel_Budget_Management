from datetime import date as Date
from typing import Any

from pymongo.asynchronous.collection import AsyncCollection

from app.core.user_context import DEFAULT_CURRENT_USER_ID


class AnalyticsRepository:
    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def grouped_rows(
        self,
        *,
        start_date: Date,
        end_date: Date,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> list[dict[str, Any]]:
        match: dict[str, Any] = {
            "date": {
                "$gte": start_date.isoformat(),
                "$lte": end_date.isoformat(),
            }
        }
        if user_id == DEFAULT_CURRENT_USER_ID:
            match["$or"] = [
                {"user_id": user_id},
                {"user_id": {"$exists": False}},
            ]
        else:
            match["user_id"] = user_id
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {
                        "type": "$transaction_type",
                        "category": "$category",
                    },
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1},
                }
            },
        ]
        cursor = await self.collection.aggregate(pipeline)
        return await cursor.to_list(length=None)
