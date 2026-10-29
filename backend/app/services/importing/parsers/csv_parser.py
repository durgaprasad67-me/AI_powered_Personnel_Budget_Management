"""
CSV parser for FinSight AI.

Extracts transaction records from CSV files and returns
a list of dictionaries for normalization and validation.
"""

import csv
import io
from typing import Any, Sequence


def extract_csv(content: bytes) -> list[dict[str, Any]]:
    """
    Extract transaction rows from a CSV file.

    Args:
        content: Raw CSV file content in bytes.

    Returns:
        A list of dictionaries, where each dictionary
        represents one row of transaction data.

    Raises:
        ValueError: If the file is empty, invalid, or contains
                    no usable transaction records.
    """
    text = _decode_content(content)

    try:
        return _parse_rows(text)

    except (csv.Error, UnicodeError) as exc:
        raise ValueError("The CSV file contains invalid or malformed data.") from exc


def _decode_content(content: bytes) -> str:
    """Decode and validate the raw CSV content."""
    if not content:
        raise ValueError("The CSV file is empty.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Unable to read the CSV file. Please save it using UTF-8 encoding."
        ) from exc

    if not text.strip():
        raise ValueError("The CSV file contains no data.")
    return text


def _parse_rows(text: str) -> list[dict[str, Any]]:
    """Parse CSV text into normalized transaction rows."""
    reader = csv.DictReader(io.StringIO(text, newline=""), dialect=_detect_dialect(text))
    _clean_headers(reader.fieldnames)
    rows = [_clean_row(raw_row) for raw_row in reader if _has_content(raw_row)]
    rows = [row for row in rows if row]

    if not rows:
        raise ValueError("No transaction records were found in the CSV file.")
    return rows


def _detect_dialect(text: str) -> type[csv.Dialect]:
    """Detect a common CSV delimiter, defaulting to commas."""
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _clean_headers(fieldnames: Sequence[str] | None) -> list[str]:
    """Validate and normalize CSV headers."""
    if not fieldnames:
        raise ValueError("The CSV file must contain a header row.")

    headers = [header.strip() if header else "" for header in fieldnames]
    if not any(headers):
        raise ValueError("The CSV file contains no usable column headers.")
    return headers


def _has_content(raw_row: dict[str | None, str | None]) -> bool:
    """Return whether a CSV row contains any non-whitespace value."""
    return any(value and value.strip() for value in raw_row.values() if isinstance(value, str))


def _clean_row(raw_row: dict[str | None, str | None]) -> dict[str, Any]:
    """Normalize a parsed CSV row."""
    row: dict[str, Any] = {}
    for header, value in raw_row.items():
        if header is None:
            raise ValueError("A CSV row contains more values than the header row.")
        clean_header = header.strip()
        if clean_header:
            row[clean_header] = value.strip() if isinstance(value, str) else value
    return row