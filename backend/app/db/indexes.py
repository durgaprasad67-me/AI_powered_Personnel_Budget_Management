from app.db.collections import FINANCIAL_GOALS, TRANSACTIONS


async def ensure_indexes(database) -> None:
    transactions = database[TRANSACTIONS]
    await transactions.create_index([("date", -1), ("_id", -1)])
    await transactions.create_index([("category", 1), ("date", -1), ("_id", -1)])
    await transactions.create_index(
        [("transaction_type", 1), ("date", -1), ("_id", -1)],
        name="transactions_type_date_id",
    )

    goals = database[FINANCIAL_GOALS]
    await goals.create_index(
        [("status", 1), ("_id", -1)],
        name="goals_status_id",
    )
