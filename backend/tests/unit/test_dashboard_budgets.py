from datetime import date

from app.api.v1.endpoints.dashboard import _active_budget_roots


def test_dashboard_counts_active_parent_allocation_once():
    global_budget = {
        "start_date": "2026-10-01",
        "period": "monthly",
        "amount": 1000,
        "transaction_type": "all",
        "category": None,
    }
    food_allocation = {
        "start_date": "2026-10-01",
        "period": "monthly",
        "amount": 400,
        "transaction_type": "expense",
        "category": "food",
    }
    future_budget = {
        "start_date": "2026-12-01",
        "period": "monthly",
        "amount": 250,
        "transaction_type": "expense",
        "category": "transport",
    }

    roots = _active_budget_roots(
        [global_budget, food_allocation, future_budget],
        date(2026, 10, 1),
        date(2026, 10, 31),
    )

    assert roots == [global_budget]
