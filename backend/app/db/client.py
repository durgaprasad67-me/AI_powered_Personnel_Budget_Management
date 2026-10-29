from urllib.parse import quote_plus

from pymongo import AsyncMongoClient

from app.core.config import get_settings
from app.repositories.transactions import insert_with_next_id as insert_transaction_with_next_id

settings = get_settings()

if settings.mongo_user and settings.mongo_password and settings.mongo_cluster:
    username = quote_plus(settings.mongo_user)
    password = quote_plus(settings.mongo_password)
    MONGODB_URL = (
        f"mongodb+srv://{username}:{password}@{settings.mongo_cluster}/"
        "?retryWrites=true&w=majority"
    )
else:
    MONGODB_URL = "mongodb://localhost:27017"

client = AsyncMongoClient(MONGODB_URL)
database = client[settings.database_name]


def get_database():
    return database


transactions_collection = database["transactions"]
budgets_collection = database["budgets"]
financial_goals_collection = database["financial_goals"]


async def insert_with_next_id(document: dict) -> int:
    """Compatibility wrapper for the legacy import route."""
    return await insert_transaction_with_next_id(transactions_collection, document)


async def close_database():
    await client.close()
