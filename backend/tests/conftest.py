import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_USER", "test_user")
os.environ.setdefault("MONGO_PASSWORD", "test_password")
os.environ.setdefault("MONGO_CLUSTER", "localhost")

from app.core.config import Settings

# Never load a developer's dotenv file during the test suite.
Settings.model_config["env_file"] = None

from app.api.deps import (
    get_analytics_service,
    get_budget_service,
    get_goal_service,
    get_rag_document_repository,
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
    FakeRAGDocumentRepository,
    FakeTransactionRepository,
)


@pytest.fixture
def client(overrides):
    return TestClient(app)


@pytest.fixture
def overrides():
    transaction_repository = FakeTransactionRepository()
    budget_repository = FakeBudgetRepository(transaction_repository=transaction_repository)
    goal_repository = FakeGoalRepository()
    analytics_repository = FakeAnalyticsRepository()
    rag_document_repository = FakeRAGDocumentRepository()

    async def ping_database():
        return {"ok": 1}

    async def no_vector_sync(*args, **kwargs):
        return True

    async def no_vector_delete(*args, **kwargs):
        return True

    class FakeDatabase:
        async def command(self, name):
            return await ping_database()

    app.dependency_overrides[get_database] = lambda: FakeDatabase()
    app.dependency_overrides[get_transaction_repository] = lambda: (
        transaction_repository
    )
    app.dependency_overrides[get_transaction_service] = lambda: TransactionService(
        transaction_repository,
        budget_repository,
        vector_sync=no_vector_sync,
        vector_delete=no_vector_delete,
    )
    app.dependency_overrides[get_budget_service] = lambda: BudgetService(
        budget_repository
    )
    app.dependency_overrides[get_goal_service] = lambda: GoalService(goal_repository)
    app.dependency_overrides[get_analytics_service] = lambda: AnalyticsService(
        analytics_repository
    )
    app.dependency_overrides[get_rag_document_repository] = (
        lambda: rag_document_repository
    )

    yield {
        "transactions": transaction_repository,
        "budgets": budget_repository,
        "goals": goal_repository,
        "analytics": analytics_repository,
        "rag_documents": rag_document_repository,
    }

    app.dependency_overrides.clear()
