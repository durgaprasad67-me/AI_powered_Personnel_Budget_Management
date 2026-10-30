from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.v1.endpoints import rag
from app.main import app

client = TestClient(app)


def test_ask_rag_returns_answer(monkeypatch):
    monkeypatch.setattr(
        rag, "answer_with_rag",
        AsyncMock(return_value={
            "question": "How can I reduce food spending?",
            "answer": "Review recurring food purchases.",
            "sources": ["budget-guide.txt"],
        }),
    )
    response = client.post(
        "/api/v1/ai/rag/ask",
        json={"question": "How can I reduce food spending?", "k": 3},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "Review recurring food purchases."
    assert response.json()["sources"] == ["budget-guide.txt"]

def test_ask_rag_rejects_short_question():
    response = client.post("/api/v1/ai/rag/ask", json={"question": "hi"})
    assert response.status_code == 422

def test_index_document_calls_indexer(monkeypatch):
    monkeypatch.setattr(
        rag, "index_document",
        lambda path, source_filename=None: {
            "filename": source_filename or path.name,
            "chunks_created": 2,
        },
    )
    response = client.post(
        "/api/v1/ai/rag/documents",
        files={"file": ("budget-guide.txt", b"Spend less than you earn.", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["chunks_created"] == 2

def test_index_document_rejects_unsupported_extension():
    response = client.post(
        "/api/v1/ai/rag/documents",
        files={"file": ("guide.exe", b"bad file", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_real_txt_upload_keeps_filename(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.services.rag.documents.add_documents",
        lambda chunks: captured.setdefault("chunks", chunks),
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
