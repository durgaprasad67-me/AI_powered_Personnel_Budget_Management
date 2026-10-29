from app.db.client import transactions_collection


async def ensure_indexes() -> None:
    await transactions_collection.create_index([("date", -1), ("_id", -1)])
    await transactions_collection.create_index(
        [("category", 1), ("date", -1), ("_id", -1)]
    )
