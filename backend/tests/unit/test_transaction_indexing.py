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
