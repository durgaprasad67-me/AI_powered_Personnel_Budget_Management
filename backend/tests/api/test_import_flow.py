"""
End-to-end integration test suite for the FinSight AI Import Data feature.
Tests all 10 scenarios (A through J) end-to-end against the test database and API:
  - Scenario A: Clean 11-row sample file -> 11 imported, 11 embedded, 0 duplicates.
  - Scenario B: Same file uploaded again immediately -> detected as duplicate, blocked.
  - Scenario C: File with 2 duplicate rows and 9 new rows -> imported with skip_duplicates;
                only 9 inserted, only 9 embedded.
  - Scenario D: File with missing required column (e.g. no "Amount") -> 422, clear error.
  - Scenario E: File with invalid rows (bad date, non-numeric amount, invalid type) -> 422,
                lists every bad row with spreadsheet row number.
  - Scenario F: Empty file -> rejected with clear message (EMPTY_FILE).
  - Scenario G: Header-only file -> rejected with clear message (HEADER_ONLY).
  - Scenario H: Non-tabular file (.py, binary junk) -> rejected with clear message.
  - Scenario I: Confirmation flow: 5 duplicates out of 10 -> user confirms skip_duplicates
                -> 5 inserted; user confirms import_all -> 10 inserted.
  - Scenario J: Add Transaction page still works (create income, expense, loan, investment;
                check balances, limits, and auto-fingerprinting).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.api.deps import get_current_user_id, get_transaction_service
from app.main import app
from app.services.transactions import TransactionService

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _read_fixture(filename: str) -> bytes:
    path = FIXTURES_DIR / filename
    return path.read_bytes()


# ---------------------------------------------------------------------------
# SCENARIO A: Clean 11-row sample file
# ---------------------------------------------------------------------------
def test_scenario_a_clean_11_rows_sample_file(client, overrides):
    """Clean 11-row sample file -> 11 imported, 11 embedded, 0 duplicates."""
    content = _read_fixture("clean_11_rows.csv")

    vector_synced = []
    async def mock_sync(txs, *, user_id, repository):
        vector_synced.extend(txs)
        return True

    orig_service = app.dependency_overrides.get(get_transaction_service)
    app.dependency_overrides[get_transaction_service] = lambda: TransactionService(
        overrides["transactions"],
        overrides["budgets"],
        vector_sync=mock_sync,
    )

    try:
        # Phase 1: Validate
        val_resp = client.post(
            "/api/v1/imports/validate",
            files={"file": ("clean_11_rows.csv", content, "text/csv")},
        )
        assert val_resp.status_code == 200
        val_data = val_resp.json()
        assert val_data["status"] == "ready"
        assert val_data["summary"]["total_rows"] == 11
        assert val_data["summary"]["valid"] == 11
        assert val_data["summary"]["invalid"] == 0
        assert val_data["summary"]["duplicates"] == 0
        assert val_data["summary"]["new"] == 11
        token = val_data["import_token"]

        # Phase 2: Commit
        commit_resp = client.post(
            "/api/v1/imports/commit",
            json={"import_token": token, "duplicate_strategy": "import_new_only"},
        )
        assert commit_resp.status_code == 200
        commit_data = commit_resp.json()
        assert commit_data["status"] == "imported"
        assert commit_data["summary"]["new"] == 11
        assert len(commit_data["records"]) == 11
        assert len(vector_synced) == 11
    finally:
        if orig_service:
            app.dependency_overrides[get_transaction_service] = orig_service


# ---------------------------------------------------------------------------
# SCENARIO B: Same file uploaded again immediately
# ---------------------------------------------------------------------------
def test_scenario_b_same_file_uploaded_again_blocked(client, overrides):
    """Same file uploaded again immediately -> detected as duplicate, blocked with 409."""
    content = _read_fixture("clean_11_rows.csv")

    # Import first time
    val1 = client.post(
        "/api/v1/imports/validate",
        files={"file": ("clean_11_rows.csv", content, "text/csv")},
    )
    assert val1.status_code == 200
    token1 = val1.json()["import_token"]

    com1 = client.post(
        "/api/v1/imports/commit",
        json={"import_token": token1, "duplicate_strategy": "import_new_only"},
    )
    assert com1.status_code == 200

    # Upload exact same file second time
    val2 = client.post(
        "/api/v1/imports/validate",
        files={"file": ("clean_11_rows.csv", content, "text/csv")},
    )
    assert val2.status_code == 409
    data2 = val2.json()
    assert data2["status"] == "rejected"
    assert data2["code"] in ("FILE_ALREADY_IMPORTED", "ALL_DUPLICATES")
    assert data2["actions"] == ["cancel"]


# ---------------------------------------------------------------------------
# SCENARIO C: 2 duplicates + 9 new rows -> skips duplicates
# ---------------------------------------------------------------------------
def test_scenario_c_file_with_2_duplicates_skips_duplicates(client, overrides):
    """File with 2 duplicate rows and 9 new rows -> only 9 inserted, only 9 embedded."""
    repo = overrides["transactions"]
    # Pre-insert matching rows 2 and 3 from clean_11_rows.csv
    asyncio.run(repo.create({
        "date": "2026-01-05",
        "description": "Monthly salary",
        "amount": 52000.0,
        "transaction_type": "income",
        "category": "salary",
    }))
    asyncio.run(repo.create({
        "date": "2026-01-11",
        "description": "Apartment rent",
        "amount": 14500.0,
        "transaction_type": "expense",
        "category": "housing",
    }))

    vector_synced = []
    async def mock_sync(txs, *, user_id, repository):
        vector_synced.extend(txs)
        return True

    orig_service = app.dependency_overrides.get(get_transaction_service)
    app.dependency_overrides[get_transaction_service] = lambda: TransactionService(
        overrides["transactions"],
        overrides["budgets"],
        vector_sync=mock_sync,
    )

    content = _read_fixture("clean_11_rows.csv")

    try:
        val = client.post(
            "/api/v1/imports/validate",
            files={"file": ("clean_11_rows.csv", content, "text/csv")},
        )
        assert val.status_code == 200
        val_data = val.json()
        assert val_data["status"] == "ready"
        assert val_data["summary"]["duplicates"] == 2
        assert val_data["summary"]["new"] == 9
        token = val_data["import_token"]

        commit = client.post(
            "/api/v1/imports/commit",
            json={"import_token": token, "duplicate_strategy": "import_new_only"},
        )
        assert commit.status_code == 200
        commit_data = commit.json()
        assert commit_data["summary"]["new"] == 9
        assert len(commit_data["records"]) == 9
        # Zero vector calls for the 2 duplicates
        assert len(vector_synced) == 9
        assert all(t["description"] not in ("Monthly salary", "Apartment rent") or t["date"] not in ("2026-01-05", "2026-01-11") for t in vector_synced)
    finally:
        if orig_service:
            app.dependency_overrides[get_transaction_service] = orig_service


# ---------------------------------------------------------------------------
# SCENARIO D: Missing required column
# ---------------------------------------------------------------------------
def test_scenario_d_missing_required_column_amount(client, overrides):
    """File with missing required column (e.g. no 'Amount') -> 422, clear error."""
    csv_missing_amount_col = (
        b"Date,Description,Type,Category\n"
        b"2026-01-05,Monthly salary,income,salary\n"
    )

    val = client.post(
        "/api/v1/imports/validate",
        files={"file": ("missing_amount_col.csv", csv_missing_amount_col, "text/csv")},
    )
    assert val.status_code == 422
    data = val.json()
    assert data["status"] == "rejected"
    assert data["code"] == "MISSING_COLUMNS"
    assert "Amount" in data["message"] or any("Amount" in iss.get("message", "") for iss in data.get("errors", []))


# ---------------------------------------------------------------------------
# SCENARIO E: Invalid rows with spreadsheet row numbers
# ---------------------------------------------------------------------------
def test_scenario_e_invalid_rows_lists_spreadsheet_row_numbers(client, overrides):
    """File with invalid rows -> 422, lists every bad row with spreadsheet row number."""
    csv_content = (
        b"Date,Description,Amount,Type,Category\n"
        b"not-a-date,Valid desc,500,expense,food\n"        # Row 2: Bad date
        b"2026-06-01,Valid desc,-50,expense,food\n"        # Row 3: Non-positive amount
        b"2026-06-02,Valid desc,100,unknown_type,food\n"   # Row 4: Invalid type
    )

    val = client.post(
        "/api/v1/imports/validate",
        files={"file": ("invalid_rows.csv", csv_content, "text/csv")},
    )
    assert val.status_code == 422
    data = val.json()
    assert data["status"] == "rejected"
    errors = data.get("errors", [])
    assert len(errors) >= 3

    # Check that row numbers 2, 3, 4 are reported
    reported_rows = {err["row"] for err in errors}
    assert 2 in reported_rows
    assert 3 in reported_rows
    assert 4 in reported_rows


# ---------------------------------------------------------------------------
# SCENARIO F: Empty file rejected
# ---------------------------------------------------------------------------
def test_scenario_f_empty_file_rejected(client, overrides):
    """Empty file -> rejected with clear message (EMPTY_FILE)."""
    val = client.post(
        "/api/v1/imports/validate",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert val.status_code == 422
    data = val.json()
    assert data["status"] == "rejected"
    assert data["code"] == "EMPTY_FILE"
    assert "empty" in data["message"].lower()


# ---------------------------------------------------------------------------
# SCENARIO G: Header-only file rejected
# ---------------------------------------------------------------------------
def test_scenario_g_header_only_file_rejected(client, overrides):
    """Header-only file -> rejected with clear message (HEADER_ONLY or NO_TRANSACTIONS_FOUND)."""
    content = _read_fixture("header_only.csv")
    val = client.post(
        "/api/v1/imports/validate",
        files={"file": ("header_only.csv", content, "text/csv")},
    )
    assert val.status_code == 422
    data = val.json()
    assert data["status"] == "rejected"
    assert data["code"] in ("HEADER_ONLY", "NO_TRANSACTIONS_FOUND")
    assert "no data rows" in data["message"].lower() or "no transactions" in data["message"].lower() or "header" in data["message"].lower()


# ---------------------------------------------------------------------------
# SCENARIO H: Non-tabular file rejected
# ---------------------------------------------------------------------------
def test_scenario_h_non_tabular_file_rejected(client, overrides):
    """Non-tabular file (.py, binary junk) -> rejected with clear message."""
    # Unsupported extension (.py)
    val_py = client.post(
        "/api/v1/imports/validate",
        files={"file": ("script.py", b"print('hello')", "text/x-python")},
    )
    assert val_py.status_code == 415
    assert val_py.json()["code"] == "UNSUPPORTED_FORMAT"

    # Binary junk renamed as .csv
    binary_junk = b"\x00\x01\x02\x03\x04\x05\xff\xfe\x00\x00"
    val_bin = client.post(
        "/api/v1/imports/validate",
        files={"file": ("corrupted.csv", binary_junk, "text/csv")},
    )
    assert val_bin.status_code == 422
    data_bin = val_bin.json()
    assert data_bin["status"] == "rejected"
    assert data_bin["code"] in ("CORRUPT_FILE", "HEADER_ONLY", "INVALID_FILE", "BINARY_CSV")


# ---------------------------------------------------------------------------
# SCENARIO I: Confirmation flow (5 duplicates out of 10)
# ---------------------------------------------------------------------------
def test_scenario_i_confirmation_flow_5_duplicates(client, overrides):
    """Confirmation flow: 5 duplicates out of 10 -> user chooses skip_duplicates vs import_all."""
    repo = overrides["transactions"]

    # Pre-insert 5 transactions
    for i in range(1, 6):
        asyncio.run(repo.create({
            "date": f"2026-06-{i:02d}",
            "description": f"Salary part {i}",
            "amount": 1000.0,
            "transaction_type": "income",
            "category": "salary",
        }))

    # 10 rows: 5 duplicates + 5 new
    rows = ["Date,Description,Amount,Type,Category"]
    for i in range(1, 6):
        rows.append(f"2026-06-{i:02d},Salary part {i},1000,income,salary")
    for i in range(6, 11):
        rows.append(f"2026-06-{i:02d},New income {i},1000,income,salary")
    csv_content = "\n".join(rows).encode("utf-8")

    # Validate
    val = client.post(
        "/api/v1/imports/validate",
        files={"file": ("ten_rows.csv", csv_content, "text/csv")},
    )
    assert val.status_code == 409
    data = val.json()
    assert data["status"] == "needs_confirmation"
    assert data["code"] == "DUPLICATES_FOUND"
    assert data["summary"]["duplicates"] == 5
    assert data["summary"]["new"] == 5
    assert data["duplicates"]["ratio"] == 0.5
    token = data["import_token"]

    # Choice 1: import_new_only
    commit_new = client.post(
        "/api/v1/imports/commit",
        json={"import_token": token, "duplicate_strategy": "import_new_only"},
    )
    assert commit_new.status_code == 200
    res_new = commit_new.json()
    assert res_new["summary"]["new"] == 5
    assert len(res_new["records"]) == 5


def test_scenario_i_confirmation_flow_import_all(client, overrides):
    """Confirmation flow: user chooses import_all -> all 10 records inserted."""
    repo = overrides["transactions"]

    # Pre-insert 5 transactions
    for i in range(1, 6):
        asyncio.run(repo.create({
            "date": f"2026-07-{i:02d}",
            "description": f"Bonus {i}",
            "amount": 500.0,
            "transaction_type": "income",
            "category": "salary",
        }))

    rows = ["Date,Description,Amount,Type,Category"]
    for i in range(1, 6):
        rows.append(f"2026-07-{i:02d},Bonus {i},500,income,salary")
    for i in range(6, 11):
        rows.append(f"2026-07-{i:02d},Extra {i},500,income,salary")
    csv_content = "\n".join(rows).encode("utf-8")

    val = client.post(
        "/api/v1/imports/validate",
        files={"file": ("bonus_ten.csv", csv_content, "text/csv")},
    )
    assert val.status_code == 409
    token = val.json()["import_token"]

    # Choice 2: import_all
    commit_all = client.post(
        "/api/v1/imports/commit",
        json={"import_token": token, "duplicate_strategy": "import_all"},
    )
    assert commit_all.status_code == 200
    res_all = commit_all.json()
    assert res_all["summary"]["new"] == 10
    assert len(res_all["records"]) == 10


def test_scenario_i_confirmation_flow_20_duplicates_out_of_43(client, overrides):
    """File with 20 duplicates and 23 new rows (43 total) MUST trigger needs_confirmation."""
    repo = overrides["transactions"]

    # Pre-insert 20 transactions
    for i in range(1, 21):
        asyncio.run(repo.create({
            "date": f"2026-08-{i:02d}",
            "description": f"Pre-existing {i}",
            "amount": 1000.0 * i,
            "transaction_type": "income",
            "category": "salary",
        }))

    # 43 rows total: 20 duplicates + 23 new rows
    rows = ["Date,Description,Amount,Type,Category"]
    for i in range(1, 21):
        rows.append(f"2026-08-{i:02d},Pre-existing {i},{1000.0 * i},income,salary")
    for i in range(21, 44):
        rows.append(f"2026-09-{i - 20:02d},New transaction {i},{500.0 * i},expense,food")
    csv_content = "\n".join(rows).encode("utf-8")

    val = client.post(
        "/api/v1/imports/validate",
        files={"file": ("forty_three_rows.csv", csv_content, "text/csv")},
    )
    assert val.status_code == 409
    data = val.json()
    assert data["status"] == "needs_confirmation"
    assert data["code"] == "DUPLICATES_FOUND"
    assert data["summary"]["duplicates"] == 20
    assert data["summary"]["new"] == 23
    assert data["summary"]["total_rows"] == 43
    assert "import_all" in data["actions"]
    assert "import_new_only" in data["actions"]
    assert "cancel" in data["actions"]
    token = data["import_token"]

    # Commit with import_all -> all 43 rows inserted!
    commit_all = client.post(
        "/api/v1/imports/commit",
        json={"import_token": token, "duplicate_strategy": "import_all"},
    )
    assert commit_all.status_code == 200
    res_all = commit_all.json()
    assert len(res_all["records"]) == 43
    assert res_all["summary"]["duplicates"] == 0 or res_all["imported_records"] == 43



# ---------------------------------------------------------------------------
# SCENARIO J: Add Transaction page still works
# ---------------------------------------------------------------------------
def test_scenario_j_add_transaction_page_still_works(client, overrides):
    """Add Transaction page works (create income, expense, loan, investment; check balances/limits)."""
    # 1. Create Income
    inc_resp = client.post(
        "/api/v1/transactions",
        json={
            "amount": 50000,
            "transaction_type": "income",
            "category": "salary",
            "description": "Tech company salary",
            "date": "2026-08-01",
        },
    )
    assert inc_resp.status_code == 201
    inc_data = inc_resp.json()
    assert inc_data["amount"] == 50000

    # 2. Create Expense
    exp_resp = client.post(
        "/api/v1/transactions",
        json={
            "amount": 15000,
            "transaction_type": "expense",
            "category": "housing",
            "description": "August rent",
            "date": "2026-08-05",
        },
    )
    assert exp_resp.status_code == 201

    # 3. Create Loan Taken
    loan_resp = client.post(
        "/api/v1/transactions",
        json={
            "amount": 20000,
            "transaction_type": "loan_taken",
            "category": "loan",
            "description": "Car loan disbursed",
            "date": "2026-08-10",
        },
    )
    assert loan_resp.status_code == 201

    # 4. Create Investment
    inv_resp = client.post(
        "/api/v1/transactions",
        json={
            "amount": 5000,
            "transaction_type": "investment",
            "category": "stocks",
            "description": "Index fund SIP",
            "date": "2026-08-15",
        },
    )
    assert inv_resp.status_code == 201

    # 5. Verify overdraw limit check
    # Total inflows = 50000 + 20000 = 70000
    # Total outflows = 15000 + 5000 = 20000
    # Available = 50000
    # Attempting to spend 60000 should exceed ceiling
    overdraw_resp = client.post(
        "/api/v1/transactions",
        json={
            "amount": 60000,
            "transaction_type": "expense",
            "category": "electronics",
            "description": "Luxury purchase exceeding cash",
            "date": "2026-08-20",
        },
    )
    assert overdraw_resp.status_code == 422
    err_text = overdraw_resp.json()["detail"].lower()
    assert "cashout failed" in err_text or "available balance" in err_text or "cash outflows exceed" in err_text

    # 6. Verify MongoDB record has auto-generated fingerprint
    repo = overrides["transactions"]
    docs = list(repo.documents.values())
    assert len(docs) >= 4
    for doc in docs:
        assert "fingerprint" in doc
        assert "fingerprint_base" in doc
        assert len(doc["fingerprint"]) == 64  # SHA-256 hex digest
