from typing import Any

from app.core.exceptions import InvalidInputError, NotFoundError
from app.domain.normalization import clean_lower, normalize_type
from app.domain.transaction_types import TRANSACTION_TYPES
from app.repositories.transactions import TransactionRepository
from app.schemas.transactions import TransactionCreate, TransactionUpdate


class TransactionService:
    def __init__(self, repository: TransactionRepository):
        self.repository = repository

    async def create(self, transaction: TransactionCreate) -> dict[str, Any]:
        saved = await self.repository.create(transaction.model_dump(mode="json"))
        if saved is None:
            raise RuntimeError("Failed to retrieve the created transaction.")
        return saved

    async def list(
        self,
        *,
        transaction_type: str | None,
        category: str | None,
        start_date: str | None,
        end_date: str | None,
        limit: int,
        skip: int,
    ) -> dict[str, Any]:
        filters: dict[str, Any] = {}

        if transaction_type:
            normalized_type = normalize_type(transaction_type)
            if normalized_type not in TRANSACTION_TYPES:
                raise InvalidInputError(
                    "transaction_type must be one of: "
                    + ", ".join(TRANSACTION_TYPES)
                )
            filters["transaction_type"] = normalized_type

        if category:
            filters["category"] = clean_lower(category)

        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            filters["date"] = date_filter

        items, total = await self.repository.list(
            filters,
            limit=limit,
            skip=skip,
        )
        return {"items": items, "total": total, "limit": limit, "skip": skip}

    async def get(self, transaction_id: int) -> dict[str, Any]:
        transaction = await self.repository.get(transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found.")
        return transaction

    async def update(
        self,
        transaction_id: int,
        updates: TransactionUpdate,
    ) -> dict[str, Any]:
        changes = updates.model_dump(mode="json", exclude_unset=True)
        if not changes:
            raise InvalidInputError("No changes provided.", status_code=400)
        if any(value is None for value in changes.values()):
            raise InvalidInputError("Updated fields cannot be null.")

        transaction = await self.repository.update(transaction_id, changes)
        if transaction is None:
            raise NotFoundError("Transaction not found.")
        return transaction

    async def replace(
        self,
        transaction_id: int,
        transaction: TransactionCreate,
    ) -> dict[str, Any]:
        replaced = await self.repository.replace(
            transaction_id,
            transaction.model_dump(mode="json"),
        )
        if replaced is None:
            raise NotFoundError("Transaction not found.")
        return replaced

    async def delete(self, transaction_id: int) -> None:
        if not await self.repository.delete(transaction_id):
            raise NotFoundError("Transaction not found.")
