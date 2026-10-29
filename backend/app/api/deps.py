from app.db.client import budgets_collection, transactions_collection
from app.repositories.budgets import BudgetRepository
from app.repositories.transactions import TransactionRepository
from app.services.budgets import BudgetService
from app.services.transactions import TransactionService


def get_transaction_service() -> TransactionService:
    return TransactionService(TransactionRepository(transactions_collection))


def get_budget_service() -> BudgetService:
    return BudgetService(BudgetRepository(budgets_collection, transactions_collection))
