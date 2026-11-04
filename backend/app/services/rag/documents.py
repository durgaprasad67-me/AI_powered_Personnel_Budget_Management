import hashlib
from datetime import datetime, timezone
from pathlib import Path

from langchain_community.document_loaders import (
    CSVLoader,
    Docx2txtLoader,
    PyMuPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings
from app.integrations.vector_store import replace_documents

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".csv",
}

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10 MB


def load_document(file_path: str | Path) -> list[Document]:
    """Load a supported document into LangChain Document objects."""
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Document not found: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {path.suffix}. "
            f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if path.stat().st_size > MAX_DOCUMENT_SIZE:
        raise ValueError("Document exceeds the maximum size of 10 MB.")

    extension = path.suffix.lower()

    if extension == ".pdf":
        loader = PyMuPDFLoader(str(path))
    elif extension == ".docx":
        loader = Docx2txtLoader(str(path))
    elif extension == ".txt":
        loader = TextLoader(str(path), autodetect_encoding=True)
    else:
        loader = CSVLoader(str(path), autodetect_encoding=True)

    documents = loader.load()

    for document in documents:
        document.metadata["source"] = path.name
        document.metadata["file_type"] = extension.lstrip(".")

    return documents


def split_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Document]:
    """Split documents into smaller chunks for retrieval."""
    settings = get_settings()
    chunk_size = settings.rag_chunk_size if chunk_size is None else chunk_size
    chunk_overlap = (
        settings.rag_chunk_overlap if chunk_overlap is None else chunk_overlap
    )

    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero.")

    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be non-negative and smaller than chunk_size."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )

    return splitter.split_documents(documents)


def index_document(
    file_path: str | Path,
    source_filename: str | None = None,
    doc_id: str | None = None,
    uploaded_at: str | None = None,
) -> dict[str, int | str]:
    """
    Load a document, split it into chunks, and index the chunks
    in ChromaDB.
    """
    documents = load_document(file_path)
    if source_filename:
        for document in documents:
            document.metadata["source"] = source_filename

    if not documents:
        return {
            "filename": source_filename or Path(file_path).name,
            "chunks_created": 0,
        }

    chunks = split_documents(documents)

    if not chunks:
        return {
            "filename": source_filename or Path(file_path).name,
            "chunks_created": 0,
        }

    max_chunks = get_settings().rag_max_chunks
    if len(chunks) > max_chunks:
        raise ValueError(
            f"Document produces {len(chunks)} chunks, exceeding the "
            f"maximum allowed of {max_chunks}."
        )

    document_id = doc_id or hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
    timestamp = uploaded_at or datetime.now(timezone.utc).isoformat()
    embedding_model = get_settings().gemini_embedding_model
    for chunk_index, chunk in enumerate(chunks):
        chunk.metadata.update(
            {
                "doc_id": document_id,
                "source": source_filename or Path(file_path).name,
                "chunk_index": chunk_index,
                "uploaded_at": timestamp,
                "embedding_model": embedding_model,
            }
        )

    chunk_ids = replace_documents(document_id, chunks)

    return {
        "filename": source_filename or Path(file_path).name,
        "chunks_created": len(chunk_ids),
    }


def index_text(
    text: str,
    source: str = "manual_text",
) -> dict[str, int | str]:
    """Index plain text without creating a temporary file."""
    if not text.strip():
        raise ValueError("Text cannot be empty.")

    document = Document(
        page_content=text,
        metadata={
            "source": source,
            "file_type": "text",
        },
    )

    chunks = split_documents([document])
    max_chunks = get_settings().rag_max_chunks
    if len(chunks) > max_chunks:
        raise ValueError(
            f"Document produces {len(chunks)} chunks, exceeding the "
            f"maximum allowed of {max_chunks}."
        )

    document_id = hashlib.sha256(text.encode("utf-8")).hexdigest()
    timestamp = datetime.now(timezone.utc).isoformat()
    embedding_model = get_settings().gemini_embedding_model
    for chunk_index, chunk in enumerate(chunks):
        chunk.metadata.update(
            {
                "doc_id": document_id,
                "chunk_index": chunk_index,
                "uploaded_at": timestamp,
                "embedding_model": embedding_model,
            }
        )

    chunk_ids = replace_documents(document_id, chunks)

    return {
        "source": source,
        "chunks_created": len(chunk_ids),
    }
