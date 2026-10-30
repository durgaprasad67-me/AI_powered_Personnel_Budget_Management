from app.services.analytics import build_monthly_summary


def test_monthly_summary_keeps_loans_and_investments_out_of_spending():
    def row(kind, category, total):
        return {"_id": {"type": kind, "category": category}, "total": total}

    summary = build_monthly_summary(
        "2026-10",
        [
            row("income", "salary", 50000.0),
            row("expense", "food", 3000.5),
            row("expense", "food", 1000.0),
            row("investment", "investment", 10000.0),
            row("investment_return", "investment", 2500.0),
            row("loan_taken", "loan", 100000.0),
            row("loan_repaid", "loan", 12000.0),
        ],
    )

    assert summary["total_income"] == 50000.0
    assert summary["total_expenses"] == 4000.5
    assert summary["balance"] == 45999.5
    assert summary["category_breakdown"] == {"food": 4000.5}
    assert summary["investments"] == {
        "invested": 10000.0,
        "returned": 2500.0,
        "net_invested": 7500.0,
    }
    assert summary["loans"]["borrowed"] == 100000.0
    assert summary["loans"]["repaid"] == 12000.0
    assert summary["net_cash_flow"] == 126499.5
