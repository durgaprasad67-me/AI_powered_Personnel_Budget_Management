def test_home_endpoint_returns_welcome_message(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Welcome to FinSight AI"
    assert response.json()["status"] == "running"


def test_create_transaction_rejects_non_positive_amount(client):
    response = client.post(
        "/api/v1/transactions",
        json={
            "amount": 0,
            "transaction_type": "expense",
            "category": "Food",
            "description": "Lunch",
            "date": "2026-10-23",
        },
    )

    assert response.status_code == 422


def test_create_transaction_rejects_invalid_transaction_type(client):
    response = client.post(
        "/api/v1/transactions",
        json={
            "amount": 100,
            "transaction_type": "transfer",
            "category": "Food",
            "description": "Lunch",
            "date": "2026-10-23",
        },
    )

    assert response.status_code == 422


def test_create_transaction_rejects_missing_amount(client):
    response = client.post("/api/v1/transactions", json={"description": "Lunch"})

    assert response.status_code == 422


def test_filter_rejects_unknown_transaction_type(client):
    response = client.get(
        "/api/v1/transactions",
        params={"transaction_type": "loan"},
    )

    assert response.status_code == 422
