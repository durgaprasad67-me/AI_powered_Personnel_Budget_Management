from __future__ import annotations

import csv
import hashlib
import io
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl
import pymupdf
from docx import Document as DocxDocument
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings
from app.integrations.vector_store import replace_documents

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".csv",
    ".xlsx",
}
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024


class ScannedPdfError(ValueError):
    """Raised when a PDF has no extractable text and would require OCR."""


def normalize_filename(filename: str) -> str:
    basename = Path(filename.replace("\\", "/")).name
    normalized = unicodedata.normalize("NFKC", basename)
    normalized = " ".join(normalized.casefold().split())
    if not normalized or normalized in {".", ".."}:
        raise ValueError("A valid filename is required.")
    return normalized


def stable_document_id(filename: str) -> str:
    return hashlib.sha256(normalize_filename(filename).encode("utf-8")).hexdigest()


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _table_document(
    headers: list[str],
    rows: list[list[str]],
    *,
    source: str,
    sheet: str | None = None,
) -> Document:
    metadata: dict[str, Any] = {
        "source": source,
        "file_type": Path(source).suffix.lower().lstrip("."),
        "_table_headers": headers,
        "_table_rows": rows,
    }
    if sheet is not None:
        metadata["sheet"] = sheet
    return Document(page_content="", metadata=metadata)


def _parse_csv(filename: str, content: bytes) -> list[Document]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV documents must use UTF-8 encoding.") from exc

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text, newline=""), dialect=dialect)
    matrix = [
        [str(cell).strip() for cell in row]
        for row in reader
        if any(str(cell).strip() for cell in row)
    ]
    if not matrix:
        return []
    headers = matrix[0]
    if not any(headers):
        raise ValueError("CSV document must contain a header row.")
    rows = [
        (row + [""] * len(headers))[: len(headers)]
        for row in matrix[1:]
    ]
    return [_table_document(headers, rows, source=filename)] if rows else []


def _excel_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return " ".join(str(value).split())


def _parse_xlsx(filename: str, content: bytes) -> list[Document]:
    workbook = None
    parsed: list[Document] = []
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(content),
            read_only=True,
            data_only=True,
        )
        for worksheet in workbook.worksheets:
            matrix = [
                [_excel_cell(value) for value in row]
                for row in worksheet.iter_rows(values_only=True)
            ]
            matrix = [row for row in matrix if any(row)]
            if not matrix:
                continue
            headers = matrix[0]
            rows = [
                (row + [""] * len(headers))[: len(headers)]
                for row in matrix[1:]
            ]
            if rows:
                parsed.append(
                    _table_document(
                        headers,
                        rows,
                        source=filename,
                        sheet=worksheet.title,
                    )
                )
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Unable to read the XLSX workbook.") from exc
    finally:
        if workbook is not None:
            workbook.close()
    return parsed


def parse_document(filename: str, content: bytes) -> list[Document]:
    """Parse a file into normalized text documents with page/sheet metadata."""
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            "Unsupported file type. Supported types: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
    if not content:
        raise ValueError("Uploaded document is empty.")
    if len(content) > MAX_DOCUMENT_SIZE:
        raise ValueError("Document exceeds the maximum size of 10 MB.")

    if extension == ".pdf":
        parsed: list[Document] = []
        try:
            with pymupdf.open(stream=content, filetype="pdf") as pdf:
                if pdf.is_encrypted:
                    raise ValueError("Password-protected PDFs are not supported.")
                for page_number, page in enumerate(pdf, start=1):
                    text = _normalize_text(page.get_text("text"))
                    if text:
                        parsed.append(
                            Document(
                                page_content=text,
                                metadata={
                                    "source": filename,
                                    "file_type": "pdf",
                                    "page": page_number,
                                },
                            )
                        )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Unable to read the PDF document.") from exc
        if not parsed:
            raise ScannedPdfError(
                "This PDF contains no extractable text. Scanned PDFs are not "
                "supported because OCR is not enabled."
            )
        return parsed

    if extension == ".docx":
        try:
            document = DocxDocument(io.BytesIO(content))
        except Exception as exc:
            raise ValueError("Unable to read the DOCX document.") from exc
        sections = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                sections.append(" | ".join(cell.text for cell in row.cells))
        text = _normalize_text("\n".join(sections))
        return (
            [
                Document(
                    page_content=text,
                    metadata={"source": filename, "file_type": "docx"},
                )
            ]
            if text
            else []
        )

    if extension == ".txt":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT documents must use UTF-8 encoding.") from exc
        text = _normalize_text(text)
        return (
            [
                Document(
                    page_content=text,
                    metadata={"source": filename, "file_type": "txt"},
                )
            ]
            if text
            else []
        )

    if extension == ".csv":
        return _parse_csv(filename, content)

    if extension == ".xlsx":
        return _parse_xlsx(filename, content)

    raise ValueError(f"Unsupported file type: {extension}")


def _format_table_chunk(headers: list[str], rows: list[list[str]]) -> str:
    header_line = " | ".join(headers)
    row_lines = [" | ".join(row) for row in rows]
    return "\n".join([header_line, *row_lines])


def _split_table_document(
    document: Document,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    headers = list(document.metadata.get("_table_headers") or [])
    rows = [list(row) for row in document.metadata.get("_table_rows") or []]
    if not headers or not rows:
        return []

    chunks: list[Document] = []
    row_start = 0
    header_length = len(" | ".join(headers))
    while row_start < len(rows):
        row_end = row_start
        chunk_length = header_length
        while row_end < len(rows):
            row_length = len(" | ".join(rows[row_end])) + 1
            if row_end > row_start and chunk_length + row_length > chunk_size:
                break
            chunk_length += row_length
            row_end += 1

        selected_rows = rows[row_start:row_end]
        metadata = {
            key: value
            for key, value in document.metadata.items()
            if not key.startswith("_table_")
        }
        chunks.append(
            Document(
                page_content=_format_table_chunk(headers, selected_rows),
                metadata=metadata,
            )
        )
        if row_end >= len(rows):
            break

        next_start = row_end
        if chunk_overlap:
            overlap_size = 0
            candidate = row_end - 1
            while candidate >= row_start:
                row_length = len(" | ".join(rows[candidate])) + 1
                if overlap_size + row_length > chunk_overlap:
                    break
                overlap_size += row_length
                next_start = candidate
                candidate -= 1
            if next_start <= row_start:
                next_start = row_end
        row_start = next_start

    return chunks


def split_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Document]:
    """Chunk text normally and tables by rows with headers repeated per chunk."""
    settings = get_settings()
    size = settings.rag_chunk_size if chunk_size is None else chunk_size
    overlap = settings.rag_chunk_overlap if chunk_overlap is None else chunk_overlap
    if size < 1:
        raise ValueError("chunk_size must be greater than zero.")
    if overlap < 0 or overlap >= size:
        raise ValueError(
            "chunk_overlap must be non-negative and smaller than chunk_size."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        add_start_index=True,
    )
    chunks: list[Document] = []
    for document in documents:
        if "_table_headers" in document.metadata:
            chunks.extend(
                _split_table_document(
                    document,
                    chunk_size=size,
                    chunk_overlap=overlap,
                )
            )
        else:
            chunks.extend(splitter.split_documents([document]))
    return chunks


def prepare_document(filename: str, content: bytes) -> list[Document]:
    return split_documents(parse_document(filename, content))


def index_parsed_document(
    chunks: list[Document],
    *,
    user_id: str,
    source_filename: str,
    doc_id: str,
    content_hash_value: str,
    uploaded_at: str,
) -> dict[str, int | str]:
    if len(chunks) > get_settings().rag_max_chunks:
        raise ValueError(
            f"Document produces {len(chunks)} chunks, exceeding the maximum "
            f"allowed of {get_settings().rag_max_chunks}."
        )

    embedding_model = get_settings().gemini_embedding_model
    for chunk_index, chunk in enumerate(chunks):
        chunk.metadata.update(
            {
                "doc_id": doc_id,
                "user_id": user_id,
                "source_type": "document",
                "source": source_filename,
                "chunk_index": chunk_index,
                "content_hash": content_hash_value,
                "uploaded_at": uploaded_at,
                "embedding_model": embedding_model,
                "vector_state": "indexed",
            }
        )
    chunk_ids = replace_documents(
        doc_id=doc_id,
        documents=chunks,
        user_id=user_id,
    )
    return {
        "filename": source_filename,
        "chunks_created": len(chunk_ids),
    }


def index_document(
    file_path: str | Path,
    *,
    user_id: str,
    source_filename: str | None = None,
    doc_id: str | None = None,
    uploaded_at: str | None = None,
) -> dict[str, int | str]:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Document not found: {path}")
    filename = source_filename or path.name
    raw_content = path.read_bytes()
    parsed_chunks = prepare_document(filename, raw_content)
    return index_parsed_document(
        parsed_chunks,
        user_id=user_id,
        source_filename=filename,
        doc_id=doc_id or stable_document_id(filename),
        content_hash_value=content_hash(raw_content),
        uploaded_at=uploaded_at or datetime.now(timezone.utc).isoformat(),
    )


def index_text(
    text: str,
    source: str = "manual_text",
    *,
    user_id: str,
) -> dict[str, int | str]:
    raw = text.encode("utf-8")
    if not text.strip():
        raise ValueError("Text cannot be empty.")
    chunks = split_documents(
        [
            Document(
                page_content=text,
                metadata={"source": source, "file_type": "text"},
            )
        ]
    )
    return index_parsed_document(
        chunks,
        user_id=user_id,
        source_filename=source,
        doc_id=stable_document_id(source),
        content_hash_value=content_hash(raw),
        uploaded_at=datetime.now(timezone.utc).isoformat(),
    )
