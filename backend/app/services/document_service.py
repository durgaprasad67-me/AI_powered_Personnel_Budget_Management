from pathlib import Path

from langchain_community.document_loaders import (
    CSVLoader,
    PyMuPDFLoader,
    TextLoader,
    Docx2txtLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.retrieval_service import add_documents


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
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[Document]:
    """Split documents into smaller chunks for retrieval."""
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
) -> dict[str, int | str]:
    """
    Load a document, split it into chunks, and index the chunks
    in ChromaDB.
    """
    documents = load_document(file_path)

    if not documents:
        return {
            "filename": Path(file_path).name,
            "chunks_created": 0,
        }

    chunks = split_documents(documents)

    if not chunks:
        return {
            "filename": Path(file_path).name,
            "chunks_created": 0,
        }

    add_documents(chunks)

    return {
        "filename": Path(file_path).name,
        "chunks_created": len(chunks),
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
    add_documents(chunks)

    return {
        "source": source,
        "chunks_created": len(chunks),
    }