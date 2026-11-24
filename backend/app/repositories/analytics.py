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

    async def get_date_coverage(
        self,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any]:
        match: dict[str, Any] = {}
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
                    "_id": None,
                    "min_date": {"$min": "$date"},
                    "max_date": {"$max": "$date"},
                    "count": {"$sum": 1},
                }
            },
        ]
        cursor = await self.collection.aggregate(pipeline)
        results = await cursor.to_list(length=1)
        if not results:
            return {"min_date": None, "max_date": None, "count": 0}
        return {
            "min_date": results[0].get("min_date"),
            "max_date": results[0].get("max_date"),
            "count": results[0].get("count", 0),
        }

    async def monthly_grouped_rows(
        self,
        *,
        start_date: Date | None = None,
        end_date: Date | None = None,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> list[dict[str, Any]]:
        match: dict[str, Any] = {}
        if start_date or end_date:
            date_filter: dict[str, Any] = {}
            if start_date:
                date_filter["$gte"] = start_date.isoformat()
            if end_date:
                date_filter["$lte"] = end_date.isoformat()
            match["date"] = date_filter
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
                        "month": {"$substr": ["$date", 0, 7]},
                        "type": "$transaction_type",
                        "category": "$category",
                    },
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.month": 1}},
        ]
        cursor = await self.collection.aggregate(pipeline)
        return await cursor.to_list(length=None)
