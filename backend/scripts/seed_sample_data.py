"""Insert the bundled synthetic datasets into the configured MongoDB database."""

import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db.client import close_database, get_database
from app.db.collections import BUDGETS, FINANCIAL_GOALS, TRANSACTIONS
from app.schemas.budgets import BudgetCreate
from app.schemas.goals import FinancialGoalCreate
from app.services.importing.service import extract_transactions, validate_rows

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SEED_SOURCE = "finsight-sample-2026-10"


async def seed() -> None:
    database = get_database()
    await database.command("ping")

    transactions_collection = database[TRANSACTIONS]
    budgets_collection = database[BUDGETS]
    goals_collection = database[FINANCIAL_GOALS]

    for collection in (
        transactions_collection,
        budgets_collection,
        goals_collection,
    ):
        await collection.delete_many({"seed_source": SEED_SOURCE})

    transaction_rows = extract_transactions(
        "transactions_sample.csv",
        (DATA_DIR / "transactions_sample.csv").read_bytes(),
    )
    transactions = [
        {**transaction.model_dump(mode="json"), "seed_source": SEED_SOURCE}
        for transaction in validate_rows(transaction_rows)
    ]
    if transactions:
        await transactions_collection.insert_many(transactions)

    budget_payloads = json.loads(
        (DATA_DIR / "budgets_sample.json").read_text(encoding="utf-8")
    )
    budgets = [
        {**BudgetCreate.model_validate(payload).model_dump(mode="json"),
         "seed_source": SEED_SOURCE}
        for payload in budget_payloads
    ]
    if budgets:
        await budgets_collection.insert_many(budgets)

    goal_payloads = json.loads(
        (DATA_DIR / "goals_sample.json").read_text(encoding="utf-8")
    )
    goals = [
        {
            **FinancialGoalCreate.model_validate(payload).model_dump(mode="json"),
            "status": "active",
            "seed_source": SEED_SOURCE,
        }
        for payload in goal_payloads
    ]
    if goals:
        await goals_collection.insert_many(goals)

    print(
        f"Seeded {len(transactions)} transactions, "
        f"{len(budgets)} budgets, and {len(goals)} goals "
        f"into database '{database.name}'."
    )
    await close_database()


if __name__ == "__main__":
    asyncio.run(seed())
