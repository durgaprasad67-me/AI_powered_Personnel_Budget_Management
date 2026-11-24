from __future__ import annotations

from typing import Any

from pymongo.asynchronous.collection import AsyncCollection

from app.core.config import get_settings


def _validate_user(user_id: str) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("Authenticated user_id is required.")
    return user_id.strip()


class RAGDocumentRepository:
    """Mongo persistence for source documents used to catalog and rebuild Chroma."""

    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def upsert_source(self, document: dict[str, Any]) -> dict[str, Any] | None:
        user_id = _validate_user(str(document.get("user_id", "")))
        normalized_filename = str(document["normalized_filename"])
        key = {
            "user_id": user_id,
            "normalized_filename": normalized_filename,
        }
        values = dict(document)
        values.pop("_id", None)
        values.pop("user_id", None)
        values.pop("normalized_filename", None)

        doc_id = str(document.get("doc_id") or document.get("document_id") or "")
        if doc_id:
            values["doc_id"] = doc_id
            values["document_id"] = doc_id

        source = str(document.get("source") or document.get("original_filename") or "")
        if source:
            values["source"] = source
            values["original_filename"] = source

        status = str(document.get("status") or document.get("vector_index_status") or "processing")
        values["status"] = status
        values["vector_index_status"] = status

        col_name = str(document.get("collection_name") or document.get("chroma_collection") or get_settings().chroma_collection_name)
        values["collection_name"] = col_name
        values["chroma_collection"] = col_name

        chunks = int(document.get("chunk_count") or document.get("chunks_created") or 0)
        values["chunk_count"] = chunks
        values["chunks_created"] = chunks

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
        user_id = _validate_user(user_id)
        return await self.collection.find_one(
            {"user_id": user_id, "$or": [{"doc_id": doc_id}, {"document_id": doc_id}]}
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
        collection_name: str | None = None,
    ) -> bool:
        user_id = _validate_user(user_id)
        col_name = collection_name or get_settings().chroma_collection_name
        result = await self.collection.update_one(
            {
                "user_id": user_id,
                "$or": [{"doc_id": doc_id}, {"document_id": doc_id}],
                "content_hash": content_hash,
            },
            {
                "$set": {
                    "status": "completed",
                    "vector_index_status": "completed",
                    "vector_indexed_at": indexed_at,
                    "indexed_at": indexed_at,
                    "embedding_model": embedding_model,
                    "vector_content_hash": content_hash,
                    "chunks_created": chunks_created,
                    "chunk_count": chunks_created,
                    "collection_name": col_name,
                    "chroma_collection": col_name,
                    "error_message": None,
                }
            },
        )
        return result.modified_count > 0 or result.matched_count > 0

    async def mark_failed(
        self,
        *,
        user_id: str,
        doc_id: str,
        error_message: str,
    ) -> bool:
        user_id = _validate_user(user_id)
        result = await self.collection.update_one(
            {
                "user_id": user_id,
                "$or": [{"doc_id": doc_id}, {"document_id": doc_id}],
            },
            {
                "$set": {
                    "status": "failed",
                    "vector_index_status": "failed",
                    "error_message": error_message,
                }
            },
        )
        return result.modified_count > 0 or result.matched_count > 0

    async def delete(self, *, user_id: str, doc_id: str) -> bool:
        user_id = _validate_user(user_id)
        result = await self.collection.delete_one(
            {"user_id": user_id, "$or": [{"doc_id": doc_id}, {"document_id": doc_id}]}
        )
        return result.deleted_count > 0

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        user_id = _validate_user(user_id)
        cursor = self.collection.find(
            {"user_id": user_id},
            projection={
                "doc_id": 1,
                "document_id": 1,
                "source": 1,
                "original_filename": 1,
                "file_type": 1,
                "content_hash": 1,
                "uploaded_at": 1,
                "status": 1,
                "vector_index_status": 1,
                "chunks_created": 1,
                "chunk_count": 1,
                "collection_name": 1,
                "chroma_collection": 1,
                "error_message": 1,
            },
        ).sort("source", 1)
        return await cursor.to_list(length=None)

    async def list_sources(self, user_id: str | None = None):
        query = {"user_id": user_id} if user_id is not None else {}
        cursor = self.collection.find(query).sort([("user_id", 1), ("source", 1)])
        return cursor
