from app.api.deps import get_current_user_id
from app.main import app


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
def test_transaction_routes_use_dependency_user_and_reject_body_user_id(
    client,
    overrides,
):
    app.dependency_overrides[get_current_user_id] = lambda: "alice"
    income = client.post(
        "/api/v1/transactions",
        json={
            "amount": 1000,
            "transaction_type": "income",
            "category": "salary",
            "description": "Salary",
            "date": "2026-06-01",
        },
    )
    assert income.status_code == 201
    created = client.post(
        "/api/v1/transactions",
        json={
            "amount": 42.75,
            "transaction_type": "expense",
            "category": "groceries",
            "description": "Fresh Mart",
            "date": "2026-06-12",
        },
    )
    assert created.status_code == 201
    transaction_id = created.json()["id"]

    app.dependency_overrides[get_current_user_id] = lambda: "bob"
    assert client.get(f"/api/v1/transactions/{transaction_id}").status_code == 404
    assert client.get("/api/v1/transactions").json()["items"] == []

    forbidden_body_user = client.post(
        "/api/v1/transactions",
        json={
            "amount": 10,
            "transaction_type": "expense",
            "category": "food",
            "description": "Lunch",
            "date": "2026-06-12",
            "user_id": "alice",
        },
    )
    assert forbidden_body_user.status_code == 422


# ===========================================================================
# 10 AUTHORITATIVE VALIDATION TESTS
# ===========================================================================

def test_v1_required_fields_and_extra_field_rejection(client, overrides):
    """V1: type, amount, category required; date optional defaults to today; reject extra fields."""
    # First seed income so available balance exists
    client.post("/api/v1/transactions", json={"amount": 10000, "transaction_type": "income", "category": "salary"})

    # Missing type -> 422
    res = client.post("/api/v1/transactions", json={"amount": 100, "category": "food"})
    assert res.status_code == 422
    assert "transaction_type" in res.json().get("errors", {})

    # Missing amount -> 422
    res = client.post("/api/v1/transactions", json={"transaction_type": "expense", "category": "food"})
    assert res.status_code == 422
    assert "amount" in res.json().get("errors", {})

    # Missing category -> 422
    res = client.post("/api/v1/transactions", json={"amount": 100, "transaction_type": "expense"})
    assert res.status_code == 422
    assert "category" in res.json().get("errors", {})

    # Date omitted -> passes and defaults to today
    res = client.post("/api/v1/transactions", json={"amount": 50, "transaction_type": "expense", "category": "food"})
    assert res.status_code == 201
    assert res.json()["date"] is not None

    # Unknown extra field -> rejected with 422
    res = client.post("/api/v1/transactions", json={"amount": 50, "transaction_type": "expense", "category": "food", "extra_bad": "surprise"})
    assert res.status_code == 422


def test_v2_type_normalization_and_support(client, overrides):
    """V2: supported types, case-insensitive, trimmed, normalized."""
    client.post("/api/v1/transactions", json={"amount": 10000, "transaction_type": "income", "category": "salary"})

    # Mixed case + spaces
    res = client.post("/api/v1/transactions", json={"amount": 50, "transaction_type": "  EXPENSE  ", "category": "food"})
    assert res.status_code == 201
    assert res.json()["transaction_type"] == "expense"

    # Supported aliases: credit -> income, debit -> expense, emi -> loan_repaid
    res_credit = client.post("/api/v1/transactions", json={"amount": 500, "transaction_type": "Credit", "category": "refund"})
    assert res_credit.status_code == 201
    assert res_credit.json()["transaction_type"] == "income"

    # Unsupported type -> 422
    res_bad = client.post("/api/v1/transactions", json={"amount": 50, "transaction_type": "cryptopump", "category": "food"})
    assert res_bad.status_code == 422


def test_v3_amount_format_decimal_safe(client, overrides):
    """V3: valid finite number > 0, max 2 decimals, no scientific notation, no NaN/inf/neg."""
    client.post("/api/v1/transactions", json={"amount": 10000, "transaction_type": "income", "category": "salary"})

    # Valid decimals
    res = client.post("/api/v1/transactions", json={"amount": 45.75, "transaction_type": "expense", "category": "food"})
    assert res.status_code == 201
    assert res.json()["amount"] == 45.75

    # Negative amount -> 422
    assert client.post("/api/v1/transactions", json={"amount": -10, "transaction_type": "expense", "category": "food"}).status_code == 422

    # Zero -> 422
    assert client.post("/api/v1/transactions", json={"amount": 0, "transaction_type": "expense", "category": "food"}).status_code == 422

    # Scientific notation -> 422
    assert client.post("/api/v1/transactions", json={"amount": "1e5", "transaction_type": "expense", "category": "food"}).status_code == 422


def test_v4_dynamic_ceiling_and_budget_limit_endpoint(client, overrides):
    """V4: dynamic ceiling for inflows, dynamic budget endpoint for frontend."""
    # Dynamic budget limit endpoint
    limit_res = client.get("/api/v1/transactions/budget-limit", params={"transaction_type": "income"})
    assert limit_res.status_code == 200
    assert limit_res.json()["max_allowed"] > 0
    assert limit_res.json()["has_budget"] is False

    # Inflow exceeding ceiling -> 422
    huge_res = client.post("/api/v1/transactions", json={"amount": 100_000_001, "transaction_type": "income", "category": "salary"})
    assert huge_res.status_code == 422


def test_v5_monthly_budget_rule_and_boundary(client, overrides):
    """V5: monthly budget rule for outflows: exactly equal passes, 1 paisa over fails, edit excludes self, warning if no budget."""
    # Seed high cash inflow to fund outflows
    client.post("/api/v1/transactions", json={"amount": 50000, "transaction_type": "income", "category": "salary", "date": "2026-11-01"})

    budget_repo = overrides["budgets"]
    # Create a monthly budget of 500 for Food in November 2026
    import asyncio
    asyncio.run(budget_repo.create({
        "name": "Food Nov",
        "category": "food",
        "transaction_type": "expense",
        "amount": 500.0,
        "period": "monthly",
        "start_date": "2026-11-01",
    }))

    # 1. Exactly equal to the remaining budget: ₹500.00 passes!
    pass_boundary = client.post("/api/v1/transactions", json={
        "amount": 500.00,
        "transaction_type": "expense",
        "category": "food",
        "date": "2026-11-05",
    })
    assert pass_boundary.status_code == 201
    tx_id = pass_boundary.json()["id"]

    # Now budget has 500 spent of 500. Remaining budget is 0.00.
    # 2. One paisa over (₹0.01) fails with clear message!
    fail_boundary = client.post("/api/v1/transactions", json={
        "amount": 0.01,
        "transaction_type": "expense",
        "category": "food",
        "date": "2026-11-06",
    })
    assert fail_boundary.status_code == 422
    data = fail_boundary.json()
    assert "Remaining budget" in str(data)

    # 3. Edit: on edit, the transaction being edited is excluded from the sum
    # Editing 500 -> 450 should pass because 500 is excluded
    edit_res = client.patch(f"/api/v1/transactions/{tx_id}", json={"amount": 450.0})
    assert edit_res.status_code == 200
    assert edit_res.json()["amount"] == 450.0

    # 4. If no budget set for that month: allows transaction but returns warning
    no_budget_res = client.post("/api/v1/transactions", json={
        "amount": 100.0,
        "transaction_type": "expense",
        "category": "food",
        "date": "2026-05-10",  # May 2026 has no budget
    })
    assert no_budget_res.status_code == 201
    assert "no budget set" in str(no_budget_res.json().get("warning", "")).lower()

    # 5. Inflow rule: Cash inflows (income, loan_taken, loan_collected, investment_return)
    # never follow budget rules and are never blocked, even when budget is full.
    inflows = [
        {"transaction_type": "income", "category": "salary", "amount": 80000.0},
        {"transaction_type": "loan_taken", "category": "loan", "amount": 25000.0},
        {"transaction_type": "loan_collected", "category": "loan", "amount": 15000.0},
        {"transaction_type": "investment_return", "category": "investment", "amount": 30000.0},
    ]
    for inf in inflows:
        res = client.post("/api/v1/transactions", json={
            "amount": inf["amount"],
            "transaction_type": inf["transaction_type"],
            "category": inf["category"],
            "date": "2026-11-10",
        })
        assert res.status_code == 201, f"Failed for {inf['transaction_type']}: {res.text}"
        assert res.json().get("warning") is None

    # 6. Cash outflows (investment, loan_repaid, loan_given, expense) follow budget rules.
    # When budget limit for food (450 spent of 500 = 50 remaining) is tested with 50.00:
    outflow_pass = client.post("/api/v1/transactions", json={
        "amount": 50.00,
        "transaction_type": "expense",
        "category": "food",
        "date": "2026-11-12",
    })
    assert outflow_pass.status_code == 201

    # Over budget now (500 spent of 500)
    outflow_fail = client.post("/api/v1/transactions", json={
        "amount": 1.00,
        "transaction_type": "expense",
        "category": "food",
        "date": "2026-11-15",
    })
    assert outflow_fail.status_code == 422
    assert "Remaining budget" in str(outflow_fail.json())


def test_v6_date_validation_future_and_floor(client, overrides):
    """V6: not in the future, not older than floor."""
    client.post("/api/v1/transactions", json={"amount": 10000, "transaction_type": "income", "category": "salary"})

    # Future date (tomorrow) -> 422
    from datetime import date, timedelta
    from app.domain.dates import today_ist
    tomorrow = today_ist() + timedelta(days=1)
    res_future = client.post("/api/v1/transactions", json={
        "amount": 50,
        "transaction_type": "expense",
        "category": "food",
        "date": str(tomorrow),
    })
    assert res_future.status_code == 422
    assert "future" in str(res_future.json()).lower()

    # Old date beyond 10-year floor -> 422
    old_date = "2005-01-01"
    res_old = client.post("/api/v1/transactions", json={
        "amount": 50,
        "transaction_type": "expense",
        "category": "food",
        "date": old_date,
    })
    assert res_old.status_code == 422


def test_v7_category_validation(client, overrides):
    """V7: category required, trimmed, 2-30 chars, lowercase stored."""
    client.post("/api/v1/transactions", json={"amount": 10000, "transaction_type": "income", "category": "salary"})

    # < 2 chars -> 422
    assert client.post("/api/v1/transactions", json={"amount": 50, "transaction_type": "expense", "category": "a"}).status_code == 422

    # > 30 chars -> 422
    assert client.post("/api/v1/transactions", json={"amount": 50, "transaction_type": "expense", "category": "x" * 31}).status_code == 422

    # Trimmed, spaces collapsed, lowercase stored
    res = client.post("/api/v1/transactions", json={"amount": 50, "transaction_type": "expense", "category": "  Home   Repairs  "})
    assert res.status_code == 201
    assert res.json()["category"] == "home repairs"


def test_v8_description_sanitization(client, overrides):
    """V8: optional, max 200, HTML tags and control chars stripped."""
    client.post("/api/v1/transactions", json={"amount": 10000, "transaction_type": "income", "category": "salary"})

    # HTML stripped
    res = client.post("/api/v1/transactions", json={
        "amount": 50,
        "transaction_type": "expense",
        "category": "food",
        "description": "<script>alert('xss')</script>Dinner with <b>family</b>",
    })
    assert res.status_code == 201
    assert res.json()["description"] == "alert('xss')Dinner with family"

    # > 200 chars -> 422
    res_long = client.post("/api/v1/transactions", json={
        "amount": 50,
        "transaction_type": "expense",
        "category": "food",
        "description": "a" * 201,
    })
    assert res_long.status_code == 422


def test_v9_security_ownership_and_field_errors_json(client, overrides):
    """V9: user_id only from auth/JWT, 422 returns field-level error messages in consistent JSON shape."""
    # user_id in body rejected
    res_body = client.post("/api/v1/transactions", json={
        "amount": 50,
        "transaction_type": "expense",
        "category": "food",
        "user_id": "malicious_user",
    })
    assert res_body.status_code == 422

    # 422 JSON shape has both detail and errors dict
    res_err = client.post("/api/v1/transactions", json={"amount": -50, "transaction_type": "expense", "category": "food"})
    assert res_err.status_code == 422
    body = res_err.json()
    assert "detail" in body
    assert "errors" in body
    assert "amount" in body["errors"]


def test_v10_double_submit_rejection(client, overrides):
    """V10: backend rejects identical transaction within duplicate window."""
    client.post("/api/v1/transactions", json={"amount": 10000, "transaction_type": "income", "category": "salary"})

    payload = {
        "amount": 75.0,
        "transaction_type": "expense",
        "category": "food",
        "description": "Coffee",
        "date": "2026-11-10",
    }
    first = client.post("/api/v1/transactions", json=payload)
    assert first.status_code == 201

    # Exact same transaction submitted immediately
    second = client.post("/api/v1/transactions", json=payload)
    assert second.status_code == 422
    assert "duplicate" in str(second.json()).lower()
