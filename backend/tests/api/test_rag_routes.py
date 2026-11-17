from unittest.mock import AsyncMock

from app.api.deps import get_current_user_id
from app.main import app


def test_ask_rag_returns_answer(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.answer_with_rag",
        AsyncMock(
            return_value={
                "question": "How can I reduce food spending?",
                "answer": "Review recurring food purchases.",
                "sources": ["budget-guide.txt"],
            }
        ),
    )
    response = client.post(
        "/api/v1/ai/rag/ask",
        json={"question": "How can I reduce food spending?", "k": 3},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "Review recurring food purchases."
    assert response.json()["sources"] == ["budget-guide.txt"]


def test_ask_rag_rejects_short_question(client):
    response = client.post("/api/v1/ai/rag/ask", json={"question": "hi"})
    assert response.status_code == 422


def test_rag_route_uses_dependency_user_and_rejects_body_user_id(
    client,
    monkeypatch,
    overrides,
):
    app.dependency_overrides[get_current_user_id] = lambda: "alice"
    calls = []

    async def answer_stub(**kwargs):
        calls.append(kwargs)
        return {
            "question": kwargs["question"],
            "answer": "Alice's document says yes.",
            "sources": [],
            "source_chunks": [],
        }

    monkeypatch.setattr("app.api.v1.endpoints.rag.answer_with_rag", answer_stub)
    forbidden = client.post(
        "/api/v1/ai/rag/ask",
        json={"question": "Read Bob's private data", "user_id": "bob"},
    )
    allowed = client.post(
        "/api/v1/ai/rag/ask",
        json={
            "question": "What does my document say?",
            "k": 2,
            "source_type": "document",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        },
    )

    assert forbidden.status_code == 422
    assert allowed.status_code == 200
    assert calls[0]["user_id"] == "alice"
    assert calls[0]["source_type"] == "document"
    assert calls[0]["start_date"].isoformat() == "2026-06-01"


def test_rag_route_never_uses_a_body_user_to_select_sources(
    client,
    monkeypatch,
    overrides,
):
    current_user = {"id": "alice"}
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    corpus = {
        "alice": "Alice's own note.",
        "bob": "Bob's private balance.",
    }

    async def answer_stub(*, question, user_id, **kwargs):
        return {
            "question": question,
            "answer": corpus[user_id],
            "sources": [f"{user_id}.txt"],
            "source_chunks": [],
        }

    monkeypatch.setattr("app.api.v1.endpoints.rag.answer_with_rag", answer_stub)
    alice = client.post(
        "/api/v1/ai/rag/ask",
        json={"question": "What does my note say?", "user_id": "bob"},
    )
    assert alice.status_code == 422

    alice = client.post(
        "/api/v1/ai/rag/ask",
        json={"question": "What does my note say?"},
    )
    current_user["id"] = "bob"
    bob = client.post(
        "/api/v1/ai/rag/ask",
        json={"question": "What is my balance?"},
    )

    assert alice.status_code == bob.status_code == 200
    assert alice.json()["answer"] == "Alice's own note."
    assert alice.json()["sources"] == ["alice.txt"]
    assert bob.json()["answer"] == "Bob's private balance."
    assert bob.json()["sources"] == ["bob.txt"]


def test_index_document_calls_indexer(client, monkeypatch, overrides):
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.index_parsed_document",
        lambda chunks, **kwargs: {
            "filename": kwargs["source_filename"],
            "chunks_created": 2,
        },
    )
    response = client.post(
        "/api/v1/ai/rag/documents",
        files={
            "file": ("budget-guide.txt", b"Spend less than you earn.", "text/plain")
        },
    )
    assert response.status_code == 201
    assert response.json()["chunks_created"] == 2


def test_index_document_rejects_unsupported_extension(client):
    response = client.post(
        "/api/v1/ai/rag/documents",
        files={"file": ("guide.exe", b"bad file", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_real_txt_upload_keeps_filename(client, monkeypatch, overrides):
    captured = {}
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.index_parsed_document",
        lambda chunks, **kwargs: captured.update(chunks=chunks)
        or {"filename": kwargs["source_filename"], "chunks_created": len(chunks)},
    )
    response = client.post(
        "/api/v1/ai/rag/documents",
        files={
            "file": (
                "budget-guide.txt",
                b"Spend less than you earn. " * 40,
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    assert response.json()["filename"] == "budget-guide.txt"
    assert {chunk.metadata["source"] for chunk in captured["chunks"]} == {
        "budget-guide.txt"
    }


def test_reupload_changed_content_uses_same_document_identity(
    client,
    monkeypatch,
    overrides,
):
    calls = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.index_parsed_document",
        lambda chunks, **kwargs: calls.append((chunks, kwargs)) or {
            "chunks_created": 1
        },
    )

    for content in (b"same.txt version one", b"same.txt version two"):
        response = client.post(
            "/api/v1/ai/rag/documents",
            files={"file": ("same.txt", content, "text/plain")},
        )
        assert response.status_code == 201

    assert calls[0][1]["doc_id"] == calls[1][1]["doc_id"]
    assert calls[0][1]["content_hash_value"] != calls[1][1]["content_hash_value"]


def test_list_and_delete_rag_documents(client, monkeypatch, overrides):
    repository = overrides["rag_documents"]
    repository.documents[("default_dashboard_user", "guide.txt")] = {
        "user_id": "default_dashboard_user",
        "normalized_filename": "guide.txt",
        "doc_id": "doc-1",
        "source": "guide.txt",
        "content_hash": "hash",
        "uploaded_at": "2026-11-11T00:00:00+00:00",
        "vector_index_status": "indexed",
        "chunks_created": 2,
    }
    deleted = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.delete_document",
        lambda doc_id, user_id: deleted.append((doc_id, user_id)) or True,
    )

    listed = client.get("/api/v1/ai/rag/documents")
    response = client.delete("/api/v1/ai/rag/documents/doc-1")

    assert listed.status_code == 200
    assert listed.json() == [
        {
            "doc_id": "doc-1",
            "source": "guide.txt",
            "chunk_count": 2,
            "vector_index_status": "indexed",
        }
    ]
    assert response.status_code == 204
    assert deleted == [("doc-1", "default_dashboard_user")]
