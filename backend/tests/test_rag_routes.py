from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.routes.v1 import rag

app = FastAPI()
app.include_router(rag.router)
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
    response = client.post("/ai/rag/ask", json={"question": "How can I reduce food spending?", "k": 3})
    assert response.status_code == 200
    assert response.json()["answer"] == "Review recurring food purchases."
    assert response.json()["sources"] == ["budget-guide.txt"]

def test_ask_rag_rejects_short_question():
    response = client.post("/ai/rag/ask", json={"question": "hi"})
    assert response.status_code == 422

def test_index_document_calls_indexer(monkeypatch):
    monkeypatch.setattr(
        rag, "index_document",
        lambda path: {"filename": path.name, "chunks_created": 2},
    )
    response = client.post(
        "/ai/rag/documents",
        files={"file": ("budget-guide.txt", b"Spend less than you earn.", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["chunks_created"] == 2

def test_index_document_rejects_unsupported_extension():
    response = client.post(
        "/ai/rag/documents",
        files={"file": ("guide.exe", b"bad file", "application/octet-stream")},
    )
    assert response.status_code == 415
