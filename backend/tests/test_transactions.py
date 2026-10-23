"""Basic automated tests for FinSight AI.

These tests avoid contacting MongoDB: they cover the home endpoint,
FastAPI/Pydantic request validation, and schema clean-up (letter case,
extra spaces, default date). Database integration tests should use a
separate test database or mocked collection methods.
"""
import os

# Set harmless defaults before importing the app so tests can run without
# real MongoDB credentials. No test in this file opens a database connection.
os.environ.setdefault("MONGO_USER", "test_user")
os.environ.setdefault("MONGO_PASSWORD", "test_password")
os.environ.setdefault("MONGO_CLUSTER", "localhost")

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.transaction import TransactionCreate, today_ist

client = TestClient(app)

# A valid transaction without a date; tests add or change fields as needed.
BASE = {
    "amount": 10,
    "transaction_type": "expense",
    "category": "Food",
    "description": "Lunch",
}


def test_home_endpoint_returns_welcome_message():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Welcome to FinSight AI"
    assert response.json()["status"] == "running"


def test_create_transaction_rejects_non_positive_amount():
    response = client.post(
        "/transactions",
        json={
            "amount": 0,
            "transaction_type": "expense",
            "category": "Food",
            "description": "Lunch",
            "date": "2026-10-23",
        },
    )

    assert response.status_code == 422


def test_create_transaction_rejects_invalid_transaction_type():
    response = client.post(
        "/transactions",
        json={
            "amount": 100,
            "transaction_type": "transfer",
            "category": "Food",
            "description": "Lunch",
            "date": "2026-10-23",
        },
    )

    assert response.status_code == 422


def test_transaction_schema_accepts_valid_transaction():
    transaction = TransactionCreate.model_validate(
        {
            "amount": 125.5,
            "transaction_type": "expense",
            "category": "Food",
            "description": "Lunch",
            "date": "2026-10-23",
        }
    )

    assert transaction.amount == 125.5
    assert transaction.transaction_type == "expense"
    assert transaction.category == "food"


def test_type_and_category_ignore_case_and_extra_spaces():
    transaction = TransactionCreate.model_validate(
        {
            **BASE,
            "transaction_type": " EXPENSE ",
            "category": "  Food  ",
            "date": "2026-10-23",
        }
    )

    assert transaction.transaction_type == "expense"
    assert transaction.category == "food"


def test_missing_date_defaults_to_today():
    transaction = TransactionCreate.model_validate(BASE)

    assert transaction.date == today_ist()


def test_blank_date_defaults_to_today():
    transaction = TransactionCreate.model_validate({**BASE, "date": ""})

    assert transaction.date == today_ist()


def test_given_date_is_kept():
    transaction = TransactionCreate.model_validate({**BASE, "date": "2026-01-05"})

    assert str(transaction.date) == "2026-01-05"