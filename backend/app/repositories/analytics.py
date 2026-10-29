from datetime import date as Date
from typing import Any

from pymongo.asynchronous.collection import AsyncCollection


class AnalyticsRepository:
    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def grouped_rows(
        self,
        *,
        start_date: Date,
        end_date: Date,
    ) -> list[dict[str, Any]]:
        pipeline = [
            {
                "$match": {
                    "date": {
                        "$gte": start_date.isoformat(),
                        "$lte": end_date.isoformat(),
                    }
                }
            },
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
