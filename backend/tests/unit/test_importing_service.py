import asyncio

import pytest

from app.core.exceptions import InvalidInputError
from app.services.importing.service import (
    extract_transactions,
    insert_transactions,
    validate_extension,
    validate_rows,
)
from tests.fakes import FakeTransactionRepository


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


def test_explicit_loan_types_survive_credit_and_debit_columns():
    validated = validate_rows(
        [
            {
                "date": "2026-10-23",
                "credit": 500,
                "transaction_type": "loan_taken",
                "category": "loan",
                "description": "Loan disbursed",
            },
            {
                "date": "2026-10-24",
                "debit": 100,
                "transaction_type": "loan_repaid",
                "category": "loan",
                "description": "Loan EMI",
            },
        ]
    )
    assert [item.transaction_type for item in validated] == [
        "loan_taken",
        "loan_repaid",
    ]


def test_credit_and_debit_columns_infer_specific_loan_actions_from_text():
    validated = validate_rows(
        [
            {
                "date": "2026-10-23",
                "credit": 500,
                "description": "Personal loan taken",
            },
            {
                "date": "2026-10-24",
                "credit": 100,
                "description": "Loan repayment collected",
            },
            {
                "date": "2026-10-25",
                "debit": 75,
                "description": "Home loan repaid",
            },
        ]
    )

    assert [item.transaction_type for item in validated] == [
        "loan_taken",
        "loan_collected",
        "loan_repaid",
    ]


def test_import_rejects_loan_type_that_conflicts_with_credit_debit_direction():
    with pytest.raises(InvalidInputError):
        validate_rows(
            [
                {
                    "date": "2026-10-23",
                    "debit": 500,
                    "transaction_type": "loan_taken",
                    "category": "loan",
                    "description": "Loan taken",
                }
            ]
        )


def test_import_persists_all_rows_then_calls_one_vector_batch():
    rows = validate_rows(
        [
            {
                "date": "2026-06-12",
                "amount": 42.75,
                "transaction_type": "expense",
                "category": "groceries",
                "description": "Fresh Mart",
            },
            {
                "date": "2026-06-14",
                "amount": 18.25,
                "transaction_type": "expense",
                "category": "groceries",
                "description": "Fresh Mart",
            },
        ]
    )
    repository = FakeTransactionRepository()
    batches = []

    async def fake_vector_sync(transactions, *, user_id, repository):
        batches.append((transactions, user_id))
        raise RuntimeError("simulated embedding outage")

    imported_ids = run(
        insert_transactions(
            rows,
            repository,
            user_id="alice",
            vector_sync=fake_vector_sync,
        )
    )

    assert imported_ids == ["1", "2"]
    assert len(repository.documents) == 2
    assert all(item["user_id"] == "alice" for item in repository.documents.values())
    assert all(
        item["vector_index_status"] == "pending"
        for item in repository.documents.values()
    )
    assert len(batches) == 1
    assert len(batches[0][0]) == 2
