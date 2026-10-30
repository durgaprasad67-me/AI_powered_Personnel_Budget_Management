from fastapi import Depends

from app.db.client import get_database
from app.db.collections import BUDGETS, FINANCIAL_GOALS, TRANSACTIONS
from app.integrations.llm import get_gemini_client
from app.repositories.analytics import AnalyticsRepository
from app.repositories.budgets import BudgetRepository
from app.repositories.goals import GoalRepository
from app.repositories.transactions import TransactionRepository
from app.services.analytics import AnalyticsService
from app.services.budgets import BudgetService
from app.services.goals import GoalService
from app.services.insights import InsightService
from app.services.transactions import TransactionService


def get_transaction_repository(
    database=Depends(get_database),
) -> TransactionRepository:
    return TransactionRepository(database[TRANSACTIONS])


def get_transaction_service(
    repository: TransactionRepository = Depends(get_transaction_repository),
) -> TransactionService:
    return TransactionService(repository)


def get_budget_service(database=Depends(get_database)) -> BudgetService:
    return BudgetService(BudgetRepository(database[BUDGETS], database[TRANSACTIONS]))


def get_goal_service(database=Depends(get_database)) -> GoalService:
    return GoalService(GoalRepository(database[FINANCIAL_GOALS]))


def get_analytics_service(database=Depends(get_database)) -> AnalyticsService:
    return AnalyticsService(AnalyticsRepository(database[TRANSACTIONS]))


def get_insight_service(
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> InsightService:
    return InsightService(analytics, get_gemini_client)
