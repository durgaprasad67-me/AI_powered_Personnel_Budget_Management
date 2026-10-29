from app.db.client import transactions_collection
from app.repositories.transactions import TransactionRepository
from app.services.transactions import TransactionService


def get_transaction_service() -> TransactionService:
    return TransactionService(TransactionRepository(transactions_collection))
