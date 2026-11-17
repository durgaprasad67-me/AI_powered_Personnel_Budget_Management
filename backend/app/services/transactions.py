from __future__ import annotations

import asyncio
from datetime import date as Date
import logging
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import InvalidInputError, NotFoundError
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.domain.dates import today_ist
from app.domain.normalization import clean_lower, normalize_type
from app.domain.transaction_types import (
    CASH_IN_TYPES,
    CASH_OUT_TYPES,
    TRANSACTION_TYPES,
)
from app.repositories.transactions import TransactionRepository
from app.schemas.transactions import TransactionCreate, TransactionUpdate
from app.services.rag.transaction_indexing import (
    delete_transaction_best_effort,
    sync_transactions_best_effort,
)

logger = logging.getLogger(__name__)


class TransactionService:
    def __init__(
        self,
        repository: TransactionRepository,
        budget_repository=None,
        *,
        vector_sync=sync_transactions_best_effort,
        vector_delete=delete_transaction_best_effort,
    ):
        self.repository = repository
        self.budget_repository = budget_repository
        self.vector_sync = vector_sync
        self.vector_delete = vector_delete
        self._user_locks: dict[str, asyncio.Lock] = {}

    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    def _check_inflow_ceiling(self, transaction: dict[str, Any]) -> None:
        """Validate dynamic ceiling for inflows from central settings."""
        kind = transaction.get("transaction_type")
        if kind in CASH_IN_TYPES:
            settings = get_settings()
            amount = float(transaction.get("amount", 0))
            if amount > settings.max_inflow_amount:
                raise InvalidInputError(
                    f"Inflow amount exceeds the maximum permitted limit of ₹{settings.max_inflow_amount:,.2f}.",
                    field="amount",
                )

    async def _check_duplicate(
        self,
        transaction: dict[str, Any],
        *,
        user_id: str,
    ) -> None:
        """Reject identical transaction submitted within duplicate window."""
        if hasattr(self.repository, "find_recent_identical"):
            settings = get_settings()
            is_dup = await self.repository.find_recent_identical(
                user_id=user_id,
                amount=float(transaction["amount"]),
                category=transaction["category"],
                date=str(transaction["date"]),
                transaction_type=transaction["transaction_type"],
                within_seconds=settings.duplicate_window_seconds,
            )
            if is_dup:
                raise InvalidInputError(
                    "Duplicate transaction detected. Please wait a few seconds before resubmitting.",
                    status_code=422,
                )

    async def _check_budget(
        self,
        transaction: dict[str, Any],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
        exclude_id=None,
        additional_transactions: list[dict[str, Any]] | None = None,
    ) -> str | None:
        """Enforce monthly budget rule for cash-outflows."""
        if self.budget_repository is None:
            return None

        kind = transaction.get("transaction_type")
        if kind not in CASH_OUT_TYPES:
            return None

        # Check monthly budget status
        if hasattr(self.budget_repository, "get_monthly_budget_status"):
            status = await self.budget_repository.get_monthly_budget_status(
                date=str(transaction.get("date", "")),
                category=transaction.get("category"),
                transaction_type=kind,
                user_id=user_id,
                exclude_transaction_id=exclude_id,
            )
            amount = float(transaction.get("amount", 0))
            if status.get("has_budget"):
                remaining = float(status.get("remaining_budget", 0.0))
                month = status.get("month", "the selected month")
                if round(amount, 2) > round(remaining, 2):
                    raise InvalidInputError(
                        f"Remaining budget for {month} is ₹{remaining:,.2f}; this transaction is ₹{amount:,.2f}.",
                        field="amount",
                    )
                return None
            else:
                # No budget set for this month -> allow, but return warning
                return status.get("warning")

        # Fallback to legacy budget_violations if fake repo doesn't have method
        violations = await self.budget_repository.budget_violations(
            date=str(transaction["date"]),
            category=transaction["category"],
            transaction_type=transaction["transaction_type"],
            amount=float(transaction["amount"]),
            exclude_transaction_id=exclude_id,
            additional_transactions=additional_transactions or [],
        )
        if violations:
            details = "; ".join(
                f'{item["name"]}: {item["projected"]:,.2f} used of '
                f'{item["amount"]:,.2f}'
                for item in violations
            )
            raise InvalidInputError(
                f"Transaction exceeds the budget limit ({details}). "
                "Reduce the amount or adjust the budget before saving.",
                field="amount",
            )
        return None

    async def _check_cash_balance(
        self,
        transaction: dict[str, Any],
        *,
        user_id: str,
        exclude_id=None,
    ) -> None:
        if transaction.get("transaction_type") not in CASH_OUT_TYPES:
            return

        items: list[dict[str, Any]] = []
        skip = 0
        while True:
            page, total = await self.repository.list(
                {},
                user_id=user_id,
                limit=100,
                skip=skip,
            )
            items.extend(page)
            if not page or len(items) >= total:
                break
            skip += len(page)

        existing = [item for item in items if item.get("id") != exclude_id]
        total_cash_in = sum(
            float(item.get("amount", 0))
            for item in existing
            if item.get("transaction_type") in CASH_IN_TYPES
        )
        total_cash_out = sum(
            float(item.get("amount", 0))
            for item in existing
            if item.get("transaction_type") in CASH_OUT_TYPES
        )
        cashout_amount = float(transaction.get("amount", 0))

        if cashout_amount <= 0:
            raise InvalidInputError(
                "Cashout failed! Please enter an amount greater than ₹0.00."
            )
        available_cash = round(total_cash_in - total_cash_out, 2)
        if available_cash <= 0:
            raise InvalidInputError(
                "Cashout failed! Your available balance is "
                f"₹{available_cash:,.2f}. "
                "You don't have enough available funds. "
                "Please add a cash inflow before cashing out."
            )
        if round(cashout_amount, 2) > available_cash:
            raise InvalidInputError(
                "Cashout failed! Your available balance is "
                f"₹{available_cash:,.2f}, but you are trying to "
                f"cash out ₹{cashout_amount:,.2f}. "
                "You don't have enough available funds. "
                "Please enter an amount within your current balance."
            )

    async def validate_import_batch(
        self,
        transactions: list[TransactionCreate],
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> None:
        """Validate an import against current cash and all applicable budgets."""
        if not transactions:
            return

        existing: list[dict[str, Any]] = []
        skip = 0
        while True:
            page, total = await self.repository.list(
                {}, user_id=user_id, limit=100, skip=skip
            )
            existing.extend(page)
            if not page or len(existing) >= total:
                break
            skip += len(page)

        available_cash = sum(
            float(item.get("amount", 0))
            * (1 if item.get("transaction_type") in CASH_IN_TYPES else -1)
            for item in existing
            if item.get("transaction_type") in CASH_IN_TYPES + CASH_OUT_TYPES
        )
        imported_cash_delta = sum(
            float(item.amount)
            * (1 if item.transaction_type in CASH_IN_TYPES else -1)
            for item in transactions
            if item.transaction_type in CASH_IN_TYPES + CASH_OUT_TYPES
        )
        projected_cash = round(available_cash + imported_cash_delta, 2)
        if projected_cash < 0:
            raise InvalidInputError(
                "Import cancelled because the imported cash outflows exceed "
                f"available cash inflows by ₹{abs(projected_cash):,.2f}. "
                "No transactions were imported."
            )

        staged: list[dict[str, Any]] = []
        for transaction in transactions:
            document = transaction.model_dump(mode="json")
            await self._check_budget(
                document,
                additional_transactions=staged,
            )
            staged.append(document)

    async def _sync_after_write(
        self,
        transaction: dict[str, Any],
        user_id: str,
    ) -> None:
        try:
            await self.vector_sync(
                [transaction],
                user_id=user_id,
                repository=self.repository,
            )
        except Exception as exc:
            # Mongo is the source of truth; vector failures must not roll it back.
            logger.warning(
                "Transaction vector sync failed after Mongo write",
                extra={"error_type": type(exc).__name__},
            )

    async def create(
        self,
        transaction: TransactionCreate,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any]:
        document = transaction.model_dump(mode="json")
        document["user_id"] = user_id

        # Race-safe locking per user to prevent concurrent requests exceeding budget
        lock = self._get_user_lock(user_id)
        async with lock:
            await self._check_duplicate(document, user_id=user_id)
            self._check_inflow_ceiling(document)
            await self._check_cash_balance(document, user_id=user_id)
            warning = await self._check_budget(document, user_id=user_id)
            if warning:
                document["warning"] = warning

            saved = await self.repository.create(document, user_id=user_id)
            if saved is None:
                raise RuntimeError("Failed to retrieve the created transaction.")
            if warning and "warning" not in saved:
                saved["warning"] = warning
            await self._sync_after_write(saved, user_id)
            return saved

    async def get_budget_limit(
        self,
        *,
        transaction_type: str,
        category: str | None = None,
        date: str | None = None,
        exclude_id: int | None = None,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any]:
        """Return dynamic ceiling and remaining budget for frontend form hints & max limits."""
        settings = get_settings()
        normalized_type = normalize_type(transaction_type)
        tx_date = date or str(today_ist())
        dt = Date.fromisoformat(str(tx_date)[:10])
        month_name = dt.strftime("%B %Y")

        if normalized_type in CASH_IN_TYPES:
            return {
                "has_budget": False,
                "month": month_name,
                "allocated_budget": None,
                "spent_amount": 0.0,
                "remaining_budget": None,
                "max_allowed": settings.max_inflow_amount,
                "warning": None,
            }

        if self.budget_repository is not None and hasattr(
            self.budget_repository, "get_monthly_budget_status"
        ):
            clean_cat = clean_lower(category) if category else None
            return await self.budget_repository.get_monthly_budget_status(
                date=tx_date,
                category=clean_cat,
                transaction_type=normalized_type,
                user_id=user_id,
                exclude_transaction_id=exclude_id,
            )

        return {
            "has_budget": False,
            "month": month_name,
            "allocated_budget": None,
            "spent_amount": 0.0,
            "remaining_budget": None,
            "max_allowed": settings.max_outflow_amount_without_budget,
            "warning": f"No budget set for {month_name}.",
        }

    async def list(
        self,
        *,
        transaction_type: str | None,
        category: str | None,
        start_date: str | None,
        end_date: str | None,
        limit: int,
        skip: int,
        user_id: str = DEFAULT_CURRENT_USER_ID,
        sort_descending: bool = True,
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
            user_id=user_id,
            limit=limit,
            skip=skip,
            sort_descending=sort_descending,
        )
        return {"items": items, "total": total, "limit": limit, "skip": skip}

    async def get(
        self,
        transaction_id: int,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any]:
        transaction = await self.repository.get(transaction_id, user_id=user_id)
        if transaction is None:
            raise NotFoundError("Transaction not found.")
        return transaction

    async def update(
        self,
        transaction_id: int,
        updates: TransactionUpdate,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any]:
        changes = updates.model_dump(mode="json", exclude_unset=True)
        if not changes:
            raise InvalidInputError("No changes provided.", status_code=400)
        if any(value is None for value in changes.values()):
            raise InvalidInputError("Updated fields cannot be null.")

        lock = self._get_user_lock(user_id)
        async with lock:
            current = await self.get(transaction_id, user_id=user_id)
            projected = {**current, **changes}
            self._check_inflow_ceiling(projected)
            await self._check_cash_balance(
                projected,
                user_id=user_id,
                exclude_id=transaction_id,
            )
            warning = await self._check_budget(
                projected,
                user_id=user_id,
                exclude_id=transaction_id,
            )
            if warning:
                changes["warning"] = warning
            transaction = await self.repository.update(
                transaction_id,
                changes,
                user_id=user_id,
            )
            if transaction is None:
                raise NotFoundError("Transaction not found.")
            if warning and "warning" not in transaction:
                transaction["warning"] = warning
            await self._sync_after_write(transaction, user_id)
            return transaction

    async def replace(
        self,
        transaction_id: int,
        transaction: TransactionCreate,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> dict[str, Any]:
        document = transaction.model_dump(mode="json")
        document["user_id"] = user_id

        lock = self._get_user_lock(user_id)
        async with lock:
            self._check_inflow_ceiling(document)
            await self._check_cash_balance(
                document,
                user_id=user_id,
                exclude_id=transaction_id,
            )
            warning = await self._check_budget(
                document,
                user_id=user_id,
                exclude_id=transaction_id,
            )
            if warning:
                document["warning"] = warning
            replaced = await self.repository.replace(
                transaction_id,
                document,
                user_id=user_id,
            )
            if replaced is None:
                raise NotFoundError("Transaction not found.")
            if warning and "warning" not in replaced:
                replaced["warning"] = warning
            await self._sync_after_write(replaced, user_id)
            return replaced

    async def delete(
        self,
        transaction_id: int,
        *,
        user_id: str = DEFAULT_CURRENT_USER_ID,
    ) -> None:
        if not await self.repository.delete(transaction_id, user_id=user_id):
            raise NotFoundError("Transaction not found.")
        try:
            await self.vector_delete(transaction_id, user_id=user_id)
        except Exception as exc:
            logger.warning(
                "Transaction vector deletion failed after Mongo delete",
                extra={"error_type": type(exc).__name__},
            )
