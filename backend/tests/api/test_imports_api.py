def test_import_preflight_includes_loan_inflows_and_blocks_overdraw(client, overrides):
    income = client.post(
        "/api/v1/transactions",
        json={
            "amount": 100,
            "transaction_type": "income",
            "category": "salary",
            "description": "Salary",
            "date": "2026-06-01",
        },
    )
    assert income.status_code == 201

    overdraw = client.post(
        "/api/v1/imports",
        files={
            "file": (
                "overdraw.csv",
                (
                    b"date,amount,transaction_type,category,description\n"
                    b"2026-06-02,101,expense,food,Lunch\n"
                ),
                "text/csv",
            )
        },
    )
    assert overdraw.status_code == 422
    assert "cash outflows exceed" in overdraw.json()["detail"]
    assert client.get("/api/v1/transactions").json()["total"] == 1

    funded_by_loan = client.post(
        "/api/v1/imports",
        files={
            "file": (
                "loan-funded.csv",
                (
                    b"date,amount,transaction_type,category,description\n"
                    b"2026-06-03,50,loan_taken,loan,Loan disbursed\n"
                    b"2026-06-04,120,expense,food,Household purchase\n"
                ),
                "text/csv",
            )
        },
    )
    assert funded_by_loan.status_code == 201
    assert funded_by_loan.json()["imported_records"] == 2
    records = funded_by_loan.json().get("records", [])
    assert len(records) == 2
    assert records[0]["category"] == "loan"
    assert records[0]["amount"] == 50.0
    assert records[0]["transaction_type"] == "loan_taken"
    assert records[1]["category"] == "food"
    assert records[1]["amount"] == 120.0
    assert records[1]["transaction_type"] == "expense"
    transactions = client.get("/api/v1/transactions").json()["items"]
    assert {item["transaction_type"] for item in transactions} == {
        "income",
        "loan_taken",
        "expense",
    }


def test_partial_import_dialog_receives_valid_row_count(client, overrides):
    csv_content = (
        b"date,amount,transaction_type,category,description\n"
        b"2026-06-03,25,expense,food,Lunch\n"
        b"2026-06-04,not-an-amount,expense,food,Invalid row\n"
    )
    response = client.post(
        "/api/v1/imports",
        files={"file": ("mixed.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["valid_records"] == 1
    assert response.json()["detail"]["total_records"] == 2


def test_two_phase_validate_and_commit_clean_sample(client, overrides):
    sample_csv = (
        b"Date,Description,Amount,Type,Category\n"
        b"2026-01-05,Monthly salary,52000,income,salary\n"
        b"2026-01-11,Apartment rent,14500,expense,housing\n"
        b"2026-02-03,Freelance website work,8200,income,freelance\n"
    )
    val_resp = client.post(
        "/api/v1/imports/validate",
        files={"file": ("clean.csv", sample_csv, "text/csv")},
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["status"] == "ready"
    assert val_data["summary"]["valid"] == 3
    assert val_data["import_token"] is not None

    token = val_data["import_token"]

    commit_resp = client.post(
        "/api/v1/imports/commit",
        json={"import_token": token, "duplicate_strategy": "import_new_only"},
    )
    assert commit_resp.status_code == 200
    commit_data = commit_resp.json()
    assert commit_data["status"] == "imported"
    assert commit_data["summary"]["new"] == 3
    assert len(commit_data["records"]) == 3

    # Idempotency / session cleanup test: second commit with same token must fail
    second_commit = client.post(
        "/api/v1/imports/commit",
        json={"import_token": token, "duplicate_strategy": "import_new_only"},
    )
    assert second_commit.status_code == 422
    assert second_commit.json()["code"] == "SESSION_EXPIRED"


def test_two_phase_duplicate_detection_all_duplicates(client, overrides):
    sample_csv = (
        b"Date,Description,Amount,Type,Category\n"
        b"2026-01-05,Monthly salary,52000,income,salary\n"
    )
    # First import
    res1 = client.post(
        "/api/v1/imports/validate",
        files={"file": ("salary.csv", sample_csv, "text/csv")},
    )
    assert res1.status_code == 200
    token1 = res1.json()["import_token"]
    commit1 = client.post(
        "/api/v1/imports/commit",
        json={"import_token": token1, "duplicate_strategy": "import_new_only"},
    )
    assert commit1.status_code == 200

    # Second validate of same file content
    res2 = client.post(
        "/api/v1/imports/validate",
        files={"file": ("salary.csv", sample_csv, "text/csv")},
    )
    assert res2.status_code == 409
    data2 = res2.json()
    assert data2["status"] == "rejected"
    assert data2["code"] in ("ALL_DUPLICATES", "FILE_ALREADY_IMPORTED")
    assert data2["actions"] == ["cancel"]


def test_validation_error_contracts(client, overrides):
    # Missing columns
    missing_col_csv = b"Date,Description,Amount\n2026-01-05,Salary,5000\n"
    res_col = client.post(
        "/api/v1/imports/validate",
        files={"file": ("bad_col.csv", missing_col_csv, "text/csv")},
    )
    assert res_col.status_code == 422
    body_col = res_col.json()
    assert body_col["status"] == "rejected"
    assert body_col["code"] == "MISSING_COLUMNS"
    assert "Type" in body_col["message"]

    # Unsupported format
    res_ext = client.post(
        "/api/v1/imports/validate",
        files={"file": ("script.py", b"print('hello')", "text/x-python")},
    )
    assert res_ext.status_code == 415
    assert res_ext.json()["code"] == "UNSUPPORTED_FORMAT"

    # Empty file
    res_empty = client.post(
        "/api/v1/imports/validate",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert res_empty.status_code == 422
    assert res_empty.json()["code"] == "EMPTY_FILE"


def test_import_job_lifecycle_states(client, overrides):
    sample_csv = (
        b"Date,Description,Amount,Type,Category\n"
        b"2026-01-05,Monthly salary,52000,income,salary\n"
    )
    # 1. Validate: should be status 'validated'
    res = client.post(
        "/api/v1/imports/validate",
        files={"file": ("salary.csv", sample_csv, "text/csv")},
    )
    assert res.status_code == 200
    token = res.json()["import_token"]

    db = overrides["database"]
    import_job = db["imports"].docs.get(token)
    assert import_job is not None
    assert import_job["status"] == "validated"

    # 2. Commit: should transition to 'completed'
    commit_res = client.post(
        "/api/v1/imports/commit",
        json={"import_token": token, "duplicate_strategy": "import_new_only"},
    )
    assert commit_res.status_code == 200
    import_job_after = db["imports"].docs.get(token)
    assert import_job_after["status"] == "completed"
    assert import_job_after["counts"]["imported_count"] == 1


def test_skipped_duplicates_generate_zero_vector_calls(client, overrides):
    from app.api.deps import get_transaction_service
    from app.main import app
    from app.services.transactions import TransactionService

    # Pre-insert 1 transaction into repo
    repo = overrides["transactions"]
    import asyncio
    asyncio.run(repo.create({
        "date": "2026-01-05",
        "description": "Monthly salary",
        "amount": 52000.0,
        "transaction_type": "income",
        "category": "salary",
    }))

    # CSV with 1 duplicate and 1 new row
    csv_data = (
        b"Date,Description,Amount,Type,Category\n"
        b"2026-01-05,Monthly salary,52000,income,salary\n"
        b"2026-01-06,Bonus pay,10000,income,salary\n"
    )

    vector_synced_txs = []
    async def mock_sync(txs, *, user_id, repository):
        vector_synced_txs.extend(txs)
        return True

    orig_override = app.dependency_overrides.get(get_transaction_service)
    app.dependency_overrides[get_transaction_service] = lambda: TransactionService(
        overrides["transactions"],
        overrides["budgets"],
        vector_sync=mock_sync,
    )

    try:
        # Direct import with duplicate_action=import_new_only
        res = client.post(
            "/api/v1/imports",
            data={"duplicate_action": "import_new_only"},
            files={"file": ("salary.csv", csv_data, "text/csv")},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["summary"]["new"] == 1
        assert data["summary"]["duplicates"] == 1
        # Verify ONLY 1 transaction was passed to vector sync
        assert len(vector_synced_txs) == 1
        assert vector_synced_txs[0]["description"] == "Bonus pay"
    finally:
        if orig_override:
            app.dependency_overrides[get_transaction_service] = orig_override


def test_failed_embedding_records_embedding_failed(client, overrides):
    from app.api.deps import get_transaction_service
    from app.main import app
    from app.services.transactions import TransactionService

    async def fail_sync(txs, *, user_id, repository):
        raise RuntimeError("simulated vector embedding timeout")

    orig_override = app.dependency_overrides.get(get_transaction_service)
    app.dependency_overrides[get_transaction_service] = lambda: TransactionService(
        overrides["transactions"],
        overrides["budgets"],
        vector_sync=fail_sync,
    )

    try:
        sample_csv = (
            b"Date,Description,Amount,Type,Category\n"
            b"2026-01-07,Freelance work,15000,income,freelance\n"
        )
        res = client.post(
            "/api/v1/imports/validate",
            files={"file": ("freelance.csv", sample_csv, "text/csv")},
        )
        assert res.status_code == 200
        token = res.json()["import_token"]

        commit_res = client.post(
            "/api/v1/imports/commit",
            json={"import_token": token, "duplicate_strategy": "import_new_only"},
        )
        assert commit_res.status_code == 200

        db = overrides["database"]
        import_job = db["imports"].docs.get(token)
        assert import_job is not None
        assert import_job["status"] == "embedding_failed"
        assert "simulated vector embedding timeout" in import_job.get("embedding_error", "")
    finally:
        if orig_override:
            app.dependency_overrides[get_transaction_service] = orig_override


