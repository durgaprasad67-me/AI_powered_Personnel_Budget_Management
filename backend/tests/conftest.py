import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_USER", "test_user")
os.environ.setdefault("MONGO_PASSWORD", "test_password")
os.environ.setdefault("MONGO_CLUSTER", "localhost")

from app.api.deps import (
    get_analytics_service,
    get_budget_service,
    get_goal_service,
    get_transaction_repository,
    get_transaction_service,
)
from app.db.client import get_database
from app.main import app
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


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def overrides():
    transaction_repository = FakeTransactionRepository()
    budget_repository = FakeBudgetRepository()
    goal_repository = FakeGoalRepository()
    analytics_repository = FakeAnalyticsRepository()

    async def ping_database():
        return {"ok": 1}

    class FakeDatabase:
        async def command(self, name):
            return await ping_database()

    app.dependency_overrides[get_database] = lambda: FakeDatabase()
    app.dependency_overrides[get_transaction_repository] = (
        lambda: transaction_repository
    )
    app.dependency_overrides[get_transaction_service] = (
        lambda: TransactionService(transaction_repository)
    )
    app.dependency_overrides[get_budget_service] = (
        lambda: BudgetService(budget_repository)
    )
    app.dependency_overrides[get_goal_service] = lambda: GoalService(goal_repository)
    app.dependency_overrides[get_analytics_service] = (
        lambda: AnalyticsService(analytics_repository)
    )

    yield {
        "transactions": transaction_repository,
        "budgets": budget_repository,
        "goals": goal_repository,
        "analytics": analytics_repository,
    }

    app.dependency_overrides.clear()
