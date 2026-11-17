from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from datetime import date, datetime, time, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import get_settings
from app.integrations.llm import get_embedding_model

logger = logging.getLogger(__name__)

_vector_store: Chroma | None = None
_client: chromadb.ClientAPI | None = None
_embedding_function: Any | None = None
_vector_store_lock = threading.RLock()

REBUILD_HINT = (
    "The Chroma collection does not match the configured embedding model, "
    "dimension, or distance metric. Run "
    "'python scripts/reindex_vectors.py --rebuild' from backend and retry."
)
_PROBE_TEXT = "FinSight Chroma embedding configuration probe"


def cosine_distance_to_score(distance: float) -> float:
    """Chroma cosine distance is 1 - cosine similarity."""
    return 1.0 - float(distance)


def _validate_user_id(user_id: str) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id is required.")
    return user_id.strip()


def _date_metadata(value: Any) -> tuple[str, int] | None:
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(raw), time.min)
            except ValueError:
                return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    normalized = parsed.astimezone(timezone.utc)
    iso_value = (
        normalized.date().isoformat()
        if normalized.time() == time.min
        else normalized.isoformat()
    )
    return iso_value, int(normalized.timestamp())


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Keep only scalar Chroma metadata and normalize date fields."""
    safe: dict[str, str | int | float | bool] = {}

    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, Enum):
            value = value.value
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            safe[key] = value.astimezone(timezone.utc).isoformat()
        elif isinstance(value, date):
            safe[key] = value.isoformat()
        elif isinstance(value, (str, int, float, bool)):
            safe[key] = value
        elif value.__class__.__name__ == "ObjectId":
            safe[key] = str(value)

    if "date" in metadata:
        normalized_date = _date_metadata(metadata["date"])
        if normalized_date is not None:
            safe["date"], safe["date_epoch"] = normalized_date

    return safe


def _expected_collection_metadata() -> dict[str, str | int]:
    settings = get_settings()
    return {
        "embedding_model": settings.gemini_embedding_model,
        "embedding_dim": settings.gemini_embedding_dim,
        "distance": "cosine",
    }


def _configuration_space(collection: Any) -> str | None:
    # Chroma 1.5 exposes the raw configuration without parsing its legacy
    # embedding-function entry (which emits a deprecation warning).
    configuration = getattr(collection, "configuration_json", None) or {}
    hnsw = configuration.get("hnsw") or {}
    if isinstance(hnsw, dict):
        return hnsw.get("space")
    return None


def _validate_collection(
    store: Chroma,
    embedding_function: Any,
    expected: dict[str, str | int],
) -> None:
    probe = embedding_function.embed_query(_PROBE_TEXT)
    expected_dim = int(expected["embedding_dim"])
    if len(probe) != expected_dim:
        raise RuntimeError(
            f"Gemini probe returned {len(probe)} dimensions; expected "
            f"{expected_dim}. {REBUILD_HINT}"
        )

    collection = store._collection
    actual_metadata = collection.metadata or {}
    mismatches = {
        key: (actual_metadata.get(key), value)
        for key, value in expected.items()
        if actual_metadata.get(key) != value
    }
    actual_space = _configuration_space(collection)
    if actual_space != "cosine":
        mismatches["collection_configuration.hnsw.space"] = (
            actual_space,
            "cosine",
        )

    try:
        stored = collection.get(limit=1, include=["embeddings"])
        stored_embeddings = stored.get("embeddings")
        if stored_embeddings is not None and len(stored_embeddings):
            stored_dim = len(stored_embeddings[0])
            if stored_dim != expected_dim:
                mismatches["stored_vector_dimension"] = (
                    stored_dim,
                    expected_dim,
                )
    except Exception as exc:
        raise RuntimeError(
            f"Could not validate stored Chroma vectors. {REBUILD_HINT}"
        ) from exc

    if mismatches:
        detail = ", ".join(
            f"{key}: found {actual!r}, expected {wanted!r}"
            for key, (actual, wanted) in mismatches.items()
        )
        raise RuntimeError(f"{detail}. {REBUILD_HINT}")


def get_vector_store() -> Chroma:
    """Initialize and validate the persistent Chroma collection on first use."""
    global _vector_store, _client, _embedding_function

    if _vector_store is not None:
        return _vector_store

    with _vector_store_lock:
        if _vector_store is not None:
            return _vector_store

        settings = get_settings()
        persist_directory = Path(settings.chroma_persist_directory)
        persist_directory.mkdir(parents=True, exist_ok=True)

        client = chromadb.PersistentClient(path=str(persist_directory))
        embeddings = get_embedding_model()
        expected = _expected_collection_metadata()
        store = Chroma(
            client=client,
            collection_name=settings.chroma_collection_name,
            embedding_function=embeddings,
            collection_metadata=expected,
            collection_configuration={"hnsw": {"space": "cosine"}},
            relevance_score_fn=cosine_distance_to_score,
        )
        _validate_collection(store, embeddings, expected)

        _client = client
        _embedding_function = embeddings
        _vector_store = store
        return store


def _raw_collection():
    """Open the configured collection without embedding or probe calls."""
    global _client
    settings = get_settings()
    with _vector_store_lock:
        client = _client
        if client is None:
            persist_directory = Path(settings.chroma_persist_directory)
            persist_directory.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(persist_directory))
            _client = client
        try:
            return client.get_collection(name=settings.chroma_collection_name)
        except chromadb.errors.NotFoundError:
            return None


def mark_transaction_vector_stale(
    transaction_id: str | int,
    user_id: str,
) -> bool:
    chunk_id = f"txn:{_validate_user_id(user_id)}:{transaction_id}"
    collection = _raw_collection()
    if collection is None:
        return False
    result = collection.get(ids=[chunk_id], include=["metadatas"])
    metadata_list = result.get("metadatas", [])
    if not result.get("ids") or not metadata_list or not metadata_list[0]:
        return False
    metadata = metadata_list[0]
    if metadata.get("user_id") != user_id or metadata.get("source_type") != "transaction":
        return False
    metadata["vector_state"] = "stale"
    collection.update(ids=[chunk_id], metadatas=[sanitize_metadata(metadata)])
    return True


def mark_document_vectors_stale(doc_id: str, user_id: str) -> int:
    user_id = _validate_user_id(user_id)
    collection = _raw_collection()
    if collection is None:
        return 0
    result = collection.get(
        where={"$and": [{"doc_id": doc_id}, {"user_id": user_id}]},
        include=["metadatas"],
    )
    ids: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for chunk_id, metadata in zip(result.get("ids", []), result.get("metadatas", [])):
        if not metadata or metadata.get("source_type", "document") != "document":
            continue
        safe = dict(metadata)
        safe["vector_state"] = "stale"
        ids.append(chunk_id)
        metadatas.append(sanitize_metadata(safe))
    if ids:
        collection.update(ids=ids, metadatas=metadatas)
    return len(ids)


def transaction_vector_is_current(
    transaction_id: str | int,
    user_id: str,
    content_hash: str,
) -> bool:
    chunk_id = f"txn:{_validate_user_id(user_id)}:{transaction_id}"
    collection = _raw_collection()
    if collection is None:
        return False
    result = collection.get(ids=[chunk_id], include=["metadatas"])
    metadata_list = result.get("metadatas", [])
    return bool(
        metadata_list
        and metadata_list[0]
        and metadata_list[0].get("user_id") == user_id
        and metadata_list[0].get("source_type") == "transaction"
        and metadata_list[0].get("vector_state") == "indexed"
        and metadata_list[0].get("content_hash") == content_hash
    )


def document_vectors_are_current(
    doc_id: str,
    user_id: str,
    content_hash: str,
) -> bool:
    user_id = _validate_user_id(user_id)
    collection = _raw_collection()
    if collection is None:
        return False
    result = collection.get(
        where={"$and": [{"doc_id": doc_id}, {"user_id": user_id}]},
        include=["metadatas"],
    )
    metadatas = result.get("metadatas", [])
    return bool(metadatas) and all(
        metadata
        and metadata.get("source_type", "document") == "document"
        and metadata.get("vector_state") == "indexed"
        and metadata.get("content_hash") == content_hash
        for metadata in metadatas
    )


def _document_identity(document: Document, user_id: str, index: int) -> str:
    metadata = document.metadata
    source_type = metadata.get("source_type", "document")
    if source_type == "transaction":
        source_id = metadata.get("source_id")
        if source_id is None:
            raise ValueError("Transaction vectors require source_id metadata.")
        return f"txn:{user_id}:{source_id}"

    doc_id = metadata.get("doc_id")
    if not doc_id:
        digest = hashlib.sha256(
            (
                str(metadata.get("source", "document"))
                + "\n"
                + document.page_content
            ).encode("utf-8")
        ).hexdigest()
        doc_id = digest
        metadata["doc_id"] = doc_id
    chunk_index = metadata.get("chunk_index", index)
    return f"doc:{user_id}:{doc_id}:{chunk_index}"


def _prepare_documents(
    documents: Iterable[Document],
    *,
    user_id: str,
    source_type: str,
) -> tuple[list[Document], list[str]]:
    user_id = _validate_user_id(user_id)
    prepared: list[Document] = []
    ids: list[str] = []

    for index, document in enumerate(documents):
        metadata = dict(document.metadata or {})
        metadata["user_id"] = user_id
        metadata["source_type"] = metadata.get("source_type", source_type)
        metadata["vector_state"] = "indexed"
        if metadata["source_type"] != source_type:
            raise ValueError(
                f"Expected source_type={source_type!r}, "
                f"got {metadata['source_type']!r}."
            )
        if source_type == "document":
            metadata.setdefault("chunk_index", index)
        safe_metadata = sanitize_metadata(metadata)
        safe_document = Document(
            page_content=document.page_content,
            metadata=safe_metadata,
        )
        ids.append(_document_identity(safe_document, user_id, index))
        prepared.append(safe_document)

    return prepared, ids


def add_documents(documents: list[Document], user_id: str) -> list[str]:
    """Deterministically upsert document chunks for one user."""
    if not documents:
        return []
    prepared, ids = _prepare_documents(
        documents,
        user_id=user_id,
        source_type="document",
    )
    get_vector_store().add_documents(documents=prepared, ids=ids)
    return ids


def upsert_transaction_documents(
    documents: list[Document],
    user_id: str,
) -> list[str]:
    """Deterministically upsert transaction vectors for one user."""
    if not documents:
        return []
    prepared, ids = _prepare_documents(
        documents,
        user_id=user_id,
        source_type="transaction",
    )
    get_vector_store().add_documents(documents=prepared, ids=ids)
    return ids


def replace_documents(
    doc_id: str,
    documents: list[Document],
    user_id: str,
) -> list[str]:
    """Upsert a document version first, then remove stale version chunks."""
    user_id = _validate_user_id(user_id)
    if not doc_id.strip():
        raise ValueError("doc_id cannot be empty.")

    if not documents:
        delete_document(doc_id, user_id)
        return []

    content_hash = next(
        (
            str(document.metadata["content_hash"])
            for document in documents
            if document.metadata.get("content_hash")
        ),
        None,
    )
    if content_hash is None:
        content_hash = hashlib.sha256(
            "\n".join(document.page_content for document in documents).encode(
                "utf-8"
            )
        ).hexdigest()

    for index, document in enumerate(documents):
        document.metadata.update(
            {
                "doc_id": doc_id,
                "content_hash": content_hash,
                "chunk_index": document.metadata.get("chunk_index", index),
                "source_type": "document",
            }
        )

    prepared, ids = _prepare_documents(
        documents,
        user_id=user_id,
        source_type="document",
    )
    store = get_vector_store()

    # Chroma.add_documents uses upsert in the installed langchain-chroma.
    store.add_documents(documents=prepared, ids=ids)

    old = store.get(
        where={
            "$and": [
                {"doc_id": doc_id},
                {"user_id": user_id},
            ]
        },
        include=["metadatas"],
    )
    stale_ids = [
        chunk_id
        for chunk_id, metadata in zip(old.get("ids", []), old.get("metadatas", []))
        if metadata
        and metadata.get("source_type", "document") == "document"
        and metadata.get("content_hash") != content_hash
    ]
    if stale_ids:
        store.delete(ids=stale_ids)
    return ids


def _date_epoch_filter(value: date | datetime | str, *, end: bool) -> int:
    normalized = _date_metadata(value)
    if normalized is None:
        raise ValueError(f"Invalid date filter: {value!r}")
    iso_value, epoch = normalized
    # A date-only end filter should include the entire day.
    if end and len(iso_value) == 10:
        epoch += 24 * 60 * 60 - 1
    return epoch


def _build_where(
    *,
    user_id: str,
    source_type: str | None,
    start_date: date | datetime | str | None,
    end_date: date | datetime | str | None,
) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = [{"user_id": _validate_user_id(user_id)}]
    if source_type:
        if source_type not in {"document", "transaction"}:
            raise ValueError("source_type must be 'document' or 'transaction'.")
        clauses.append({"source_type": source_type})

    clauses.append({"vector_state": "indexed"})

    if start_date is not None:
        clauses.append(
            {"date_epoch": {"$gte": _date_epoch_filter(start_date, end=False)}}
        )
    if end_date is not None:
        clauses.append(
            {"date_epoch": {"$lte": _date_epoch_filter(end_date, end=True)}}
        )

    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


async def retrieve_documents(
    question: str,
    k: int | None = None,
    *,
    user_id: str,
    source_type: str | None = None,
    start_date: date | datetime | str | None = None,
    end_date: date | datetime | str | None = None,
    threshold: float | None = None,
    include_below_threshold: bool = False,
) -> list[tuple[Document, float]]:
    """Retrieve top-k chunks with mandatory user and optional metadata filters.

    ``include_below_threshold`` is used by the answer service to log every
    candidate before applying the configured relevance cutoff.
    """
    if not question.strip():
        return []

    settings = get_settings()
    requested_k = settings.rag_top_k if k is None else k
    if requested_k < 1 or requested_k > 20:
        raise ValueError("k must be between 1 and 20.")
    top_k = min(requested_k, settings.rag_top_k)
    minimum_score = settings.rag_min_score if threshold is None else threshold
    if not 0.0 <= minimum_score <= 1.0:
        raise ValueError("threshold must be between 0 and 1.")

    # Collection creation validates a probe embedding synchronously. Keep that
    # first-use network call off the event loop used by FastAPI requests.
    store = await asyncio.to_thread(get_vector_store)
    where = _build_where(
        user_id=user_id,
        source_type=source_type,
        start_date=start_date,
        end_date=end_date,
    )
    collection = getattr(store, "_collection", None)

    if collection is None:
        matches = await store.asimilarity_search_with_relevance_scores(
            query=question,
            k=top_k,
            filter=where,
        )
        return [
            (document, float(score))
            for document, score in matches
            if include_below_threshold or float(score) >= minimum_score
        ]

    embedding_function = getattr(store, "_embedding_function", None)
    if embedding_function is None:
        embedding_function = _embedding_function or get_embedding_model()
    query_vector = await embedding_function.aembed_query(question)
    result = await asyncio.to_thread(
        collection.query,
        query_embeddings=[query_vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    ids = (result.get("ids") or [[]])[0]
    texts = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    matches: list[tuple[Document, float]] = []
    for chunk_id, text, metadata, distance in zip(ids, texts, metadatas, distances):
        score = cosine_distance_to_score(float(distance))
        if not include_below_threshold and score < minimum_score:
            continue
        safe_metadata = sanitize_metadata(metadata or {})
        safe_metadata["chunk_id"] = str(chunk_id)
        matches.append((Document(page_content=text or "", metadata=safe_metadata), score))
    return matches


def list_documents(user_id: str) -> list[dict[str, str | int]]:
    user_id = _validate_user_id(user_id)
    records = get_vector_store().get(
        where={"user_id": user_id},
        include=["metadatas"],
    )
    grouped: dict[str, dict[str, str | int]] = {}
    for metadata in records.get("metadatas", []):
        if not metadata or metadata.get("source_type", "document") != "document":
            continue
        if not metadata.get("doc_id"):
            continue
        doc_id = str(metadata["doc_id"])
        if doc_id not in grouped:
            grouped[doc_id] = {
                "doc_id": doc_id,
                "source": str(metadata.get("source", "Knowledge base")),
                "chunk_count": 0,
            }
        grouped[doc_id]["chunk_count"] = int(grouped[doc_id]["chunk_count"]) + 1
    return list(grouped.values())


def delete_document(doc_id: str, user_id: str) -> bool:
    user_id = _validate_user_id(user_id)
    if not doc_id.strip():
        raise ValueError("doc_id cannot be empty.")
    collection = _raw_collection()
    if collection is None:
        return False
    records = collection.get(
        where={
            "$and": [
                {"doc_id": doc_id},
                {"user_id": user_id},
            ]
        },
        include=["metadatas"],
    )
    ids = [
        chunk_id
        for chunk_id, metadata in zip(
            records.get("ids", []), records.get("metadatas", [])
        )
        if metadata and metadata.get("source_type", "document") == "document"
    ]
    if not ids:
        return False
    collection.delete(ids=ids)
    return True


def delete_transaction(transaction_id: str | int, user_id: str) -> bool:
    user_id = _validate_user_id(user_id)
    chunk_id = f"txn:{user_id}:{transaction_id}"
    collection = _raw_collection()
    if collection is None:
        return False
    existing = collection.get(ids=[chunk_id], include=["metadatas"])
    metadata = (existing.get("metadatas") or [None])[0]
    if (
        not existing.get("ids")
        or not metadata
        or metadata.get("user_id") != user_id
        or metadata.get("source_type") != "transaction"
    ):
        return False
    collection.delete(ids=[chunk_id])
    return True


def delete_documents(document_ids: list[str]) -> None:
    """Delete trusted internal Chroma IDs, for scripts and maintenance only."""
    if document_ids:
        get_vector_store().delete(ids=document_ids)


def get_collection_metadata() -> dict[str, Any]:
    return dict(get_vector_store()._collection.metadata or {})


def count_vectors_by_source_type() -> dict[str, int]:
    records = get_vector_store().get(include=["metadatas"])
    counts: dict[str, int] = {}
    for metadata in records.get("metadatas", []):
        source_type = str((metadata or {}).get("source_type", "unknown"))
        counts[source_type] = counts.get(source_type, 0) + 1
    return counts


def rebuild_vector_collection() -> None:
    """Delete only the configured Chroma collection; recreate it on next use."""
    global _vector_store, _client, _embedding_function
    with _vector_store_lock:
        settings = get_settings()
        persist_directory = Path(settings.chroma_persist_directory)
        persist_directory.mkdir(parents=True, exist_ok=True)
        client = _client or chromadb.PersistentClient(path=str(persist_directory))
        try:
            client.delete_collection(name=settings.chroma_collection_name)
        except chromadb.errors.NotFoundError:
            pass
        _client = client
        _vector_store = None
        _embedding_function = None
