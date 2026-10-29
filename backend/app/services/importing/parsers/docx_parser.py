"""
DOCX parser for FinSight AI.

Extracts transaction records from tables in Word documents.
Supports standard .docx files containing financial data.
"""

from io import BytesIO
from typing import Any

from docx import Document


def extract_docx(content: bytes) -> list[dict[str, Any]]:
    """
    Extract transaction rows from tables in a DOCX document.

    Args:
        content: Raw DOCX file content in bytes.

    Returns:
        A list of dictionaries representing extracted table rows.

    Raises:
        ValueError: If the document is empty, invalid, or contains
                    no usable transaction tables.
    """
    if not content:
        raise ValueError("The Word document is empty.")

    try:
        document = Document(BytesIO(content))
    except Exception as exc:
        raise ValueError(
            "Unable to read the Word document. Please upload a valid .docx file."
        ) from exc

    rows: list[dict[str, Any]] = []

    # Extract tables from the document.
    for table in document.tables:
        rows.extend(_extract_table_rows(table))

    if not rows:
        raise ValueError(
            "No usable transaction tables were found in the Word document. "
            "Please ensure the document contains a table with column headers "
            "and transaction records."
        )

    return rows


def _extract_table_rows(table: Any) -> list[dict[str, Any]]:
    """Extract transaction rows from a single Word table."""
    if not table.rows:
        return []

    headers = [_clean_cell(cell.text) for cell in table.rows[0].cells]
    if not any(headers):
        return []

    return [
        row
        for table_row in table.rows[1:]
        if (row := _build_row(headers, table_row)) is not None
    ]


def _build_row(headers: list[str | None], table_row: Any) -> dict[str, Any] | None:
    """Pair a table row's values with its non-empty headers."""
    values = [_clean_cell(cell.text) for cell in table_row.cells]
    if not any(values):
        return None

    row = {
        header: value
        for header, value in zip(headers, values)
        if header
    }
    return row or None


def _clean_cell(value: str) -> str | None:
    """
    Clean text extracted from a Word table cell.
    """
    if not value:
        return None

    # Replace line breaks and repeated whitespace with single spaces.
    cleaned_value = " ".join(value.split())
    return cleaned_value or None