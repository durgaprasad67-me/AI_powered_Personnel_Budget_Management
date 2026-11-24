import base64
import json
from fastapi import Depends, Header

from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.db.client import get_database
from app.db.collections import BUDGETS, FINANCIAL_GOALS, RAG_DOCUMENTS, TRANSACTIONS
from app.integrations.llm import get_gemini_client
from app.repositories.analytics import AnalyticsRepository
from app.repositories.budgets import BudgetRepository
from app.repositories.goals import GoalRepository
from app.repositories.rag_documents import RAGDocumentRepository
from app.repositories.transactions import TransactionRepository
from app.services.analytics import AnalyticsService
from app.services.budgets import BudgetService
from app.services.goals import GoalService
from app.services.insights import InsightService
from app.services.transactions import TransactionService


def get_current_user_id(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """Take user identity from X-User-Id header or JWT Bearer token when present, fallback to default user context."""
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        parts = token.split(".")
        if len(parts) == 3:
            try:
                padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
                user_id = payload.get("sub") or payload.get("user_id")
                if user_id and isinstance(user_id, str):
                    return user_id.strip()
            except Exception:
                pass
        elif token:
            return token
    return DEFAULT_CURRENT_USER_ID


def get_rag_document_repository(
    database=Depends(get_database),
) -> RAGDocumentRepository:
    return RAGDocumentRepository(database[RAG_DOCUMENTS])


def get_transaction_repository(
    database=Depends(get_database),
) -> TransactionRepository:
    budget_repository = BudgetRepository(database[BUDGETS], database[TRANSACTIONS])
    return TransactionRepository(database[TRANSACTIONS], budget_repository)


def get_transaction_service(
    repository: TransactionRepository = Depends(get_transaction_repository),
    database=Depends(get_database),
) -> TransactionService:
    return TransactionService(
        repository,
        BudgetRepository(database[BUDGETS], database[TRANSACTIONS]),
    )


def get_budget_service(database=Depends(get_database)) -> BudgetService:
    return BudgetService(BudgetRepository(database[BUDGETS], database[TRANSACTIONS]))


def get_goal_service(database=Depends(get_database)) -> GoalService:
    return GoalService(GoalRepository(database[FINANCIAL_GOALS]))


def get_analytics_service(database=Depends(get_database)) -> AnalyticsService:
    return AnalyticsService(AnalyticsRepository(database[TRANSACTIONS]))


def get_insight_service(
    analytics: AnalyticsService = Depends(get_analytics_service),
    transactions: TransactionService = Depends(get_transaction_service),
) -> InsightService:
    return InsightService(
        analytics,
        get_gemini_client,
        transaction_service=transactions,
    )
