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


async def no_vector_sync(*args, **kwargs):
    return True


async def no_vector_delete(*args, **kwargs):
    return True


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
    service = TransactionService(
        repository,
        vector_sync=no_vector_sync,
        vector_delete=no_vector_delete,
    )
    run(
        service.create(
            TransactionCreate.model_validate(
                transaction_data(
                    amount=1000,
                    transaction_type="income",
                    category="salary",
                )
            )
        )
    )
    created = run(service.create(TransactionCreate.model_validate(transaction_data())))

    assert created["id"] == 2
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
    assert run(service.get(2))["id"] == 2

    updated = run(
        service.update(
            2,
            TransactionUpdate.model_validate({"amount": 125}),
        )
    )
    assert updated["amount"] == 125

    replaced = run(
        service.replace(
            2,
            TransactionCreate.model_validate(transaction_data(amount=200)),
        )
    )
    assert replaced["amount"] == 200
    run(service.delete(2))
    with pytest.raises(NotFoundError):
        run(service.get(2))


def test_transaction_service_errors():
    service = TransactionService(
        FakeTransactionRepository(),
        vector_sync=no_vector_sync,
        vector_delete=no_vector_delete,
    )
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


def test_loan_inflows_fund_cash_outflows_without_salary_income():
    repository = FakeTransactionRepository()
    service = TransactionService(repository, vector_sync=no_vector_sync)

    run(
        service.create(
            TransactionCreate.model_validate(
                transaction_data(
                    amount=100,
                    transaction_type="loan_taken",
                    category="loan",
                    description="Personal loan taken",
                )
            )
        )
    )
    run(
        service.create(
            TransactionCreate.model_validate(
                transaction_data(
                    amount=40,
                    transaction_type="loan_repaid",
                    category="loan",
                    description="Loan repaid",
                )
            )
        )
    )
    run(
        service.create(
            TransactionCreate.model_validate(
                transaction_data(amount=60, transaction_type="expense")
            )
        )
    )

    with pytest.raises(InvalidInputError, match="available balance"):
        run(
            service.create(
                TransactionCreate.model_validate(
                    transaction_data(amount=0.01, transaction_type="expense")
                )
            )
        )


def test_import_cash_preflight_checks_the_whole_batch_before_writes():
    repository = FakeTransactionRepository()
    service = TransactionService(repository, vector_sync=no_vector_sync)
    run(
        service.create(
            TransactionCreate.model_validate(
                transaction_data(
                    amount=100,
                    transaction_type="income",
                    category="salary",
                )
            )
        )
    )
    imported = [
        TransactionCreate.model_validate(transaction_data(amount=80)),
        TransactionCreate.model_validate(transaction_data(amount=30)),
    ]

    with pytest.raises(InvalidInputError, match="No transactions were imported"):
        run(service.validate_import_batch(imported))

    assert len(repository.documents) == 1


def test_transaction_vector_failures_do_not_fail_mongo_crud():
    repository = FakeTransactionRepository()

    async def embedding_fails(*args, **kwargs):
        raise RuntimeError("offline embedding provider")

    service = TransactionService(
        repository,
        vector_sync=embedding_fails,
        vector_delete=embedding_fails,
    )
    run(
        service.create(
            TransactionCreate.model_validate(
                transaction_data(
                    amount=1000,
                    transaction_type="income",
                    category="salary",
                )
            )
        )
    )
    created = run(
        service.create(TransactionCreate.model_validate(transaction_data()))
    )
    assert created["id"] == 2
    assert repository.documents[1]["vector_index_status"] == "pending"
    assert repository.documents[2]["vector_index_status"] == "pending"

    updated = run(
        service.update(
            2,
            TransactionUpdate.model_validate({"amount": 125}),
        )
    )
    assert updated["amount"] == 125
    assert repository.documents[1]["vector_index_status"] == "pending"

    run(service.delete(2))
    assert 2 not in repository.documents


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

    # Budgets can be planned for future dates
    future_budget = run(
        service.create(
            BudgetCreate.model_validate(
                budget_data(
                    name="Future Food",
                    start_date="2030-01-01",
                    end_date="2030-01-31",
                )
            )
        )
    )
    assert future_budget["start_date"] == "2030-01-01"
    assert future_budget["end_date"] == "2030-01-31"


def test_budget_service_rejects_global_limit_below_specific_allocations():
    repository = FakeBudgetRepository()
    service = BudgetService(repository)
    run(
        service.create(
            BudgetCreate.model_validate(
                budget_data(name="Food", amount=600, category="food")
            )
        )
    )
    run(
        service.create(
            BudgetCreate.model_validate(
                budget_data(name="Transport", amount=500, category="transport")
            )
        )
    )

    with pytest.raises(InvalidInputError, match="Budget plan conflict"):
        run(
            service.create(
                BudgetCreate.model_validate(
                    budget_data(
                        name="Monthly total",
                        amount=1_000,
                        category=None,
                        transaction_type="all",
                    )
                )
            )
        )

    repository = FakeBudgetRepository()
    service = BudgetService(repository)
    run(
            service.create(
                BudgetCreate.model_validate(
                    budget_data(
                        name="Monthly total",
                        amount=1_000,
                        category=None,
                        transaction_type="all",
                    )
                )
            )
    )
    with pytest.raises(InvalidInputError, match="Budget plan conflict"):
            run(
                service.create(
                    BudgetCreate.model_validate(
                        budget_data(name="Food", amount=1_001, category="food")
                    )
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
