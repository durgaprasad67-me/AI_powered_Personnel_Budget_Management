"""
Data normalization utilities for FinSight AI file imports.

Responsibilities:
- Standardize column names.
- Map common financial column names to schema fields.
- Normalize transaction amounts and dates.
- Handle debit and credit columns.
- Clean extracted cell values.
"""

import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.domain.normalization import (
    normalize_amount,
    normalize_transaction_type,
)

# Maps common file column names to FinSight AI transaction fields.
COLUMN_ALIASES: dict[str, set[str]] = {
    "date": {
        "date",
        "transaction date",
        "txn date",
        "value date",
        "posting date",
    },
    "description": {
        "description",
        "details",
        "narration",
        "particulars",
        "transaction details",
        "remarks",
        "merchant",
    },
    "amount": {
        "amount",
        "transaction amount",
        "txn amount",
    },
    "debit": {
        "debit",
        "withdrawal",
        "withdrawals",
        "money out",
    },
    "credit": {
        "credit",
        "deposit",
        "deposits",
        "money in",
    },
    "transaction_type": {
        "type",
        "transaction type",
        "txn type",
        "dr cr",
        "debit credit",
    },
    "category": {
        "category",
        "expense category",
    },
}


def normalize_header(value: Any) -> str:
    """
    Normalize a column header for consistent matching.

    Example:
        'Transaction Amount' -> 'transaction amount'
        'Transaction_Type'   -> 'transaction type'
    """
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text)

    return text


def map_column_name(header: Any) -> str | None:
    """
    Map a recognized source column name to a standard field name.

    Returns None when the column is not recognized.
    """
    normalized = normalize_header(header)

    for field_name, aliases in COLUMN_ALIASES.items():
        if normalized in aliases:
            return field_name

    return None


def clean_value(value: Any) -> Any:
    """
    Clean common values extracted from PDF, DOCX, CSV, or Excel.

    - Converts blank strings to None.
    - Converts dates and datetimes to ISO strings.
    - Converts integral floats to integers.
    - Converts NaN to None.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None

        if value.is_integer():
            return int(value)

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

    return value


def _collect_normalized_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Map recognized source fields while retaining the first non-empty value."""
    normalized: dict[str, Any] = {}

    for original_key, original_value in row.items():
        field_name = map_column_name(original_key)
        if field_name is None:
            continue

        value = clean_value(original_value)
        if field_name not in normalized or normalized[field_name] is None:
            normalized[field_name] = value

    return normalized


def _normalize_debit_credit(normalized: dict[str, Any]) -> bool:
    """Set amount and type from debit/credit fields when either is present."""
    debit = normalize_amount(normalized.get("debit"))
    credit = normalize_amount(normalized.get("credit"))

    if debit is None and credit is None:
        return False

    if debit not in (None, Decimal("0")) and credit not in (None, Decimal("0")):
        raise ValueError("A transaction cannot have both debit and credit amounts.")

    if credit not in (None, Decimal("0")):
        normalized["amount"] = abs(credit)
        normalized["transaction_type"] = "income"
    elif debit not in (None, Decimal("0")):
        normalized["amount"] = abs(debit)
        normalized["transaction_type"] = "expense"
    else:
        normalized["amount"] = abs(debit or credit or Decimal("0"))

    return True


def _normalize_amount_field(normalized: dict[str, Any]) -> None:
    """Normalize an amount field and infer its type when needed."""
    if "amount" not in normalized:
        return

    amount = normalize_amount(normalized["amount"])
    if amount is None:
        return

    if "transaction_type" not in normalized:
        normalized["transaction_type"] = "expense" if amount < 0 else "income"
    normalized["amount"] = abs(amount)


def normalize_transaction_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize one extracted row into FinSight AI transaction fields.

    Handles:
    - Common column aliases.
    - Currency-formatted amounts.
    - Debit and credit columns.
    - Common transaction type labels.
    - Empty and date values.

    Unrecognized columns are ignored.
    """
    if not isinstance(row, dict):
        raise TypeError("Transaction row must be a dictionary.")

    normalized = _collect_normalized_fields(row)

    # Determine the amount from debit and credit columns when available.
    if not _normalize_debit_credit(normalized):
        _normalize_amount_field(normalized)

    if "transaction_type" in normalized:
        normalized["transaction_type"] = normalize_transaction_type(
            normalized["transaction_type"]
        )

    # Remove source-only fields; they are not TransactionCreate fields.
    normalized.pop("debit", None)
    normalized.pop("credit", None)

    return normalized
