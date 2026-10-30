import asyncio
from datetime import date

import pytest

from app.core.exceptions import InvalidInputError, NotFoundError
from app.schemas.budgets import BudgetCreate, BudgetUpdate
from app.schemas.goals import FinancialGoalCreate, FinancialGoalUpdate
from app.schemas.transactions import TransactionCreate, TransactionUpdate
from app.services.analytics import AnalyticsService
from app.services.budgets import BudgetService
from app.services.goals import GoalService
from app.services.transactions import TransactionService
from tests.fakes import (
    FakeAnalyticsRepository,
    FakeBudgetRepository,
    FakeGoalRepository,
    FakeTransactionRepository,
)


def run(awaitable):
    return asyncio.run(awaitable)


def transaction_data(**changes):
    return {
        "amount": 100,
        "transaction_type": "expense",
        "category": "food",
        "description": "Lunch",
        "date": "2026-10-23",
        **changes,
    }


def test_transaction_service_create_list_filters_get_update_replace_delete():
    repository = FakeTransactionRepository()
    service = TransactionService(repository)
    created = run(
        service.create(TransactionCreate.model_validate(transaction_data()))
    )

    assert created["id"] == 1
    listed = run(
        service.list(
            transaction_type="expense",
            category=" FOOD ",
            start_date="2026-01-01",
            end_date="2026-12-31",
            limit=50,
            skip=0,
        )
    )
    assert listed["total"] == 1
    assert run(service.get(1))["id"] == 1

    updated = run(
        service.update(
            1,
            TransactionUpdate.model_validate({"amount": 125}),
        )
    )
    assert updated["amount"] == 125

    replaced = run(
        service.replace(
            1,
            TransactionCreate.model_validate(transaction_data(amount=200)),
        )
    )
    assert replaced["amount"] == 200
    run(service.delete(1))
    with pytest.raises(NotFoundError):
        run(service.get(1))


def test_transaction_service_errors():
    service = TransactionService(FakeTransactionRepository())

    with pytest.raises(NotFoundError):
        run(service.get(1))
    with pytest.raises(InvalidInputError) as no_changes:
        run(service.update(1, TransactionUpdate.model_validate({})))
    assert no_changes.value.status_code == 400
    with pytest.raises(InvalidInputError):
        run(
            service.update(
                1,
                TransactionUpdate.model_validate({"amount": None}),
            )
        )


def budget_data(**changes):
    return {
        "name": "Food",
        "category": "food",
        "amount": 500,
        "period": "monthly",
        "start_date": "2026-10-01",
        **changes,
    }


def test_budget_service_validation_and_progress():
    repository = FakeBudgetRepository()
    service = BudgetService(repository)
    budget = run(service.create(BudgetCreate.model_validate(budget_data())))

    repository.spent_amount_value = 300
    progress = run(service.progress(budget["id"]))
    assert progress.spent_amount == 300
    assert progress.remaining_amount == 200

    with pytest.raises(InvalidInputError) as invalid_id:
        run(service.get("bad"))
    assert invalid_id.value.status_code == 400

    with pytest.raises(InvalidInputError):
        run(
            service.update(
                budget["id"],
                BudgetUpdate.model_validate({"end_date": "2026-09-01"}),
            )
        )
    with pytest.raises(InvalidInputError):
        run(
            service.update(
                budget["id"],
                BudgetUpdate.model_validate({"period": "custom"}),
            )
        )


def test_goal_service_sets_status_updates_and_reports_progress():
    repository = FakeGoalRepository()
    service = GoalService(repository)
    active = run(
        service.create(
            FinancialGoalCreate.model_validate(
                {
                    "name": "Emergency fund",
                    "target_amount": 1000,
                    "current_amount": 100,
                }
            )
        )
    )
    completed = run(
        service.create(
            FinancialGoalCreate.model_validate(
                {
                    "name": "Small goal",
                    "target_amount": 100,
                    "current_amount": 100,
                }
            )
        )
    )
    assert active["status"] == "active"
    assert completed["status"] == "completed"

    updated = run(
        service.update(
            active["id"],
            FinancialGoalUpdate.model_validate({"current_amount": 500}),
        )
    )
    assert updated["current_amount"] == 500
    progress = run(service.progress(active["id"]))
    assert progress.remaining_amount == 500


def test_analytics_service_monthly_and_spending_summaries():
    rows = [
        {
            "_id": {"type": "income", "category": "salary"},
            "total": 1000,
            "count": 1,
        },
        {
            "_id": {"type": "expense", "category": "food"},
            "total": 250,
            "count": 2,
        },
    ]
    service = AnalyticsService(FakeAnalyticsRepository(rows))

    monthly = run(service.monthly_summary("2026-10"))
    assert monthly["total_income"] == 1000
    spending = run(service.spending_summary(date(2026, 10, 1), date(2026, 10, 31)))
    assert spending.total_expenses == 250

    with pytest.raises(InvalidInputError):
        run(service.spending_summary(date(2026, 11, 1), date(2026, 10, 31)))
