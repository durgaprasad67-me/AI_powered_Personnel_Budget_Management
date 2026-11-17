import asyncio
import hashlib
import math
from datetime import date, datetime, timezone
from types import SimpleNamespace

import chromadb
import pytest
from langchain_core.documents import Document

from app.integrations import vector_store


class HashEmbeddings:
    def __init__(self, dimension=16):
        self.dimension = dimension

    def _embed(self, text):
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)

    async def aembed_query(self, text):
        return self._embed(text)


def setup_store(monkeypatch, tmp_path, *, configured_dim=16, embedding_dim=16):
    settings = SimpleNamespace(
        chroma_persist_directory=str(tmp_path),
        chroma_collection_name="test_rag",
        gemini_embedding_model="fake-embedding-v1",
        gemini_embedding_dim=configured_dim,
        rag_top_k=10,
        rag_min_score=0.0,
    )
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)
    monkeypatch.setattr(
        vector_store,
        "get_embedding_model",
        lambda: HashEmbeddings(embedding_dim),
    )
    monkeypatch.setattr(vector_store, "_vector_store", None)
    monkeypatch.setattr(vector_store, "_client", None)
    monkeypatch.setattr(vector_store, "_embedding_function", None)
    return settings


def make_document(text, *, doc_id="alice-guide", chunk_index=0, **metadata):
    return Document(
        page_content=text,
        metadata={
            "doc_id": doc_id,
            "chunk_index": chunk_index,
            "source": "guide.txt",
            **metadata,
        },
    )


def test_collection_is_created_with_cosine_and_expected_metadata(monkeypatch, tmp_path):
    setup_store(monkeypatch, tmp_path)

    store = vector_store.get_vector_store()

    assert store._collection.metadata == {
        "embedding_model": "fake-embedding-v1",
        "embedding_dim": 16,
        "distance": "cosine",
    }
    assert store._collection.configuration_json["hnsw"]["space"] == "cosine"


def test_probe_dimension_mismatch_has_rebuild_instruction(monkeypatch, tmp_path):
    setup_store(
        monkeypatch,
        tmp_path,
        configured_dim=16,
        embedding_dim=15,
    )

    with pytest.raises(RuntimeError, match="reindex_vectors.py --rebuild"):
        vector_store.get_vector_store()


def test_existing_collection_metadata_mismatch_is_rejected(monkeypatch, tmp_path):
    settings = setup_store(monkeypatch, tmp_path)
    client = chromadb.PersistentClient(path=str(tmp_path))
    client.create_collection(
        name=settings.chroma_collection_name,
        metadata={
            "embedding_model": "old-model",
            "embedding_dim": 16,
            "distance": "cosine",
        },
        configuration={"hnsw": {"space": "cosine"}},
    )

    with pytest.raises(RuntimeError, match="embedding_model.*reindex_vectors.py --rebuild"):
        vector_store.get_vector_store()


def test_document_upsert_is_idempotent_and_uses_deterministic_id(monkeypatch, tmp_path):
    setup_store(monkeypatch, tmp_path)
    document = make_document("Fresh Mart receipt 42.75", content_hash="hash-a")

    first_ids = vector_store.add_documents([document], user_id="alice")
    second_ids = vector_store.add_documents(
        [make_document("Fresh Mart receipt 42.75", content_hash="hash-a")],
        user_id="alice",
    )

    store = vector_store.get_vector_store()
    assert first_ids == second_ids == ["doc:alice:alice-guide:0"]
    assert store._collection.count() == 1


def test_transaction_upsert_is_idempotent_and_scoped_by_user(monkeypatch, tmp_path):
    setup_store(monkeypatch, tmp_path)
    transaction = Document(
        page_content="Transaction on 2026-06-12 Fresh Mart ₹42.75 expense",
        metadata={"source_id": "104", "source": "Transaction 104"},
    )

    first = vector_store.upsert_transaction_documents([transaction], "alice")
    second = vector_store.upsert_transaction_documents([transaction], "alice")
    vector_store.upsert_transaction_documents([transaction], "bob")

    store = vector_store.get_vector_store()
    assert first == second == ["txn:alice:104"]
    assert store._collection.count() == 2
    alice = store.get(ids=["txn:alice:104"], include=["metadatas"])
    assert alice["metadatas"][0]["user_id"] == "alice"
    assert alice["metadatas"][0]["source_type"] == "transaction"


def test_changed_document_upserts_then_removes_old_chunks(monkeypatch, tmp_path):
    setup_store(monkeypatch, tmp_path)
    vector_store.replace_documents(
        "alice-guide",
        [
            make_document("Old chunk one", chunk_index=0, content_hash="old"),
            make_document("Old chunk two", chunk_index=1, content_hash="old"),
        ],
        user_id="alice",
    )

    vector_store.replace_documents(
        "alice-guide",
        [make_document("New version only", chunk_index=0, content_hash="new")],
        user_id="alice",
    )

    records = vector_store.get_vector_store().get(
        where={"$and": [{"doc_id": "alice-guide"}, {"user_id": "alice"}]},
        include=["documents", "metadatas"],
    )
    assert records["ids"] == ["doc:alice:alice-guide:0"]
    assert records["documents"] == ["New version only"]
    assert records["metadatas"][0]["content_hash"] == "new"


def test_delete_document_removes_all_user_chunks(monkeypatch, tmp_path):
    setup_store(monkeypatch, tmp_path)
    vector_store.replace_documents(
        "guide",
        [make_document("first", doc_id="guide"), make_document("second", doc_id="guide", chunk_index=1)],
        user_id="alice",
    )

    assert vector_store.delete_document("guide", "alice") is True
    assert vector_store.get_vector_store()._collection.count() == 0


def test_retrieval_always_filters_by_user_and_supports_optional_filters(
    monkeypatch, tmp_path
):
    setup_store(monkeypatch, tmp_path)
    vector_store.replace_documents(
        "same-guide",
        [
            make_document(
                "private balance reference code", doc_id="same-guide",
                content_hash="alice", date="2026-06-12",
            )
        ],
        user_id="alice",
    )
    vector_store.replace_documents(
        "same-guide",
        [
            make_document(
                "private balance reference code", doc_id="same-guide",
                content_hash="bob", date="2026-06-12",
            )
        ],
        user_id="bob",
    )

    matches = asyncio.run(
        vector_store.retrieve_documents(
            "private balance reference code",
            k=5,
            user_id="alice",
            source_type="document",
            start_date=date(2026, 6, 1),
            end_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
    )

    assert len(matches) == 1
    assert matches[0][0].metadata["user_id"] == "alice"
    assert matches[0][0].metadata["chunk_id"] == "doc:alice:same-guide:0"


def test_stale_vectors_are_hidden_until_a_successful_upsert(monkeypatch, tmp_path):
    setup_store(monkeypatch, tmp_path)
    vector_store.upsert_transaction_documents(
        [
            Document(
                page_content="R-104 Fresh Mart 42.75 groceries",
                metadata={
                    "source_id": "R-104",
                    "source": "Transaction R-104",
                    "content_hash": "v1",
                },
            )
        ],
        user_id="alice",
    )
    assert vector_store.transaction_vector_is_current("R-104", "alice", "v1")

    assert vector_store.mark_transaction_vector_stale("R-104", "alice")
    hidden = asyncio.run(
        vector_store.retrieve_documents(
            "R-104 Fresh Mart 42.75 groceries",
            user_id="alice",
        )
    )
    assert hidden == []

    vector_store.upsert_transaction_documents(
        [
            Document(
                page_content="R-104 Fresh Mart 43.75 groceries",
                metadata={
                    "source_id": "R-104",
                    "source": "Transaction R-104",
                    "content_hash": "v2",
                },
            )
        ],
        user_id="alice",
    )
    assert vector_store.transaction_vector_is_current("R-104", "alice", "v2")


def test_stale_document_vectors_are_hidden_and_removed_on_replacement(
    monkeypatch,
    tmp_path,
):
    setup_store(monkeypatch, tmp_path)
    vector_store.replace_documents(
        "guide",
        [make_document("June grocery limit is 100", doc_id="guide", content_hash="v1")],
        user_id="alice",
    )
    assert vector_store.document_vectors_are_current("guide", "alice", "v1")
    assert vector_store.mark_document_vectors_stale("guide", "alice") == 1
    hidden = asyncio.run(
        vector_store.retrieve_documents("June grocery limit is 100", user_id="alice")
    )
    assert hidden == []

    vector_store.replace_documents(
        "guide",
        [make_document("June grocery limit is 125", doc_id="guide", content_hash="v2")],
        user_id="alice",
    )
    assert vector_store.document_vectors_are_current("guide", "alice", "v2")


def test_metadata_sanitization_drops_none_and_stores_date_epoch():
    metadata = vector_store.sanitize_metadata(
        {
            "user_id": "alice",
            "source": "receipt.pdf",
            "date": date(2026, 6, 12),
            "amount": 42.75,
            "category": "groceries",
            "optional": None,
            "complex": {"not": "scalar"},
        }
    )

    assert metadata["date"] == "2026-06-12"
    assert isinstance(metadata["date_epoch"], int)
    assert metadata["amount"] == 42.75
    assert "optional" not in metadata
    assert "complex" not in metadata


def test_cosine_distance_conversion_is_one_minus_distance():
    assert vector_store.cosine_distance_to_score(0.0) == 1.0
    assert vector_store.cosine_distance_to_score(0.25) == 0.75
    assert vector_store.cosine_distance_to_score(1.0) == 0.0
