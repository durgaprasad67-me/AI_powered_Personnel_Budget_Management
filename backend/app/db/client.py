from functools import lru_cache
from urllib.parse import quote_plus

from pymongo import AsyncMongoClient

from app.core.config import get_settings


@lru_cache
def get_client() -> AsyncMongoClient:
    settings = get_settings()
    if not (settings.mongo_user and settings.mongo_password and settings.mongo_cluster):
        raise RuntimeError("MONGO_USER, MONGO_PASSWORD and MONGO_CLUSTER must be set")

    username = quote_plus(settings.mongo_user)
    password = quote_plus(settings.mongo_password)
    mongodb_url = (
        f"mongodb+srv://{username}:{password}@{settings.mongo_cluster}/"
        "?retryWrites=true&w=majority"
    )
    return AsyncMongoClient(mongodb_url)


@lru_cache
def get_database():
    return get_client()[get_settings().database_name]


async def close_database() -> None:
    client = get_client()
    await client.close()
    get_database.cache_clear()
    get_client.cache_clear()
