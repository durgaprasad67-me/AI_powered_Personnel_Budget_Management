from app.db.client import budgets_collection, transactions_collection
from app.db.client import financial_goals_collection
from app.repositories.analytics import AnalyticsRepository
from app.repositories.budgets import BudgetRepository
from app.repositories.goals import GoalRepository
from app.repositories.transactions import TransactionRepository
from app.services.budgets import BudgetService
from app.services.goals import GoalService
from app.services.analytics import AnalyticsService
from app.services.transactions import TransactionService


def get_transaction_service() -> TransactionService:
    return TransactionService(TransactionRepository(transactions_collection))


def get_transaction_repository() -> TransactionRepository:
    return TransactionRepository(transactions_collection)


def get_budget_service() -> BudgetService:
    return BudgetService(BudgetRepository(budgets_collection, transactions_collection))


def get_goal_service() -> GoalService:
    return GoalService(GoalRepository(financial_goals_collection))


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService(AnalyticsRepository(transactions_collection))
