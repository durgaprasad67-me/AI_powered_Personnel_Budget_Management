import asyncio
import hashlib

from langchain_core.documents import Document

from app.integrations import vector_store
from app.services.rag import answering, documents


def test_index_document_sets_deterministic_metadata(tmp_path, monkeypatch):
    file_path = tmp_path / "guide.txt"
    content = b"Budget guidance " * 20
    file_path.write_bytes(content)
    captured = {}

    monkeypatch.setattr(
        documents,
        "load_document",
        lambda path: [
            Document(
                page_content="Budget guidance",
                metadata={"source": "guide.txt", "page": 2},
            )
        ],
    )
    monkeypatch.setattr(
        documents,
        "replace_documents",
        lambda doc_id, chunks: (
            captured.update(doc_id=doc_id, chunks=chunks),
            ["chunk-id"],
        )[1],
    )

    result = documents.index_document(file_path, "guide.txt")

    assert result["chunks_created"] == 1
    assert captured["doc_id"] == hashlib.sha256(content).hexdigest()
    assert captured["chunks"][0].metadata["doc_id"] == captured["doc_id"]
    assert captured["chunks"][0].metadata["source"] == "guide.txt"
    assert captured["chunks"][0].metadata["page"] == 2
    assert captured["chunks"][0].metadata["chunk_index"] == 0


def test_retrieve_documents_filters_below_minimum_score(monkeypatch):
    class FakeStore:
        async def asimilarity_search_with_relevance_scores(self, **kwargs):
            return [
                (Document(page_content="relevant"), 0.8),
                (Document(page_content="irrelevant"), 0.2),
            ]

    monkeypatch.setattr(vector_store, "get_vector_store", lambda: FakeStore())

    matches = asyncio.run(vector_store.retrieve_documents("question", k=2))

    assert [(document.page_content, score) for document, score in matches] == [
        ("relevant", 0.8)
    ]


def test_empty_store_does_not_call_llm(monkeypatch):
    async def no_matches(question, k):
        return []

    async def fail_if_called(**kwargs):
        raise AssertionError("LLM should not be called for an empty store")

    monkeypatch.setattr(answering, "retrieve_documents", no_matches)
    monkeypatch.setattr(answering, "generate_response", fail_if_called)

    result = asyncio.run(answering.answer_with_rag("question", k=2))

    assert result["answer"] == "I couldn't find that in your uploaded documents."
    assert result["sources"] == []
