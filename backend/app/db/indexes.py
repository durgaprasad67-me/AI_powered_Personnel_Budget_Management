from app.db.collections import TRANSACTIONS


async def ensure_indexes(database) -> None:
    transactions = database[TRANSACTIONS]
    await transactions.create_index([("date", -1), ("_id", -1)])
    await transactions.create_index([("category", 1), ("date", -1), ("_id", -1)])
