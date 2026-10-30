import asyncio


def test_transaction_crud_uses_repository_override(client, overrides):
    payload = {
        "amount": 100,
        "transaction_type": "expense",
        "category": "food",
        "description": "Lunch",
        "date": "2026-10-23",
    }

    created = client.post("/api/v1/transactions", json=payload)
    assert created.status_code == 201
    transaction_id = created.json()["id"]

    listed = client.get("/api/v1/transactions")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = client.get(f"/api/v1/transactions/{transaction_id}")
    assert fetched.status_code == 200

    patched = client.patch(
        f"/api/v1/transactions/{transaction_id}",
        json={"amount": 125},
    )
    assert patched.status_code == 200
    assert patched.json()["amount"] == 125

    replaced = client.put(
        f"/api/v1/transactions/{transaction_id}",
        json={**payload, "amount": 200},
    )
    assert replaced.status_code == 200
    assert replaced.json()["amount"] == 200

    deleted = client.delete(f"/api/v1/transactions/{transaction_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/transactions/{transaction_id}").status_code == 404


def test_transaction_get_returns_404(client, overrides):
    assert client.get("/api/v1/transactions/999").status_code == 404


def test_budget_bad_id_returns_400(client, overrides):
    assert client.get("/api/v1/budgets/not-an-object-id").status_code == 400


def test_analytics_summary_valid_and_invalid_month(client, overrides):
    valid = client.get("/api/v1/analytics/summary", params={"month": "2026-10"})
    assert valid.status_code == 200
    assert valid.json()["month"] == "2026-10"

    invalid = client.get("/api/v1/analytics/summary", params={"month": "2026-13"})
    assert invalid.status_code == 422


def test_health_routes_use_database_override(client, overrides):
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/transactions").status_code == 404


def test_rag_ask_happy_path_with_service_stub(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.rag.answer_with_rag",
        lambda question, k: asyncio.sleep(
            0,
            result={
                "question": question,
                "answer": "Use a food budget.",
                "sources": [],
            },
        ),
    )

    response = client.post(
        "/api/v1/ai/rag/ask",
        json={"question": "How can I spend less?", "k": 3},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "Use a food budget."


def test_import_happy_path_with_service_stubs(client, monkeypatch, overrides):
    monkeypatch.setattr(
        "app.api.v1.endpoints.imports.extract_transactions",
        lambda filename, content: [{"amount": 10}],
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.imports.validate_rows",
        lambda rows: [],
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.imports.insert_transactions",
        lambda transactions, repository: asyncio.sleep(0, result=["1"]),
    )

    response = client.post(
        "/api/v1/imports",
        files={"file": ("transactions.csv", b"amount\n10\n", "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["imported_records"] == 1
