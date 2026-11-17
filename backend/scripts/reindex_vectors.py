"""Idempotently rebuild stale or missing RAG vectors from Mongo source data."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.db.client import close_database, get_database
from app.db.collections import RAG_DOCUMENTS, TRANSACTIONS
from app.integrations.vector_store import (
    document_vectors_are_current,
    get_vector_store,
    mark_document_vectors_stale,
    mark_transaction_vector_stale,
    rebuild_vector_collection,
    transaction_vector_is_current,
)
from app.services.rag.documents import index_parsed_document, prepare_document
from app.services.rag.transaction_indexing import (
    index_transactions_sync,
    transaction_text_hash,
)


def _user_filter(user_id: str | None) -> dict[str, Any]:
    if user_id is None:
        return {}
    if user_id == DEFAULT_CURRENT_USER_ID:
        return {
            "$or": [
                {"user_id": user_id},
                {"user_id": {"$exists": False}},
            ]
        }
    return {"user_id": user_id}


async def _index_transaction_batch(
    collection,
    user_id: str,
    transactions: list[dict[str, Any]],
) -> int:
    if not transactions:
        return 0

    for transaction in transactions:
        await asyncio.to_thread(
            mark_transaction_vector_stale,
            transaction.get("_id"),
            user_id,
        )
        await collection.update_one(
            {"_id": transaction["_id"]},
            {"$set": {"user_id": user_id, "vector_index_status": "pending"}},
        )

    states = await asyncio.to_thread(index_transactions_sync, transactions, user_id)
    indexed_at = datetime.now(timezone.utc).isoformat()
    for transaction, (_source_id, text_hash) in zip(transactions, states):
        await collection.update_one(
            {"_id": transaction["_id"]},
            {
                "$set": {
                    "user_id": user_id,
                    "vector_index_status": "indexed",
                    "vector_indexed_at": indexed_at,
                    "vector_text_hash": text_hash,
                }
            },
        )
    return len(states)


async def reindex_transactions(database, *, user_id: str | None) -> tuple[int, int]:
    collection = database[TRANSACTIONS]
    query = _user_filter(user_id)
    cursor = collection.find(query).sort("_id", 1)
    batch_size = get_settings().gemini_embedding_batch_size
    batches: dict[str, list[dict[str, Any]]] = {}
    indexed = 0
    skipped = 0

    async for transaction in cursor:
        owner = str(transaction.get("user_id") or DEFAULT_CURRENT_USER_ID)
        current_hash = transaction.get("vector_text_hash")
        text_hash = transaction_text_hash(transaction)
        if (
            transaction.get("vector_index_status") == "indexed"
            and current_hash == text_hash
            and await asyncio.to_thread(
                transaction_vector_is_current,
                transaction.get("_id"),
                owner,
                text_hash,
            )
        ):
            skipped += 1
            continue

        batch = batches.setdefault(owner, [])
        batch.append(transaction)
        if len(batch) >= batch_size:
            indexed += await _index_transaction_batch(collection, owner, batch)
            batches[owner] = []

    for owner, batch in batches.items():
        indexed += await _index_transaction_batch(collection, owner, batch)
    return indexed, skipped


async def reindex_documents(database, *, user_id: str | None) -> tuple[int, int]:
    collection = database[RAG_DOCUMENTS]
    cursor = collection.find(_user_filter(user_id)).sort(
        [("user_id", 1), ("normalized_filename", 1)]
    )
    indexed = 0
    skipped = 0
    settings = get_settings()

    async for document in cursor:
        raw_content = document.get("raw_content")
        if not isinstance(raw_content, bytes):
            skipped += 1
            continue

        model_matches = document.get("embedding_model") == settings.gemini_embedding_model
        hash_matches = document.get("vector_content_hash") == document.get("content_hash")
        if (
            document.get("vector_index_status") == "indexed"
            and model_matches
            and hash_matches
            and await asyncio.to_thread(
                document_vectors_are_current,
                str(document["doc_id"]),
                str(document["user_id"]),
                str(document["content_hash"]),
            )
        ):
            skipped += 1
            continue

        key = {
            "user_id": document["user_id"],
            "doc_id": document["doc_id"],
            "content_hash": document["content_hash"],
        }
        await collection.update_one(
            key,
            {"$set": {"vector_index_status": "pending"}},
        )
        await asyncio.to_thread(
            mark_document_vectors_stale,
            str(document["doc_id"]),
            str(document["user_id"]),
        )
        source = str(document["source"])
        chunks = await asyncio.to_thread(prepare_document, source, raw_content)
        if not chunks:
            skipped += 1
            continue

        result = await asyncio.to_thread(
            index_parsed_document,
            chunks,
            user_id=str(document["user_id"]),
            source_filename=source,
            doc_id=str(document["doc_id"]),
            content_hash_value=str(document["content_hash"]),
            uploaded_at=str(document.get("uploaded_at") or ""),
        )
        await collection.update_one(
            key,
            {
                "$set": {
                    "vector_index_status": "indexed",
                    "vector_content_hash": document["content_hash"],
                    "vector_indexed_at": datetime.now(timezone.utc).isoformat(),
                    "embedding_model": settings.gemini_embedding_model,
                    "chunks_created": int(result["chunks_created"]),
                }
            },
        )
        indexed += int(result["chunks_created"])
    return indexed, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user-id",
        help="Reindex only this user. Omit to process all users.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop and recreate the collection, then reindex all users.",
    )
    args = parser.parse_args()
    if args.rebuild and args.user_id:
        parser.error("--rebuild recreates the whole collection; omit --user-id.")
    return args


async def main() -> None:
    args = parse_args()
    database = get_database()
    try:
        if args.rebuild:
            await asyncio.to_thread(rebuild_vector_collection)
        await asyncio.to_thread(get_vector_store)
        transaction_count, transaction_skipped = await reindex_transactions(
            database,
            user_id=args.user_id,
        )
        document_chunks, document_skipped = await reindex_documents(
            database,
            user_id=args.user_id,
        )
        print(
            "Reindex complete: "
            f"transactions_indexed={transaction_count}, "
            f"transactions_skipped={transaction_skipped}, "
            f"document_chunks_indexed={document_chunks}, "
            f"documents_skipped={document_skipped}"
        )
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
