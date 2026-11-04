from unittest.mock import AsyncMock


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


def test_index_document_calls_indexer(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.index_document",
        lambda path, source_filename=None, doc_id=None, uploaded_at=None: {
            "filename": source_filename or path.name,
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


def test_real_txt_upload_keeps_filename(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.services.rag.documents.replace_documents",
        lambda doc_id, chunks: (
            captured.setdefault("chunks", chunks),
            [f"chunk-{index}" for index, _ in enumerate(chunks)],
        )[1],
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


def test_reupload_uses_same_document_hash(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.index_document",
        lambda *args: calls.append(args) or {"chunks_created": 1},
    )

    for _ in range(2):
        response = client.post(
            "/api/v1/ai/rag/documents",
            files={"file": ("same.txt", b"same content", "text/plain")},
        )
        assert response.status_code == 201

    assert calls[0][2] == calls[1][2]


def test_list_and_delete_rag_documents(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.list_documents",
        lambda: [
            {
                "doc_id": "doc-1",
                "source": "guide.txt",
                "chunk_count": 2,
            }
        ],
    )
    deleted = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.delete_document",
        lambda doc_id: deleted.append(doc_id) or True,
    )

    listed = client.get("/api/v1/ai/rag/documents")
    response = client.delete("/api/v1/ai/rag/documents/doc-1")

    assert listed.status_code == 200
    assert listed.json() == [
        {"doc_id": "doc-1", "source": "guide.txt", "chunk_count": 2}
    ]
    assert response.status_code == 204
    assert deleted == ["doc-1"]
