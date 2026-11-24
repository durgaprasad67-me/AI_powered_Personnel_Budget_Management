import asyncio
from types import SimpleNamespace

from app.services.rag import transaction_indexing


def test_transaction_text_contains_retrieval_fields():
    text = transaction_indexing.build_transaction_text(
        {
            "date": "2026-06-12",
            "merchant": "Fresh Mart",
            "amount": 42.75,
            "transaction_type": "expense",
            "category": "Groceries",
            "note": "weekly shop",
        }
    )

    assert text == (
        "Transaction on 2026-06-12: Fresh Mart, ₹42.75 expense, "
        "category Groceries, note: weekly shop"
    )


def test_transaction_batch_uses_deterministic_metadata(monkeypatch):
    monkeypatch.setattr(
        transaction_indexing,
        "get_settings",
        lambda: SimpleNamespace(gemini_embedding_model="fake-model"),
    )
    captured = []
    monkeypatch.setattr(
        transaction_indexing,
        "upsert_transaction_documents",
        lambda documents, user_id: captured.append((documents, user_id)) or [
            f"txn:{user_id}:{document.metadata['source_id']}"
            for document in documents
        ],
    )
    transaction = {
        "id": 104,
        "date": "2026-06-12",
        "description": "Fresh Mart",
        "amount": 42.75,
        "transaction_type": "expense",
        "category": "Groceries",
    }

    first = transaction_indexing.index_transactions_sync([transaction], "alice")
    second = transaction_indexing.index_transactions_sync([transaction], "alice")

    assert first == second
    documents, user_id = captured[0]
    assert user_id == "alice"
    assert documents[0].metadata["source_type"] == "transaction"
    assert documents[0].metadata["source_id"] == "104"
    assert documents[0].metadata["embedding_model"] == "fake-model"
    assert transaction_indexing.transaction_text_hash(transaction) == first[0][1]


def test_embedding_failure_keeps_transaction_pending(monkeypatch):
    class Repository:
        indexed = []

        async def mark_vector_indexed(self, **kwargs):
            self.indexed.append(kwargs)
            return True

    repository = Repository()
    monkeypatch.setattr(transaction_indexing, "mark_transaction_vector_stale", lambda *args: False)
    monkeypatch.setattr(transaction_indexing, "delete_transaction", lambda *args: False)

    def fail(*args, **kwargs):
        raise RuntimeError("simulated embedding outage")

    monkeypatch.setattr(transaction_indexing, "index_transactions_sync", fail)
    succeeded = asyncio.run(
        transaction_indexing.sync_transactions_best_effort(
            [{"id": 104, "date": "2026-06-12", "amount": 42.75}],
            user_id="alice",
            repository=repository,
        )
    )

    assert succeeded is False
    assert repository.indexed == []


def test_delete_marks_vector_stale_before_best_effort_cleanup(monkeypatch):
    calls = []

    def mark_stale(transaction_id, user_id):
        calls.append(("stale", transaction_id, user_id))
        return True

    def fail_delete(transaction_id, user_id):
        calls.append(("delete", transaction_id, user_id))
        raise RuntimeError("simulated Chroma deletion failure")

    monkeypatch.setattr(
        transaction_indexing,
        "mark_transaction_vector_stale",
        mark_stale,
    )
    monkeypatch.setattr(transaction_indexing, "delete_transaction", fail_delete)

    result = asyncio.run(
        transaction_indexing.delete_transaction_best_effort(
            104,
            user_id="alice",
        )
    )

    assert result is False
    assert calls == [
        ("stale", 104, "alice"),
        ("delete", 104, "alice"),
    ]


def test_transaction_metadata_includes_import_id_and_fingerprint(monkeypatch):
    monkeypatch.setattr(
        transaction_indexing,
        "get_settings",
        lambda: SimpleNamespace(gemini_embedding_model="fake-model"),
    )
    transaction = {
        "id": 201,
        "date": "2026-07-01",
        "description": "Tech Store",
        "amount": 1500.0,
        "transaction_type": "expense",
        "category": "electronics",
        "import_id": "batch-uuid-123",
        "fingerprint": "fp-sha256-456",
    }
    doc, content_hash, source_id = transaction_indexing._transaction_document(transaction, "user-bob")
    assert source_id == "201"
    assert doc.metadata["import_id"] == "batch-uuid-123"
    assert doc.metadata["fingerprint"] == "fp-sha256-456"
    assert doc.metadata["source_type"] == "transaction"
    assert doc.metadata["user_id"] == "user-bob"


def test_index_transactions_skips_existing_content_hash(monkeypatch):
    monkeypatch.setattr(
        transaction_indexing,
        "get_settings",
        lambda: SimpleNamespace(gemini_embedding_model="fake-model"),
    )
    t1 = {
        "id": 1,
        "date": "2026-07-01",
        "description": "Item 1",
        "amount": 10.0,
        "transaction_type": "expense",
        "category": "food",
    }
    t2 = {
        "id": 2,
        "date": "2026-07-02",
        "description": "Item 2",
        "amount": 20.0,
        "transaction_type": "expense",
        "category": "food",
    }
    h1 = transaction_indexing.transaction_text_hash(t1)

    # Simulate t1 content_hash already existing in Chroma
    monkeypatch.setattr(
        transaction_indexing,
        "get_existing_content_hashes",
        lambda user_id, hashes: {h1},
    )

    captured_docs = []
    monkeypatch.setattr(
        transaction_indexing,
        "upsert_transaction_documents",
        lambda docs, user_id: captured_docs.extend(docs) or ["id2"],
    )

    states = transaction_indexing.index_transactions_sync([t1, t2], "user-bob")
    assert len(states) == 2  # State returns both so Mongo updates status
    assert len(captured_docs) == 1  # Only t2 was sent to Chroma
    assert captured_docs[0].metadata["source_id"] == "2"


def test_index_transactions_all_existing_makes_zero_vector_calls(monkeypatch):
    monkeypatch.setattr(
        transaction_indexing,
        "get_settings",
        lambda: SimpleNamespace(gemini_embedding_model="fake-model"),
    )
    t1 = {
        "id": 1,
        "date": "2026-07-01",
        "description": "Item 1",
        "amount": 10.0,
        "transaction_type": "expense",
        "category": "food",
    }
    h1 = transaction_indexing.transaction_text_hash(t1)

    monkeypatch.setattr(
        transaction_indexing,
        "get_existing_content_hashes",
        lambda user_id, hashes: {h1},
    )

    called = []
    monkeypatch.setattr(
        transaction_indexing,
        "upsert_transaction_documents",
        lambda docs, user_id: called.append(docs),
    )

    states = transaction_indexing.index_transactions_sync([t1], "user-bob")
    assert len(states) == 1
    assert len(called) == 0  # Zero calls to upsert


def test_sync_transactions_rollback_on_failure(monkeypatch):
    class Repository:
        async def mark_vector_indexed(self, **kwargs):
            return True

    cleanups = []
    monkeypatch.setattr(transaction_indexing, "mark_transaction_vector_stale", lambda *a: True)
    monkeypatch.setattr(
        transaction_indexing,
        "delete_transactions_by_import_id",
        lambda imp_id, uid: cleanups.append(("import_id", imp_id, uid)) or 1,
    )
    monkeypatch.setattr(
        transaction_indexing,
        "delete_transaction",
        lambda tid, uid: cleanups.append(("txn", tid, uid)) or True,
    )

    def fail_index(*args, **kwargs):
        raise RuntimeError("simulated Chroma outage")

    monkeypatch.setattr(transaction_indexing, "index_transactions_sync", fail_index)

    txs = [
        {"id": 101, "date": "2026-07-01", "amount": 50.0, "import_id": "batch-99"},
        {"id": 102, "date": "2026-07-02", "amount": 60.0, "import_id": "batch-99"},
    ]
    succeeded = asyncio.run(
        transaction_indexing.sync_transactions_best_effort(
            txs,
            user_id="user-bob",
            repository=Repository(),
        )
    )
    assert succeeded is False
    assert ("import_id", "batch-99", "user-bob") in cleanups
    assert ("txn", 101, "user-bob") in cleanups
    assert ("txn", 102, "user-bob") in cleanups
