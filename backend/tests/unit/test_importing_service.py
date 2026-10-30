import asyncio

import pytest

from app.core.exceptions import InvalidInputError
from app.services.importing.service import (
    extract_transactions,
    validate_extension,
    validate_rows,
)


def run(awaitable):
    return asyncio.run(awaitable)


def test_validate_extension():
    assert validate_extension("transactions.csv") == ".csv"
    with pytest.raises(InvalidInputError):
        validate_extension("transactions.exe")


def test_validate_rows_and_extract_tiny_csv():
    content = (
        b"date,amount,transaction_type,category,description\n"
        b"2026-10-23,25,expense,food,Lunch\n"
    )
    rows = extract_transactions("transactions.csv", content)
    validated = validate_rows(rows)

    assert len(validated) == 1
    assert validated[0].amount == 25
    assert validated[0].category == "food"
