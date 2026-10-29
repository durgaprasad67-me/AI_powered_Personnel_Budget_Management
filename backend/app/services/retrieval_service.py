import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pydantic import SecretStr

load_dotenv()

VECTOR_DB_PATH = Path(
    os.getenv("CHROMA_PERSIST_DIRECTORY", "./chroma_db")
)

COLLECTION_NAME = os.getenv(
    "CHROMA_COLLECTION_NAME",
    "finsight_knowledge",
)

_vector_store: Chroma | None = None


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Create the embedding model used for document retrieval."""
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from the environment.")

    return GoogleGenerativeAIEmbeddings(
        model=os.getenv(
            "GEMINI_EMBEDDING_MODEL",
            "gemini-embedding-001",
        ),
        api_key=SecretStr(api_key),
    )


def get_vector_store() -> Chroma:
    """Initialize ChromaDB once and reuse the vector store."""
    global _vector_store

    if _vector_store is None:
        VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)

        _vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embeddings(),
            persist_directory=str(VECTOR_DB_PATH),
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