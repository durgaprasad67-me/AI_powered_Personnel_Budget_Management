"""
Unit tests for duplicate detection service, fingerprinting, and multiset occurrence logic.
"""

import pytest

from app.services.importing.deduplication import (
    DeduplicationService,
    assign_occurrence_fingerprints,
    compute_file_hashes,
    compute_row_fingerprint,
    compute_row_fingerprint_base,
)


class MockCollection:
    """In-memory async mock collection for testing batched queries."""

    def __init__(self, documents: list[dict]):
        self.documents = documents

    async def find(self, query: dict, projection: dict | None = None):
        user_id = query.get("user_id")
        fp_query = query.get("fingerprint", {})
        target_fps = set(fp_query.get("$in", []))

        for doc in self.documents:
            if doc.get("user_id") == user_id and doc.get("fingerprint") in target_fps:
                yield doc

    async def find_one(self, query: dict):
        user_id = query.get("user_id")
        status = query.get("status")
        or_clauses = query.get("$or", [])

        for doc in self.documents:
            if doc.get("user_id") == user_id and doc.get("status") == status:
                for clause in or_clauses:
                    for k, v in clause.items():
                        if doc.get(k) == v:
                            return doc
        return None

    async def count_documents(self, query: dict) -> int:
        count = 0
        user_id = query.get("user_id")
        base_key = query.get("fingerprint_base")
        for doc in self.documents:
            if doc.get("user_id") == user_id and doc.get("fingerprint_base") == base_key:
                count += 1
        return count


@pytest.fixture
def dedupe():
    return DeduplicationService()


def test_fingerprint_base_excludes_category():
    fp1 = compute_row_fingerprint_base("user1", "2026-01-05", "Grocery Store", 1500.0, "expense")
    # Change category from groceries to food
    fp2 = compute_row_fingerprint_base("user1", "2026-01-05", "  grocery   store  ", 1500.0, "expense")
    assert fp1 == fp2


def test_occurrence_index_generates_distinct_fingerprints():
    base = compute_row_fingerprint_base("user1", "2026-01-05", "Coffee", 150.0, "expense")
    fp_occ1 = compute_row_fingerprint(base, occurrence=1)
    fp_occ2 = compute_row_fingerprint(base, occurrence=2)

    assert fp_occ1 != fp_occ2


def test_assign_occurrence_fingerprints_in_batch():
    rows = [
        {"date": "2026-01-05", "description": "Coffee", "amount": 150.0, "transaction_type": "expense"},
        {"date": "2026-01-05", "description": "Coffee", "amount": 150.0, "transaction_type": "expense"},
        {"date": "2026-01-05", "description": "Lunch", "amount": 350.0, "transaction_type": "expense"},
    ]
    tagged = assign_occurrence_fingerprints(rows, user_id="user1")

    assert tagged[0]["occurrence"] == 1
    assert tagged[1]["occurrence"] == 2
    assert tagged[2]["occurrence"] == 1
    assert tagged[0]["fingerprint"] != tagged[1]["fingerprint"]


def test_normalized_content_hash_matches_resaved_file():
    rows = [
        {"date": "2026-01-05", "description": "Monthly Salary", "amount": 52000.0, "transaction_type": "income"},
        {"date": "2026-01-11", "description": "Rent", "amount": 14500.0, "transaction_type": "expense"},
    ]
    raw1 = b"Date,Description,Amount,Type\n2026-01-05,Monthly Salary,52000,income\n2026-01-11,Rent,14500,expense\n"
    # Re-saved with CRLF and trailing spaces
    raw2 = b"Date,Description,Amount,Type\r\n2026-01-05, Monthly Salary ,52000,income\r\n2026-01-11, Rent ,14500,expense\r\n"

    _, norm_hash1 = compute_file_hashes(raw1, rows, "user1")
    _, norm_hash2 = compute_file_hashes(raw2, rows, "user1")

    assert norm_hash1 == norm_hash2


@pytest.mark.anyio
async def test_zero_duplicates(dedupe):
    rows = [
        {"row_number": 2, "date": "2026-01-05", "description": "Salary", "amount": 52000.0, "transaction_type": "income"},
    ]
    empty_db = MockCollection([])
    report = await dedupe.evaluate_duplicates("user1", rows, empty_db)

    assert report.decision == "no_duplicates"
    assert report.duplicate_count == 0
    assert report.new_count == 1
    assert report.actions == ["import_all"]


@pytest.mark.anyio
async def test_some_duplicates_below_threshold(dedupe):
    # 2 duplicates out of 10 rows (20% ratio <= 50%, count <= 2) -> some_duplicates_allowed
    base1 = compute_row_fingerprint_base("user1", "2026-01-01", "Row1", 100.0, "expense")
    base2 = compute_row_fingerprint_base("user1", "2026-01-02", "Row2", 200.0, "expense")
    fp1 = compute_row_fingerprint(base1, 1)
    fp2 = compute_row_fingerprint(base2, 1)

    existing_docs = [
        {"user_id": "user1", "fingerprint": fp1},
        {"user_id": "user1", "fingerprint": fp2},
    ]
    db = MockCollection(existing_docs)

    rows = [
        {"row_number": 2, "date": "2026-01-01", "description": "Row1", "amount": 100.0, "transaction_type": "expense"},
        {"row_number": 3, "date": "2026-01-02", "description": "Row2", "amount": 200.0, "transaction_type": "expense"},
    ]
    # Add 8 new rows
    for i in range(3, 11):
        rows.append({"row_number": i + 1, "date": f"2026-01-{i:02d}", "description": f"New{i}", "amount": 100.0 * i, "transaction_type": "expense"})

    report = await dedupe.evaluate_duplicates("user1", rows, db)

    assert report.decision == "some_duplicates_allowed"
    assert report.duplicate_count == 2
    assert report.new_count == 8
    assert report.ratio == 0.2
    assert "import_new_only" in report.actions


@pytest.mark.anyio
async def test_high_ratio_needs_confirmation(dedupe):
    # 6 duplicates out of 10 rows (60% ratio >= 50%) -> needs_confirmation
    existing_docs = []
    rows = []
    for i in range(1, 11):
        r = {"row_number": i + 1, "date": f"2026-01-{i:02d}", "description": f"Desc{i}", "amount": 100.0 * i, "transaction_type": "expense"}
        rows.append(r)
        if i <= 6:
            base = compute_row_fingerprint_base("user1", r["date"], r["description"], r["amount"], r["transaction_type"])
            existing_docs.append({"user_id": "user1", "fingerprint": compute_row_fingerprint(base, 1)})

    db = MockCollection(existing_docs)
    report = await dedupe.evaluate_duplicates("user1", rows, db)

    assert report.decision == "needs_confirmation"
    assert report.duplicate_count == 6
    assert report.new_count == 4
    assert len(report.sample_duplicates) == 5
    assert report.actions == ["import_new_only", "import_all", "cancel"]


@pytest.mark.anyio
async def test_all_duplicates_blocked(dedupe):
    # 3 duplicates out of 3 rows (100%) -> all_duplicates
    existing_docs = []
    rows = []
    for i in range(1, 4):
        r = {"row_number": i + 1, "date": f"2026-01-{i:02d}", "description": f"Desc{i}", "amount": 100.0, "transaction_type": "expense"}
        rows.append(r)
        base = compute_row_fingerprint_base("user1", r["date"], r["description"], r["amount"], r["transaction_type"])
        existing_docs.append({"user_id": "user1", "fingerprint": compute_row_fingerprint(base, 1)})

    db = MockCollection(existing_docs)
    report = await dedupe.evaluate_duplicates("user1", rows, db)

    assert report.decision == "all_duplicates"
    assert report.duplicate_count == 3
    assert report.new_count == 0
    assert report.actions == ["cancel"]


@pytest.mark.anyio
async def test_user_scoping_prevents_cross_user_duplicates(dedupe):
    # Same transaction belongs to user2, so user1 should NOT see it as duplicate
    base = compute_row_fingerprint_base("user2", "2026-01-05", "Salary", 52000.0, "income")
    existing_docs = [
        {"user_id": "user2", "fingerprint": compute_row_fingerprint(base, 1)}
    ]
    db = MockCollection(existing_docs)

    rows = [
        {"row_number": 2, "date": "2026-01-05", "description": "Salary", "amount": 52000.0, "transaction_type": "income"}
    ]
    report = await dedupe.evaluate_duplicates("user1", rows, db)

    assert report.decision == "no_duplicates"
    assert report.duplicate_count == 0
    assert report.new_count == 1
