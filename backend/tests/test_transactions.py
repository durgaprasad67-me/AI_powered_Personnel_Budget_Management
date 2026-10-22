"""Basic automated tests for FinSight AI.

These tests avoid contacting MongoDB: they cover the home endpoint and
FastAPI/Pydantic request validation. Database integration tests should use
a separate test database or mocked collection methods.
"""
import os

# Set harmless defaults before importing the app so tests can run without
# real MongoDB credentials. No test in this file opens a database connection.
os.environ.setdefault("MONGO_USER", "test_user")
os.environ.setdefault("MONGO_PASSWORD", "test_password")
os.environ.setdefault("MONGO_CLUSTER", "localhost")

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.transaction import TransactionCreate

client = TestClient(app)


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
    assert transaction.category == "Food"
