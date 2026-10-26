import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError
load_dotenv()

MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_CLUSTER = os.getenv("MONGO_CLUSTER")
DATABASE_NAME = os.getenv("DATABASE_NAME", "finsight_db")

if not MONGO_USER or not MONGO_PASSWORD or not MONGO_CLUSTER:
    raise RuntimeError("Set MONGO_USER, MONGO_PASSWORD, and MONGO_CLUSTER in .env")

# Encode credentials in case the password contains URL-reserved characters.
username = quote_plus(MONGO_USER)
password = quote_plus(MONGO_PASSWORD)
MONGODB_URL = (f"mongodb+srv://{username}:{password}@{MONGO_CLUSTER}/""?retryWrites=true&w=majority")

client = AsyncMongoClient(MONGODB_URL)

#collection definitions
database = client[DATABASE_NAME]
transactions_collection = database["transactions"]
budgets_collection = database["budgets"]
financial_goals_collection = database["financial_goals"]
counters_collection = database["counters"]


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
