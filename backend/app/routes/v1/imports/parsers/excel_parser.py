"""
Excel parser for FinSight AI.

Extracts transaction records from .xlsx and .xls files.
Uses the first worksheet and treats its first non-empty row
as the header row.
"""

from datetime import date, datetime
from io import BytesIO
import math
from pathlib import Path
from typing import Any, Literal, cast

import openpyxl
import xlrd


def extract_excel(content: bytes, extension: str) -> list[dict[str, Any]]:
    """
    Extract transaction records from an Excel file.

    Args:
        content: Raw bytes from the uploaded Excel file.
        extension: File extension, either '.xlsx' or '.xls'.

    Returns:
        A list of dictionaries representing transaction rows.

    Raises:
        ValueError: If the file is empty, invalid, or contains
                    no usable transaction records.
    """
    if not content:
        raise ValueError("The Excel file is empty.")

    extension = extension.lower()

    if extension not in {".xlsx", ".xls"}:
        raise ValueError("Unsupported Excel format. Use .xlsx or .xls.")

    if extension == ".xlsx":
        rows = _extract_xlsx(content)
    else:
        rows = _extract_xls(content)

    if not rows:
        raise ValueError("No transaction records were found in the Excel file.")

    return rows


def _extract_xlsx(content: bytes) -> list[dict[str, Any]]:
    """Extract records from an .xlsx workbook."""
    workbook = None

    try:
        workbook = openpyxl.load_workbook(
            BytesIO(content),
            read_only=True,
            data_only=True,
        )

        worksheet = workbook.active

        if worksheet is None:
            raise ValueError("The Excel workbook contains no active worksheet.")

        return _worksheet_to_records(worksheet.iter_rows(values_only=True))

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "Unable to read the .xlsx file. Please upload a valid Excel workbook."
        ) from exc
    finally:
        if workbook is not None:
            workbook.close()


def _extract_xls(content: bytes) -> list[dict[str, Any]]:
    """Extract records from a legacy .xls workbook."""
    try:
        workbook = xlrd.open_workbook(file_contents=content)

        if workbook.nsheets == 0:
            raise ValueError("The Excel workbook contains no worksheets.")

        worksheet = workbook.sheet_by_index(0)
        raw_rows: list[tuple[Any, ...]] = []

        for row_index in range(worksheet.nrows):
            values: list[Any] = []

            for column_index in range(worksheet.ncols):
                cell = worksheet.cell(row_index, column_index)
                values.append(
                    _xls_cell_value(
                        cell,
                        workbook.datemode,
                        row_index,
                        column_index,
                    )
                )

            raw_rows.append(tuple(values))

        return _worksheet_to_records(raw_rows)

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "Unable to read the .xls file. Please upload a valid Excel workbook."
        ) from exc


def _xls_cell_value(
    cell: Any,
    datemode: int,
    row_index: int,
    column_index: int,
) -> Any:
    """Convert an .xls cell to a Python value."""
    if cell.ctype == xlrd.XL_CELL_DATE:
        if not isinstance(cell.value, (int, float)):
            raise ValueError(
                f"Excel contains an invalid date in row {row_index + 1}, "
                f"column {column_index + 1}."
            )
        if datemode not in (0, 1):
            raise ValueError("Excel contains an invalid date mode.")
        return xlrd.xldate_as_datetime(
            cell.value,
            cast(Literal[0, 1], datemode),
        )

    if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
        return None

    if cell.ctype == xlrd.XL_CELL_ERROR:
        raise ValueError(
            f"Excel contains an error in row {row_index + 1}, "
            f"column {column_index + 1}."
        )

    return cell.value


def _worksheet_to_records(raw_rows: Any) -> list[dict[str, Any]]:
    """
    Convert worksheet rows into dictionaries.

    The first non-empty row is treated as the header.
    Completely empty rows are skipped.
    """
    headers: list[str] | None = None
    records: list[dict[str, Any]] = []

    for raw_row in raw_rows:
        values = [_clean_cell(value) for value in raw_row]

        if _is_empty_row(values):
            continue

        if headers is None:
            headers = _extract_headers(values)
            continue

        record = _row_to_record(values, headers)
        if record:
            records.append(record)

    if headers is None:
        raise ValueError("The Excel worksheet does not contain a usable header row.")

    return records


def _is_empty_row(values: list[Any]) -> bool:
    """Return whether a row contains no usable values."""
    return not any(value is not None for value in values)


def _extract_headers(values: list[Any]) -> list[str] | None:
    """Normalize and validate a worksheet header row."""
    headers = [str(value).strip() if value is not None else "" for value in values]

    if not any(headers):
        return None

    non_empty_headers = [header for header in headers if header]
    if len(set(non_empty_headers)) != len(non_empty_headers):
        raise ValueError("The Excel header row contains duplicate column names.")

    return headers


def _row_to_record(values: list[Any], headers: list[str]) -> dict[str, Any]:
    """Convert one worksheet row to a record."""
    if any(value is not None for value in values[len(headers):]):
        raise ValueError("A worksheet row contains data beyond the header columns.")

    values = values[: len(headers)]
    values.extend([None] * (len(headers) - len(values)))

    return {
        header: value
        for header, value in zip(headers, values)
        if header
    }


def _clean_cell(value: Any) -> Any:
    """Normalize Excel cell values without losing numeric precision."""
    if value is None:
        return None

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("The Excel file contains an invalid numeric value.")

        if value.is_integer():
            return int(value)

    return value