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


async def retrieve_documents(
    question: str,
    k: int = 4,
) -> list[Document]:
    """Retrieve the most relevant document chunks for a question."""
    if not question.strip():
        return []

    if k < 1 or k > 20:
        raise ValueError("k must be between 1 and 20.")

    vector_store = get_vector_store()

    return await vector_store.asimilarity_search(
        query=question,
        k=k,
    )


def delete_documents(document_ids: list[str]) -> None:
    """Delete indexed document chunks by their ChromaDB IDs."""
    if not document_ids:
        return

    get_vector_store().delete(ids=document_ids)