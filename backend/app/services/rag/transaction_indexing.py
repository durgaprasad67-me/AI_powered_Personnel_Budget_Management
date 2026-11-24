from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any

from langchain_core.documents import Document

from app.core.config import get_settings
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.integrations.vector_store import (
    delete_transaction,
    delete_transactions_by_import_id,
    get_existing_content_hashes,
    mark_transaction_vector_stale,
    upsert_transaction_documents,
)

logger = logging.getLogger(__name__)


def build_transaction_text(transaction: dict[str, Any]) -> str:
    """Build a stable, human-readable retrieval record without calculations."""
    transaction_date = transaction.get("date", "unknown date")
    if isinstance(transaction_date, (date, datetime)):
        transaction_date = transaction_date.isoformat()

    merchant = str(
        transaction.get("merchant")
        or transaction.get("description")
        or "Unspecified merchant"
    ).strip()
    transaction_type = str(
        transaction.get("transaction_type") or transaction.get("type") or "unknown"
    ).strip()
    category = str(transaction.get("category") or "uncategorized").strip()
    amount = float(transaction.get("amount", 0))
    source_id = transaction.get("receipt_id", transaction.get("id", transaction.get("_id")))
    reference = f" {source_id}" if source_id is not None else ""
    text = (
        f"Transaction{reference} on {transaction_date}: {merchant}, "
        f"₹{amount:.2f} {transaction_type}, category {category}"
    )
    note = transaction.get("note")
    if note:
        text += f", note: {str(note).strip()}"
    return text


def transaction_text_hash(transaction: dict[str, Any]) -> str:
    return hashlib.sha256(build_transaction_text(transaction).encode("utf-8")).hexdigest()


def _transaction_document(
    transaction: dict[str, Any],
    user_id: str,
) -> tuple[Document, str, str]:
    source_id = transaction.get("id", transaction.get("_id"))
    if source_id is None:
        raise ValueError("Mongo transaction is missing its ID.")
    source_id = str(source_id)
    text = build_transaction_text(transaction)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    metadata = {
        "user_id": user_id,
        "source_type": "transaction",
        "source_id": source_id,
        "source": f"Transaction {source_id}",
        "chunk_index": 0,
        "date": transaction.get("date"),
        "amount": float(transaction.get("amount", 0)),
        "category": str(transaction.get("category") or "uncategorized"),
        "type": str(
            transaction.get("transaction_type") or transaction.get("type") or "unknown"
        ),
        "content_hash": content_hash,
        "embedding_model": get_settings().gemini_embedding_model,
    }
    if transaction.get("import_id"):
        metadata["import_id"] = str(transaction["import_id"])
    if transaction.get("fingerprint"):
        metadata["fingerprint"] = str(transaction["fingerprint"])
    return Document(page_content=text, metadata=metadata), content_hash, source_id


def index_transactions_sync(
    transactions: list[dict[str, Any]],
    user_id: str,
) -> list[tuple[str, str]]:
    """Upsert a batch of Mongo transactions into Chroma."""
    documents: list[Document] = []
    state: list[tuple[str, str]] = []
    content_hashes: list[str] = []
    for transaction in transactions:
        document, content_hash, source_id = _transaction_document(
            transaction,
            user_id,
        )
        documents.append(document)
        state.append((source_id, content_hash))
        content_hashes.append(content_hash)

    # Check for chunks whose content_hash is already indexed in Chroma
    existing_hashes = get_existing_content_hashes(user_id, content_hashes)
    docs_to_index = [
        doc for doc in documents
        if doc.metadata.get("content_hash") not in existing_hashes
    ]

    if docs_to_index:
        upsert_transaction_documents(docs_to_index, user_id=user_id)
    return state


async def sync_transactions_best_effort(
    transactions: list[dict[str, Any]],
    *,
    user_id: str = DEFAULT_CURRENT_USER_ID,
    repository: Any,
) -> bool:
    """Index after Mongo succeeds; failures leave sync state pending."""
    if not transactions:
        return True

    for transaction in transactions:
        transaction_id = transaction.get("id", transaction.get("_id"))
        if transaction_id is None:
            continue
        try:
            await asyncio.to_thread(
                mark_transaction_vector_stale,
                transaction_id,
                user_id,
            )
        except Exception as exc:
            logger.warning(
                "Could not mark the prior transaction vector stale",
                extra={"error_type": type(exc).__name__},
            )

    try:
        states = await asyncio.to_thread(
            index_transactions_sync,
            transactions,
            user_id,
        )
    except Exception as exc:
        logger.warning(
            "Transaction vector indexing failed; Mongo write was retained",
            extra={"error_type": type(exc).__name__},
        )
        # Batch rollback: delete individual transaction IDs and purge by import_id
        import_ids = {str(t["import_id"]) for t in transactions if t.get("import_id")}
        for imp_id in import_ids:
            try:
                await asyncio.to_thread(delete_transactions_by_import_id, imp_id, user_id)
            except Exception as cleanup_exc:
                logger.warning(
                    "Could not remove import batch vectors during rollback",
                    extra={"error_type": type(cleanup_exc).__name__},
                )
        for transaction in transactions:
            transaction_id = transaction.get("id", transaction.get("_id"))
            if transaction_id is None:
                continue
            try:
                await asyncio.to_thread(delete_transaction, transaction_id, user_id)
            except Exception as cleanup_exc:
                logger.warning(
                    "Could not remove a stale transaction vector",
                    extra={"error_type": type(cleanup_exc).__name__},
                )
        return False

    indexed_at = datetime.now(timezone.utc).isoformat()
    for source_id, content_hash in states:
        try:
            await repository.mark_vector_indexed(
                transaction_id=source_id,
                user_id=user_id,
                text_hash=content_hash,
                indexed_at=indexed_at,
            )
        except Exception as exc:
            logger.warning(
                "Transaction vector state update failed",
                extra={"error_type": type(exc).__name__},
            )
            return False
    return True


async def delete_transaction_best_effort(
    transaction_id: str | int,
    *,
    user_id: str = DEFAULT_CURRENT_USER_ID,
) -> bool:
    try:
        await asyncio.to_thread(
            mark_transaction_vector_stale,
            transaction_id,
            user_id,
        )
    except Exception as exc:
        logger.warning(
            "Could not mark the deleted transaction vector stale",
            extra={"error_type": type(exc).__name__},
        )

    try:
        return await asyncio.to_thread(delete_transaction, transaction_id, user_id)
    except Exception as exc:
        logger.warning(
            "Transaction vector deletion failed after Mongo delete",
            extra={"error_type": type(exc).__name__},
        )
        return False
