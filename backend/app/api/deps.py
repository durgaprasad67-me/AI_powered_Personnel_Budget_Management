from app.db.client import get_database
from app.repositories.analytics import AnalyticsRepository
from app.repositories.budgets import BudgetRepository
from app.repositories.goals import GoalRepository
from app.repositories.transactions import TransactionRepository
from app.services.analytics import AnalyticsService
from app.services.budgets import BudgetService
from app.services.goals import GoalService
from app.services.transactions import TransactionService


def get_transaction_service() -> TransactionService:
    database = get_database()
    return TransactionService(TransactionRepository(database["transactions"]))


def get_transaction_repository() -> TransactionRepository:
    return TransactionRepository(get_database()["transactions"])


def get_budget_service() -> BudgetService:
    database = get_database()
    return BudgetService(
        BudgetRepository(database["budgets"], database["transactions"])
    )


def get_goal_service() -> GoalService:
    return GoalService(GoalRepository(get_database()["financial_goals"]))


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService(
        AnalyticsRepository(get_database()["transactions"])
    )
