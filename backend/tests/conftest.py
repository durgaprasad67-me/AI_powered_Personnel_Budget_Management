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

    class FakeCollection:
        def __init__(self, name: str, backing_repo=None):
            self.name = name
            self.backing_repo = backing_repo
            self.docs = {}

        async def find_one(self, query: dict, projection: dict | None = None):
            if self.backing_repo:
                for doc in self.backing_repo.documents.values():
                    match = True
                    for k, v in query.items():
                        if k == "$or":
                            continue
                        if doc.get(k) != v:
                            match = False
                            break
                    if match:
                        return doc
                return None
            token = query.get("import_token") or query.get("import_id")
            if token and token in self.docs:
                return self.docs[token]
            for doc in self.docs.values():
                match = True
                for k, v in query.items():
                    if k == "$or":
                        or_matches = any(
                            all(doc.get(sub_k) == sub_v for sub_k, sub_v in clause.items())
                            for clause in v
                        )
                        if not or_matches:
                            match = False
                            break
                    elif doc.get(k) != v:
                        match = False
                        break
                if match:
                    return doc
            return None

        def find(self, query: dict, projection: dict | None = None):
            class AsyncCursor:
                def __init__(self, items):
                    self.items = list(items)

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    if not self.items:
                        raise StopAsyncIteration
                    return self.items.pop(0)

            results = []
            source = (
                self.backing_repo.documents.values()
                if self.backing_repo
                else self.docs.values()
            )
            fp_in = query.get("fingerprint", {}).get("$in", [])
            user_id = query.get("user_id")
            for doc in source:
                if user_id and doc.get("user_id") != user_id:
                    continue
                if fp_in and doc.get("fingerprint") not in fp_in:
                    continue
                results.append(doc)
            return AsyncCursor(results)

        async def count_documents(self, query: dict) -> int:
            source = (
                self.backing_repo.documents.values()
                if self.backing_repo
                else self.docs.values()
            )
            count = 0
            for doc in source:
                match = True
                for k, v in query.items():
                    if doc.get(k) != v:
                        match = False
                        break
                if match:
                    count += 1
            return count

        async def update_one(self, query: dict, update: dict, upsert: bool = False):
            token = query.get("import_token") or query.get("import_id")
            set_data = update.get("$set", {})
            if token:
                if token not in self.docs:
                    self.docs[token] = {"_id": token, **query}
                self.docs[token].update(set_data)
            return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()

        async def delete_one(self, query: dict):
            token = query.get("import_token")
            if token and token in self.docs:
                del self.docs[token]
            return type("DeleteResult", (), {"deleted_count": 1})()

        async def create_index(self, keys, **kwargs):
            return "ok"

    class FakeDatabase:
        def __init__(self):
            self.collections = {}

        def __getitem__(self, name: str):
            if name not in self.collections:
                repo = transaction_repository if name == "transactions" else None
                self.collections[name] = FakeCollection(name, backing_repo=repo)
            return self.collections[name]

        async def command(self, name):
            return await ping_database()

    fake_db = FakeDatabase()
    app.dependency_overrides[get_database] = lambda: fake_db
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
        "database": fake_db,
    }

    app.dependency_overrides.clear()


def pytest_pyfunc_call(pyfuncitem):
    import inspect
    import asyncio
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        testargs = {arg: pyfuncitem.funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        asyncio.run(pyfuncitem.obj(**testargs))
        return True

