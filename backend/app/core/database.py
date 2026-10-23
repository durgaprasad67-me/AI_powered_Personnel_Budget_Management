import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pymongo import AsyncMongoClient, ReturnDocument

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
database = client[DATABASE_NAME]
transactions_collection = database["transactions"]

counters_collection = database["counters"]


async def next_sequence() -> int:
    # Find the transaction with the highest ID.
    last_transaction = await transactions_collection.find_one(
        {},
        projection={"_id": 1},
        sort=[("_id", -1)],
    )

    # Start at 1 if no transactions exist.
    if last_transaction is None:
        return 1

    # Otherwise, return the highest existing ID + 1.
    return last_transaction["_id"] + 1


async def close_database():
    await client.close()
