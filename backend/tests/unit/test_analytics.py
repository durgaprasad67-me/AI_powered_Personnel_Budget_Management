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
            row("loan_collected", "loan return", 200.0),
            row("loan_given", "loan", 500.0),
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
    assert summary["loans"]["collected"] == 200.0
    assert summary["loans"]["lent"] == 500.0
    assert summary["net_cash_flow"] == 126199.5
    assert summary["total_cash_inflow"] == 152700.0
    assert summary["total_cash_outflow"] == 26500.5
    assert summary["outflow_categories"] == {
        "loan": 12500.0,
        "investment": 10000.0,
        "food": 4000.5,
    }
    assert summary["inflow_categories"] == {
        "loan": 100000.0,
        "salary": 50000.0,
        "investment": 2500.0,
        "loan return": 200.0,
    }
    assert summary["type_breakdown"]["income"] == 50000.0
    assert summary["type_breakdown"]["expense"] == 4000.5
    assert summary["type_breakdown"]["investment"] == 10000.0
    assert summary["type_breakdown"]["loan_repaid"] == 12000.0
    assert len(summary["type_details"]) == 8
    food_expense = next(item for item in summary["type_details"] if item["type"] == "expense")
    assert food_expense["stream"] == "outflow"
    assert food_expense["total"] == 4000.5
    assert food_expense["categories"] == {"food": 4000.5}


def test_monthly_analytics_summary_schema_validation():
    from app.schemas.analytics import MonthlyAnalyticsSummary

    def row(kind, category, total):
        return {"_id": {"type": kind, "category": category}, "total": total}

    summary_dict = build_monthly_summary(
        "2026-11",
        [
            row("income", "salary", 80000.0),
            row("income", "consulting", 20000.0),
            row("investment_return", "dividends", 5000.0),
            row("loan_taken", "personal loan", 50000.0),
            row("loan_collected", "debt collection", 1500.0),
            row("expense", "groceries", 12000.0),
            row("expense", "utilities", 4000.0),
            row("investment", "mutual funds", 25000.0),
            row("loan_repaid", "car emi", 15000.0),
            row("loan_given", "emergency help", 5000.0),
        ],
    )

    validated = MonthlyAnalyticsSummary.model_validate(summary_dict)
    assert validated.month == "2026-11"
    assert validated.total_income == 100000.0
    assert validated.total_expenses == 16000.0
    assert validated.balance == 84000.0
    assert validated.total_cash_inflow == 156500.0
    assert validated.total_cash_outflow == 61000.0
    assert validated.net_cash_flow == 95500.0
    assert validated.inflow_categories["salary"] == 80000.0
    assert validated.inflow_categories["consulting"] == 20000.0
    assert validated.inflow_categories["dividends"] == 5000.0
    assert validated.outflow_categories["mutual funds"] == 25000.0
    assert validated.outflow_categories["car emi"] == 15000.0
    assert validated.outflow_categories["groceries"] == 12000.0
    assert validated.type_breakdown["loan_given"] == 5000.0
    assert len(validated.type_details) == 8
