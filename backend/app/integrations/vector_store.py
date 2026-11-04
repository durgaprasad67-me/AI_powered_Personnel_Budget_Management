from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import get_settings
from app.integrations.llm import get_embedding_model

_vector_store: Chroma | None = None


def get_vector_store() -> Chroma:
    """Initialize ChromaDB once and reuse the vector store."""
    global _vector_store

    if _vector_store is None:
        settings = get_settings()
        vector_db_path = Path(settings.chroma_persist_directory)
        vector_db_path.mkdir(parents=True, exist_ok=True)

        _vector_store = Chroma(
            collection_name=settings.chroma_collection_name,
            embedding_function=get_embedding_model(),
            persist_directory=str(vector_db_path),
        )

    return _vector_store


def add_documents(documents: list[Document]) -> list[str]:
    """Add document chunks and their embeddings to ChromaDB."""
    if not documents:
        return []

    vector_store = get_vector_store()

    return vector_store.add_documents(documents=documents)


def replace_documents(doc_id: str, documents: list[Document]) -> list[str]:
    """Replace all chunks for a document and return the new Chroma IDs."""
    vector_store = get_vector_store()
    existing = vector_store.get(where={"doc_id": doc_id})
    existing_ids = existing.get("ids", [])
    if existing_ids:
        vector_store.delete(ids=existing_ids)
    return vector_store.add_documents(documents=documents)


async def retrieve_documents(
    question: str,
    k: int | None = None,
) -> list[tuple[Document, float]]:
    """Retrieve the most relevant document chunks for a question."""
    if not question.strip():
        return []

    settings = get_settings()
    k = settings.rag_top_k if k is None else min(k, settings.rag_top_k)
    if k < 1 or k > 20:
        raise ValueError("k must be between 1 and 20.")

    vector_store = get_vector_store()

    matches = await vector_store.asimilarity_search_with_relevance_scores(
        query=question,
        k=k,
    )
    return [
        (document, score)
        for document, score in matches
        if score >= settings.rag_min_score
    ]


def delete_documents(document_ids: list[str]) -> None:
    """Delete indexed document chunks by their ChromaDB IDs."""
    if not document_ids:
        return

    get_vector_store().delete(ids=document_ids)
