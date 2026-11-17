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
