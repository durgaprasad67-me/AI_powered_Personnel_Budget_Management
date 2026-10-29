"""
Validation utilities for FinSight AI file imports.
"""

from typing import Any

from pydantic import ValidationError

from app.routes.v1.imports.normalizers import normalize_transaction_row
from app.schemas.transactions import TransactionCreate


def validate_transaction(row: dict[str, Any]) -> TransactionCreate:
    """
    Normalize and validate one extracted transaction.

    Args:
        row: Raw transaction data extracted from a file.

    Returns:
        A validated TransactionCreate instance.

    Raises:
        TypeError: If the row is not a dictionary.
        ValueError: If normalization fails.
        ValidationError: If the data violates the Pydantic schema.
    """
    if not isinstance(row, dict):
        raise TypeError("Each transaction row must be a dictionary.")

    # Step 1: Standardize column names and values.
    normalized_row = normalize_transaction_row(row)

    # Step 2: Validate the normalized data.
    return TransactionCreate.model_validate(normalized_row)


def validate_transactions(
    rows: list[dict[str, Any]],
    max_errors: int = 100,
) -> tuple[list[TransactionCreate], list[dict[str, Any]]]:
    """
    Normalize and validate multiple transactions.

    Returns:
        A tuple containing:
        1. Validated transaction objects.
        2. Validation errors with their row numbers.
    """
    if max_errors < 1:
        raise ValueError("max_errors must be at least 1.")

    validated_transactions: list[TransactionCreate] = []
    errors: list[dict[str, Any]] = []

    for row_number, row in enumerate(rows, start=1):
        try:
            transaction = validate_transaction(row)
            validated_transactions.append(transaction)

        except ValidationError as exc:
            if len(errors) < max_errors:
                errors.append(
                    {
                        "row": row_number,
                        "errors": exc.errors(
                            include_url=False,
                            include_input=False,
                        ),
                    }
                )

        except (TypeError, ValueError) as exc:
            if len(errors) < max_errors:
                errors.append(
                    {
                        "row": row_number,
                        "errors": [{"message": str(exc)}],
                    }
                )

    return validated_transactions, errors