"""
Central error catalog and user-facing messages for FinSight AI file imports.
All user-facing error strings and templates are maintained in this module.
"""

from __future__ import annotations

from typing import Any


def format_rows(rows: list[int], max_shown: int = 5) -> str:
    """Format row numbers with spreadsheet labels, e.g., 'row 4' or 'rows 4, 9, 12 and 5 more'."""
    if not rows:
        return ""
    if len(rows) == 1:
        return f"row {rows[0]}"
    if len(rows) <= max_shown:
        return "rows " + ", ".join(str(r) for r in rows)
    shown = ", ".join(str(r) for r in rows[:max_shown])
    remaining = len(rows) - max_shown
    return f"rows {shown} and {remaining} more"


def count_label(count: int, singular: str = "row", plural: str = "rows") -> str:
    """Format a count and noun, e.g., '1 row' or '3 rows'."""
    return f"{count} {singular}" if count == 1 else f"{count} {plural}"


TEMPLATES: dict[str, str] = {
    "EMPTY_FILE": "The uploaded file '{filename}' is empty. Please choose a file that contains transaction data.",
    "FILE_TOO_LARGE": "File size exceeds the limit of {max_size_mb} MB. Please upload a smaller file.",
    "UNSUPPORTED_FORMAT": "The file format '{extension}' is not supported. Please upload a CSV, Excel (.xlsx, .xls), PDF, DOCX, or TXT file.",
    "CORRUPT_FILE": "Unable to read '{filename}'. The file appears to be corrupted or in an unexpected format.",
    "PASSWORD_PROTECTED": "The file '{filename}' is password-protected. Please remove password protection and re-upload.",
    "ENCODING_ERROR": "Unable to decode '{filename}'. Please save the file using standard UTF-8 encoding.",
    "MAX_ROWS_EXCEEDED": "The file contains {total_rows} rows, which exceeds the limit of {max_rows} rows per import.",
    "NO_TRANSACTIONS_FOUND": "No transactions were detected in '{filename}'. Ensure the file contains a table with Date, Description, Amount, Type, and Category columns.",
    "MISSING_COLUMNS": "We couldn't import '{filename}' because {missing_count} required {col_word} missing: {missing_columns}. Your file has: {file_columns}. Add the missing columns and upload again.",
    "DUPLICATE_HEADER": "Your file contains duplicate columns for '{column}'. Please ensure each column appears only once.",
    "UNKNOWN_COLUMNS": "Ignored unmapped columns: {columns}. FinSight AI only imports Date, Description, Amount, Type, and Category.",
    "UNKNOWN_COLUMN_HINT": "Unknown column '{column}'. Did you mean '{hint}'?",
    "MISSING_VALUE": "{column} is empty or missing in {count_str} ({rows}). Please fill these cells and re-upload.",
    "INVALID_DATE": "Invalid date format in {count_str} ({rows}). Accepted formats are YYYY-MM-DD, DD/MM/YYYY, or DD-MM-YYYY.",
    "FUTURE_DATE": "Date cannot be in the future in {count_str} ({rows}).",
    "DATE_TOO_OLD": "Date is older than {years} years in {count_str} ({rows}).",
    "INVALID_AMOUNT": "Amount must be a valid number in {count_str} ({rows}).",
    "AMOUNT_ZERO_OR_NEGATIVE": "Amount must be greater than zero in {count_str} ({rows}). The sign is determined by the Type column.",
    "AMOUNT_TOO_LARGE": "Amount exceeds the maximum limit of ₹{max_amount:,.2f} in {count_str} ({rows}).",
    "INVALID_TYPE": "Invalid transaction type '{sample_value}' in {count_str} ({rows}). Allowed types are: {allowed_types}.",
    "INVALID_CATEGORY": "Category must be between {min_len} and {max_len} characters in {count_str} ({rows}).",
    "DESCRIPTION_REQUIRED": "Description is required in {count_str} ({rows}).",
    "DESCRIPTION_TOO_LONG": "Description exceeds the maximum limit of {max_len} characters in {count_str} ({rows}).",
    "FILE_ALREADY_IMPORTED": "This file was already imported on {import_date} ({count} transactions). Importing it again would create duplicate records.",
    "DUPLICATES_FOUND": "{duplicate_count} of {total_count} records already exist in your account. We'll skip those and import the {new_count} new ones.",
    "ALL_DUPLICATES": "Nothing new to import. All {total_count} records already exist in your account.",
}


def render_message(code: str, **kwargs: Any) -> str:
    """Render a user-facing message from the catalog, falling back gracefully if unknown."""
    template = TEMPLATES.get(code)
    if not template:
        return f"Import issue ({code}): " + " ".join(f"{k}={v}" for k, v in kwargs.items())
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def group_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Group detailed errors by (code, column) to provide aggregated user summaries.
    Each item in errors has keys: 'row', 'column', 'code', 'message', 'severity'.
    """
    groups: dict[tuple[str, str], list[int]] = {}
    sample_msgs: dict[tuple[str, str], str] = {}

    for err in errors:
        code = str(err.get("code") or "UNKNOWN")
        column = str(err.get("column") or "")
        row = err.get("row")
        key = (code, column)
        if key not in groups:
            groups[key] = []
            sample_msgs[key] = str(err.get("message") or "")
        if isinstance(row, int) and row not in groups[key]:
            groups[key].append(row)

    grouped_list: list[dict[str, Any]] = []
    for (code, column), rows in groups.items():
        rows.sort()
        count = len(rows)
        cnt_str = count_label(count)
        row_str = format_rows(rows)

        # Build clean summary sentence
        if column:
            summary = render_message(
                code,
                column=column,
                count_str=cnt_str,
                rows=row_str,
                sample_value=err.get("sample_value", ""),
                allowed_types="income, expense, investment, investment_return, loan_taken, loan_repaid, loan_given, loan_collected",
                min_len=2,
                max_len=30,
            )
        else:
            summary = sample_msgs[(code, column)]

        grouped_list.append({
            "code": code,
            "column": column,
            "count": count,
            "rows": rows[:10],
            "total_rows_affected": count,
            "message": summary,
        })

    return grouped_list
