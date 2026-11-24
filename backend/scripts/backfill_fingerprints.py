"""
Idempotent backfill script to populate transaction fingerprints for existing database records.
Usage:
    python scripts/backfill_fingerprints.py
"""

import asyncio
import os
import sys

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.db.client import close_database, get_database
from app.db.collections import TRANSACTIONS
from app.services.importing.deduplication import (
    compute_row_fingerprint,
    compute_row_fingerprint_base,
)


async def backfill_fingerprints() -> int:
    db = get_database()
    collection = db[TRANSACTIONS]

    query = {
        "$or": [
            {"fingerprint": {"$exists": False}},
            {"fingerprint": None},
        ]
    }

    cursor = collection.find(query).sort([("_id", 1)])
    missing_docs = [doc async for doc in cursor]

    if not missing_docs:
        print("All transactions already have fingerprints. 0 records updated.")
        return 0

    print(f"Found {len(missing_docs)} transaction(s) missing fingerprints. Starting backfill...")

    occurrence_tracker: dict[tuple[str, str], int] = {}
    updated_count = 0

    for doc in missing_docs:
        doc_id = doc["_id"]
        user_id = doc.get("user_id") or DEFAULT_CURRENT_USER_ID
        date_str = str(doc.get("date", ""))
        desc = str(doc.get("description", ""))
        amount = float(doc.get("amount", 0.0))
        tx_type = str(doc.get("transaction_type") or doc.get("type") or "expense")

        base_key = compute_row_fingerprint_base(user_id, date_str, desc, amount, tx_type)
        tracker_key = (user_id, base_key)

        if tracker_key not in occurrence_tracker:
            # Query existing count in DB that already have this base key
            existing_count = await collection.count_documents(
                {"user_id": user_id, "fingerprint_base": base_key}
            )
            occurrence_tracker[tracker_key] = existing_count

        occurrence_tracker[tracker_key] += 1
        occ = occurrence_tracker[tracker_key]
        fp = compute_row_fingerprint(base_key, occ)

        await collection.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "fingerprint_base": base_key,
                    "occurrence": occ,
                    "fingerprint": fp,
                }
            },
        )
        updated_count += 1

    print(f"Backfill complete: successfully updated {updated_count} transaction(s).")
    return updated_count


async def main():
    try:
        await backfill_fingerprints()
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
