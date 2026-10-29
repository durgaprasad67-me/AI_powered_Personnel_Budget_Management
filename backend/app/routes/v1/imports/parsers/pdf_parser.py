"""
PDF parser for FinSight AI.

Extracts transaction tables from text-based PDF files.
Scanned PDFs requiring OCR are not supported by this parser.
"""

from typing import Any

import fitz  # PyMuPDF


def extract_pdf(content: bytes) -> list[dict[str, Any]]:
    """
    Extract tables from a PDF document.

    Args:
        content: Raw PDF file content in bytes.

    Returns:
        A list of dictionaries representing extracted table rows.

    Raises:
        ValueError: If the PDF is invalid or contains no usable tables.
    """
    if not content:
        raise ValueError("The PDF file is empty.")

    rows: list[dict[str, Any]] = []

    try:
        with fitz.open(stream=content, filetype="pdf") as document:
            if document.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")

            rows.extend(_extract_document_rows(document))

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "Unable to extract tables from the PDF. "
            "The file may be invalid or use an unsupported layout."
        ) from exc

    if not rows:
        raise ValueError(
            "No usable transaction tables were found in the PDF. "
            "Scanned PDFs and unsupported layouts may require OCR "
            "or additional extraction rules."
        )

    return rows


def _extract_document_rows(document: Any) -> list[dict[str, Any]]:
    """Extract rows from all tables in a PDF document."""
    rows: list[dict[str, Any]] = []

    for page in document:
        tables = page.find_tables()
        for table in tables.tables:
            rows.extend(_extract_table_rows(table.extract()))

    return rows


def _extract_table_rows(extracted_table: Any) -> list[dict[str, Any]]:
    """Extract transaction rows from one table."""
    if not extracted_table or len(extracted_table) < 2:
        return []

    headers = [_clean_cell(header) for header in extracted_table[0]]
    if not any(headers):
        return []

    return [
        row
        for raw_row in extracted_table[1:]
        if (row := _build_row(headers, raw_row))
    ]


def _build_row(headers: list[str | None], raw_row: Any) -> dict[str, Any] | None:
    """Build a row from table headers and cell values."""
    values = [_clean_cell(value) for value in raw_row]
    if not any(values):
        return None

    row = {
        header: value
        for header, value in zip(headers, values)
        if header
    }
    return row or None


def _clean_cell(value: Any) -> str | None:
    """
    Clean an extracted PDF table cell.
    """
    if value is None:
        return None

    text = " ".join(str(value).split())
    return text or None