from __future__ import annotations

from typing import Any

from pymongo.asynchronous.collection import AsyncCollection


class RAGDocumentRepository:
    """Mongo persistence for source documents used to rebuild Chroma."""

    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def upsert_source(self, document: dict[str, Any]) -> dict[str, Any] | None:
        user_id = str(document["user_id"])
        normalized_filename = str(document["normalized_filename"])
        key = {
            "user_id": user_id,
            "normalized_filename": normalized_filename,
        }
        values = dict(document)
        values.pop("_id", None)
        values.pop("user_id", None)
        values.pop("normalized_filename", None)
        await self.collection.update_one(
            key,
            {
                "$set": values,
                "$setOnInsert": key,
            },
            upsert=True,
        )
        return await self.collection.find_one(key)

    async def get(self, *, user_id: str, doc_id: str) -> dict[str, Any] | None:
        return await self.collection.find_one(
            {"user_id": user_id, "doc_id": doc_id}
        )

    async def mark_indexed(
        self,
        *,
        user_id: str,
        doc_id: str,
        content_hash: str,
        indexed_at: str,
        embedding_model: str,
        chunks_created: int,
    ) -> bool:
        result = await self.collection.update_one(
            {
                "user_id": user_id,
                "doc_id": doc_id,
                "content_hash": content_hash,
            },
            {
                "$set": {
                    "vector_index_status": "indexed",
                    "vector_indexed_at": indexed_at,
                    "embedding_model": embedding_model,
                    "vector_content_hash": content_hash,
                    "chunks_created": chunks_created,
                }
            },
        )
        return result.modified_count > 0 or result.matched_count > 0

    async def delete(self, *, user_id: str, doc_id: str) -> bool:
        result = await self.collection.delete_one(
            {"user_id": user_id, "doc_id": doc_id}
        )
        return result.deleted_count > 0

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        cursor = self.collection.find(
            {"user_id": user_id},
            projection={
                "doc_id": 1,
                "source": 1,
                "content_hash": 1,
                "uploaded_at": 1,
                "vector_index_status": 1,
                "chunks_created": 1,
            },
        ).sort("source", 1)
        return await cursor.to_list(length=None)

    async def list_sources(self, user_id: str | None = None):
        query = {"user_id": user_id} if user_id is not None else {}
        cursor = self.collection.find(query).sort([("user_id", 1), ("source", 1)])
        return cursor
