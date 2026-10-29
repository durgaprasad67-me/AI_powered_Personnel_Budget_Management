from urllib.parse import quote_plus
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError
from app.core.config import get_settings

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

#collection definitions
database = client[settings.database_name]
transactions_collection = database["transactions"]
budgets_collection = database["budgets"]
financial_goals_collection = database["financial_goals"]


async def insert_with_next_id(document: dict) -> int:
    """Save a transaction with _id = highest number in use + 1 (1 when empty)."""
    for _ in range(5):
        last = await transactions_collection.find_one(
            {"_id": {"$type": "number"}},  # ignore any old ObjectId records
            projection={"_id": 1},
            sort=[("_id", -1)],
        )
        document["_id"] = last["_id"] + 1 if last else 1
        try:
            await transactions_collection.insert_one(document)
            return document["_id"]
        except DuplicateKeyError:
            continue  # another request took this number first, try the next
    raise RuntimeError("Could not assign a transaction number, please retry")


async def close_database():
    await client.close()
