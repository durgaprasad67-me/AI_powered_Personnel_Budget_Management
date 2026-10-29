"""
Text file parser for FinSight AI.

Extracts transaction records from plain-text files.
Supports delimiter-separated text files with a header row,
such as tab-separated or pipe-separated transaction data.

Example:
Date | Description | Amount | Type | Category
2026-10-01 | Salary | 35000 | income | Salary
2026-10-02 | Groceries | 1200 | expense | Food
"""

import csv
import io
from typing import Any

SUPPORTED_DELIMITERS = ("|", "\t", ";", ",")


def _decode_content(content: bytes) -> str:
    if not content:
        raise ValueError("The text file is empty.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Unable to read the text file. Please save it using UTF-8 encoding."
        ) from exc

    if not text.strip():
        raise ValueError("The text file contains no data.")

    return text


def _get_dialect(text: str) -> type[csv.Dialect]:
    try:
        return csv.Sniffer().sniff(
            text[:8192],
            delimiters="".join(SUPPORTED_DELIMITERS),
        )
    except csv.Error:
        return csv.excel_tab


def _clean_row(raw_row: dict[str | None, Any]) -> dict[str, Any] | None:
    if not any(value.strip() for value in raw_row.values() if isinstance(value, str)):
        return None

    row: dict[str, Any] = {}
    for header, value in raw_row.items():
        if header is None:
            raise ValueError("A text row contains more values than the header row.")

        clean_header = header.strip()
        if clean_header:
            row[clean_header] = value.strip() if isinstance(value, str) else value

    return row or None


def _extract_rows(reader: csv.DictReader) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for raw_row in reader:
        row = _clean_row(raw_row)
        if row:
            rows.append(row)

    if not rows:
        raise ValueError("No transaction records were found in the text file.")

    return rows


def extract_text(content: bytes) -> list[dict[str, Any]]:
    """
    Decode a UTF-8 text file and extract transaction records.

    Args:
        content: Raw bytes from the uploaded .txt file.

    Returns:
        A list of dictionaries representing transaction rows.

    Raises:
        ValueError: If the file is empty, unreadable, or malformed.
    """
    try:
        text = _decode_content(content)
        dialect = _get_dialect(text)

        reader = csv.DictReader(
            io.StringIO(text, newline=""),
            dialect=dialect,
        )

        if not reader.fieldnames:
            raise ValueError("The text file must contain a header row.")

        headers = []
        for header in reader.fieldnames:
            headers.append(header.strip() if header else "")

        if not any(headers):
            raise ValueError("The text file contains no usable column headers.")

        return _extract_rows(reader)

    except ValueError:
        raise
    except csv.Error as exc:
        raise ValueError("The text file contains invalid or malformed data.") from exc