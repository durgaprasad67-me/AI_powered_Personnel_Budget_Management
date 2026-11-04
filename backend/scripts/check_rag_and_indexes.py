"""Runtime audit checks for MongoDB indexes and the configured RAG store."""

import asyncio
import hashlib
import sys
from pathlib import Path
from typing import Any

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.client import close_database, get_database
from app.db.collections import BUDGETS, FINANCIAL_GOALS, TRANSACTIONS
from app.integrations.vector_store import (
    delete_documents,
    get_vector_store,
    retrieve_documents,
)
from app.services.rag.documents import index_text

COLLECTIONS = (TRANSACTIONS, BUDGETS, FINANCIAL_GOALS)
MARKER = "finsight_audit_marker_20261104"
SAMPLE_OBJECT_ID = ObjectId("000000000000000000000000")


async def print_indexes(database: Any) -> None:
    print("MONGODB INDEX INFORMATION")
    for collection_name in COLLECTIONS:
        information = await database[collection_name].index_information()
        print(f"{collection_name}: {information}")


async def explain_queries(database: Any) -> None:
    queries = {
        "transactions.insert_with_next_id": (
            TRANSACTIONS,
            {
                "find": TRANSACTIONS,
                "filter": {"_id": {"$type": "number"}},
                "sort": {"_id": -1},
                "limit": 1,
            },
        ),
        "transactions.create.get": (
            TRANSACTIONS,
            {"find": TRANSACTIONS, "filter": {"_id": 1}},
        ),
        "transactions.list.count": (
            TRANSACTIONS,
            {"find": TRANSACTIONS, "filter": {"transaction_type": "expense"}},
        ),
        "transactions.list.find": (
            TRANSACTIONS,
            {
                "find": TRANSACTIONS,
                "filter": {"transaction_type": "expense", "category": "food"},
                "sort": {"date": -1, "_id": -1},
                "limit": 50,
                "skip": 0,
            },
        ),
        "transactions.get": (
            TRANSACTIONS,
            {"find": TRANSACTIONS, "filter": {"_id": 1}},
        ),
        "transactions.update": (
            TRANSACTIONS,
            {"find": TRANSACTIONS, "filter": {"_id": 1}},
        ),
        "transactions.replace": (
            TRANSACTIONS,
            {"find": TRANSACTIONS, "filter": {"_id": 1}},
        ),
        "transactions.delete": (
            TRANSACTIONS,
            {"find": TRANSACTIONS, "filter": {"_id": 1}},
        ),
        "budgets.create.get": (
            BUDGETS,
            {"find": BUDGETS, "filter": {"_id": SAMPLE_OBJECT_ID}},
        ),
        "budgets.get": (
            BUDGETS,
            {"find": BUDGETS, "filter": {"_id": SAMPLE_OBJECT_ID}},
        ),
        "budgets.list.count": (
            BUDGETS,
            {"find": BUDGETS, "filter": {}},
        ),
        "budgets.list.find": (
            BUDGETS,
            {"find": BUDGETS, "filter": {}, "sort": {"_id": -1}, "limit": 50},
        ),
        "budgets.update": (
            BUDGETS,
            {"find": BUDGETS, "filter": {"_id": SAMPLE_OBJECT_ID}},
        ),
        "budgets.delete": (
            BUDGETS,
            {"find": BUDGETS, "filter": {"_id": SAMPLE_OBJECT_ID}},
        ),
        "budgets.spent_amount": (
            TRANSACTIONS,
            {
                "find": TRANSACTIONS,
                "filter": {
                    "date": {"$gte": "2026-01-01", "$lte": "2026-12-31"},
                    "transaction_type": "expense",
                    "category": "food",
                },
            },
        ),
        "goals.create.get": (
            FINANCIAL_GOALS,
            {"find": FINANCIAL_GOALS, "filter": {"_id": SAMPLE_OBJECT_ID}},
        ),
        "goals.get": (
            FINANCIAL_GOALS,
            {"find": FINANCIAL_GOALS, "filter": {"_id": SAMPLE_OBJECT_ID}},
        ),
        "goals.list.count": (
            FINANCIAL_GOALS,
            {"find": FINANCIAL_GOALS, "filter": {"status": "active"}},
        ),
        "goals.list.find": (
            FINANCIAL_GOALS,
            {
                "find": FINANCIAL_GOALS,
                "filter": {"status": "active"},
                "sort": {"_id": -1},
                "limit": 50,
            },
        ),
        "goals.update": (
            FINANCIAL_GOALS,
            {"find": FINANCIAL_GOALS, "filter": {"_id": SAMPLE_OBJECT_ID}},
        ),
        "goals.delete": (
            FINANCIAL_GOALS,
            {"find": FINANCIAL_GOALS, "filter": {"_id": SAMPLE_OBJECT_ID}},
        ),
        "analytics.grouped_rows": (
            TRANSACTIONS,
            {
                "aggregate": TRANSACTIONS,
                "pipeline": [
                    {
                        "$match": {
                            "date": {
                                "$gte": "2026-01-01",
                                "$lte": "2026-12-31",
                            }
                        }
                    },
                    {
                        "$group": {
                            "_id": {
                                "type": "$transaction_type",
                                "category": "$category",
                            },
                            "total": {"$sum": "$amount"},
                            "count": {"$sum": 1},
                        }
                    },
                ],
                "cursor": {},
            },
        ),
    }

    def stages(value: Any) -> list[str]:
        if isinstance(value, dict):
            found = []
            if isinstance(value.get("stage"), str):
                found.append(value["stage"])
            for child in value.values():
                found.extend(stages(child))
            return found
        if isinstance(value, list):
            found = []
            for child in value:
                found.extend(stages(child))
            return found
        return []

    print("MONGODB EXPLAIN PLANS")
    for name, (collection_name, command) in queries.items():
        try:
            explanation = await database.command(
                "explain",
                command,
                verbosity="queryPlanner",
            )
            stage_names = stages(explanation)
            stage = next(
                (name for name in stage_names if name in {"IXSCAN", "COLLSCAN"}),
                stage_names[0] if stage_names else "UNKNOWN",
            )
            flag = "COLLSCAN" if "COLLSCAN" in stage_names else ""
            print(f"{name}: winning_stage={stage} {flag}")
        except Exception as exc:
            print(f"{name}: EXPLAIN FAILED ({type(exc).__name__}: {exc})")


async def rag_smoke_test() -> None:
    print("RAG SMOKE TEST")
    settings = get_settings()
    print(
        "settings: "
        f"persist_directory={settings.chroma_persist_directory}, "
        f"collection={settings.chroma_collection_name}"
    )
    indexed_ids: list[str] = []
    try:
        text = f"This audit document contains the unique word {MARKER}."
        result = index_text(text, source=f"{MARKER}.txt")
        print(f"indexed: {result}")
        store = get_vector_store()
        stored = store.get(where={"source": f"{MARKER}.txt"})
        indexed_ids = list(stored.get("ids", []))
        documents = await retrieve_documents(MARKER, k=4)
        marker_found = any(
            MARKER in document.page_content for document, _score in documents
        )
        print(f"retrieved_chunks={len(documents)} marker_found={marker_found}")
        doc_id = hashlib.sha256(text.encode("utf-8")).hexdigest()
        for label, questions in {
            "relevant": (
                "What unique word appears in the audit document?",
                "Which marker is in the uploaded audit text?",
            ),
            "irrelevant": (
                "What is the capital of France?",
                "How do I bake a chocolate cake?",
            ),
        }.items():
            for question in questions:
                matches = await store.asimilarity_search_with_relevance_scores(
                    question,
                    k=1,
                    filter={"doc_id": doc_id},
                )
                scores = [round(score, 6) for _, score in matches]
                print(f"{label}: question={question!r} scores={scores}")
        delete_documents(indexed_ids)
        remaining = store.get(where={"source": f"{MARKER}.txt"})
        print(
            f"deleted_ids={len(indexed_ids)} remaining={len(remaining.get('ids', []))}"
        )
    finally:
        if indexed_ids:
            delete_documents(indexed_ids)


async def main() -> None:
    database = get_database()
    try:
        await print_indexes(database)
        await explain_queries(database)
        await rag_smoke_test()
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
