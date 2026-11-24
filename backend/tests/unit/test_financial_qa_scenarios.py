import asyncio
from datetime import date
import pytest

from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.domain.dates import today_ist
from app.schemas.insights import SpendingInsightRequest
from app.services.analytics import AnalyticsService
from app.services.financial_qa import FinancialQAEngine, classify_question_intent
from app.services.insights import InsightService
from app.services.transactions import TransactionService
from tests.fakes import FakeAnalyticsRepository, FakeTransactionRepository


def make_transaction(tx_id, tx_date, amount, category, tx_type, desc="", user_id=DEFAULT_CURRENT_USER_ID):
    return {
        "id": tx_id,
        "date": str(tx_date),
        "amount": float(amount),
        "category": category,
        "transaction_type": tx_type,
        "description": desc or f"{category} transaction",
        "user_id": user_id,
    }


class InMemoryAnalyticsRepository:
    """Mock repository that faithfully executes aggregations across in-memory transactions."""
    def __init__(self, transactions):
        self.transactions = transactions

    async def grouped_rows(self, *, start_date, end_date, user_id=DEFAULT_CURRENT_USER_ID):
        s_str = start_date.isoformat()
        e_str = end_date.isoformat()
        buckets = {}
        for tx in self.transactions:
            if tx.get("user_id") != user_id:
                continue
            d = str(tx["date"])
            if s_str <= d <= e_str:
                key = (tx["transaction_type"], tx["category"])
                if key not in buckets:
                    buckets[key] = {"total": 0.0, "count": 0}
                buckets[key]["total"] += float(tx["amount"])
                buckets[key]["count"] += 1
        return [
            {"_id": {"type": k[0], "category": k[1]}, "total": v["total"], "count": v["count"]}
            for k, v in buckets.items()
        ]

    async def get_date_coverage(self, *, user_id=DEFAULT_CURRENT_USER_ID):
        user_txs = [tx for tx in self.transactions if tx.get("user_id") == user_id]
        if not user_txs:
            return {"min_date": None, "max_date": None, "count": 0}
        dates = [str(tx["date"]) for tx in user_txs]
        return {"min_date": min(dates), "max_date": max(dates), "count": len(user_txs)}

    async def monthly_grouped_rows(self, *, start_date=None, end_date=None, user_id=DEFAULT_CURRENT_USER_ID):
        s_str = start_date.isoformat() if start_date else "0000-00-00"
        e_str = end_date.isoformat() if end_date else "9999-99-99"
        buckets = {}
        for tx in self.transactions:
            if tx.get("user_id") != user_id:
                continue
            d = str(tx["date"])
            if s_str <= d <= e_str:
                month_str = d[:7]
                key = (month_str, tx["transaction_type"], tx["category"])
                if key not in buckets:
                    buckets[key] = {"total": 0.0, "count": 0}
                buckets[key]["total"] += float(tx["amount"])
                buckets[key]["count"] += 1
        return [
            {
                "_id": {"month": k[0], "type": k[1], "category": k[2]},
                "total": v["total"],
                "count": v["count"],
            }
            for k, v in sorted(buckets.items())
        ]


def create_test_engine(transactions, user_id=DEFAULT_CURRENT_USER_ID):
    repo = FakeTransactionRepository(transactions)
    tx_service = TransactionService(repo)
    analytics_repo = InMemoryAnalyticsRepository(transactions)
    analytics_service = AnalyticsService(analytics_repo)
    engine = FinancialQAEngine(analytics_service, tx_service)
    return engine, tx_service, analytics_service


# ==============================================================================
# SECTION 8: VERIFY ALL 40 FINANCIAL QUESTIONS
# ==============================================================================

@pytest.fixture
def comprehensive_2026_dataset():
    """Rich dataset for 2026 covering multiple months and transaction types."""
    user = DEFAULT_CURRENT_USER_ID
    txs = [
        # January - October 2026
        make_transaction(1, "2026-01-15", 50000.0, "salary", "income", "January Salary", user),
        make_transaction(2, "2026-01-20", 12000.0, "housing", "expense", "January Rent", user),
        make_transaction(3, "2026-02-15", 50000.0, "salary", "income", "February Salary", user),
        make_transaction(4, "2026-02-18", 12000.0, "housing", "expense", "February Rent", user),
        make_transaction(5, "2026-05-10", 15000.0, "freelance", "income", "Freelance Web Project", user),
        make_transaction(6, "2026-06-15", 25000.0, "freelance", "income", "Freelance Mobile App", user),

        # October 2026
        make_transaction(7, "2026-10-01", 50000.0, "salary", "income", "October Salary", user),
        make_transaction(8, "2026-10-05", 12000.0, "housing", "expense", "October Rent", user),
        make_transaction(9, "2026-10-10", 6000.0, "food", "expense", "October Restaurants", user),
        make_transaction(10, "2026-10-15", 4000.0, "shopping", "expense", "October Shopping", user),
        make_transaction(11, "2026-10-20", 3000.0, "transport", "expense", "October Fuel", user),

        # November 2026 (current month)
        make_transaction(12, "2026-11-01", 60000.0, "salary", "income", "November Salary", user),
        make_transaction(13, "2026-11-02", 10000.0, "freelance", "income", "November Consulting", user),
        make_transaction(14, "2026-11-03", 12000.0, "housing", "expense", "November Rent", user),
        make_transaction(15, "2026-11-05", 8000.0, "food", "expense", "Groceries and Dining", user),
        make_transaction(16, "2026-11-08", 5000.0, "transport", "expense", "Flight ticket", user),
        make_transaction(17, "2026-11-10", 2500.0, "groceries", "expense", "Weekly Supermarket", user),
        make_transaction(18, "2026-11-12", 4500.0, "education", "expense", "AI Course", user),
        make_transaction(19, "2026-11-14", 1500.0, "health", "expense", "Pharmacy Doctor", user),
        make_transaction(20, "2026-11-15", 500.0, "subscriptions", "expense", "Cloud Storage", user),
        make_transaction(21, "2026-11-18", 16000.0, "investment", "investment", "Mutual Fund SIP", user),
        make_transaction(22, "2026-11-20", 5000.0, "loan", "loan_repaid", "Car Loan EMI", user),

        # Highest expense ever
        make_transaction(23, "2026-03-15", 45000.0, "education", "expense", "Annual University Tuition", user),
    ]
    return txs


@pytest.mark.asyncio
async def test_q01_where_did_i_spend_least_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Where did I spend the least this year?", reference_date=ref)
    assert "least" in res.summary.lower()
    # Subscriptions is ₹500 (lowest non-zero operating expense)
    assert "subscriptions" in res.summary.lower() or "Subscriptions" in str(res.key_findings)
    assert "500" in res.summary or "500" in str(res.key_findings)


@pytest.mark.asyncio
async def test_q02_where_did_i_spend_most_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Where did I spend the most this year?", reference_date=ref)
    assert "most" in res.summary.lower()
    # Education is 45,000 + 4,500 = 49,500 (operating expense), higher than housing 48,000
    assert "education" in res.summary.lower()
    assert "investment" not in res.summary.lower()  # Must not confuse investments with operating expenses!


@pytest.mark.asyncio
async def test_q03_how_much_money_did_i_spend_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much money did I spend this year?", reference_date=ref)
    assert "total operating expenses" in res.summary.lower()
    assert "₹" in res.summary


@pytest.mark.asyncio
async def test_q04_what_was_my_total_income_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What was my total income this year?", reference_date=ref)
    assert "total earned income" in res.summary.lower() or "income was" in res.summary.lower()


@pytest.mark.asyncio
async def test_q05_how_much_money_did_i_save_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much money did I save this year?", reference_date=ref)
    assert "saved" in res.summary.lower()
    assert "operating savings" in str(res.limitations).lower() or "operating savings" in str(res.key_findings).lower()


@pytest.mark.asyncio
async def test_q06_which_category_consumed_largest_portion_of_income(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Which category consumed the largest portion of my income?", reference_date=ref)
    assert "consumed the largest portion" in res.summary.lower()


@pytest.mark.asyncio
async def test_q07_top_five_spending_categories_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What are my top five spending categories this year?", reference_date=ref)
    assert "top" in res.summary.lower()
    assert len(res.key_findings) >= 5


@pytest.mark.asyncio
async def test_q08_how_much_did_i_spend_on_food_throughout_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much did I spend on food throughout this year?", reference_date=ref)
    assert "food" in res.summary.lower()
    # Food is 6,000 (Oct) + 8,000 (Nov) = 14,000
    assert "14,000" in res.summary


@pytest.mark.asyncio
async def test_q09_how_much_did_i_spend_on_transportation_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much did I spend on transportation this year?", reference_date=ref)
    assert "transport" in res.summary.lower()


@pytest.mark.asyncio
async def test_q10_compare_income_and_expenses_this_year(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Compare my income and expenses for this year.", reference_date=ref)
    assert "income was" in res.summary.lower()
    assert "operating expenses" in res.summary.lower()


@pytest.mark.asyncio
async def test_q11_how_much_did_i_spend_this_month(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much did I spend this month?", reference_date=ref)
    assert "operating expenses were" in res.summary.lower()
    # Nov expenses: housing 12,000 + food 8,000 + transport 5,000 + groceries 2,500 + edu 4,500 + health 1,500 + sub 500 = 34,000
    assert "34,000" in res.summary


@pytest.mark.asyncio
async def test_q12_which_category_spend_most_this_month(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Which category did I spend the most on this month?", reference_date=ref)
    # Housing is ₹12,000
    assert "housing" in res.summary.lower()


@pytest.mark.asyncio
async def test_q13_which_category_had_lowest_spending_this_month(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Which category had the lowest spending this month?", reference_date=ref)
    # Subscriptions is ₹500
    assert "subscriptions" in res.summary.lower()
    assert "500" in res.summary


@pytest.mark.asyncio
async def test_q14_what_was_my_highest_spending_month(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What was my highest spending month?", reference_date=ref)
    assert "highest spending month" in res.summary.lower()
    # March had the 45,000 tuition
    assert "2026-03" in res.summary


@pytest.mark.asyncio
async def test_q15_which_month_had_highest_income(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Which month had the highest income?", reference_date=ref)
    assert "highest income" in res.summary.lower()
    # November had 60,000 salary + 10,000 freelance = 70,000
    assert "2026-11" in res.summary


@pytest.mark.asyncio
async def test_q16_compare_expenses_between_october_and_november(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Compare my expenses between October and November.", reference_date=ref)
    assert "comparing october vs november" in res.summary.lower()
    assert "operating expenses" in res.summary.lower()


@pytest.mark.asyncio
async def test_q17_top_three_expenses_this_month(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What are my top three expenses this month?", reference_date=ref)
    assert "top 3" in res.summary.lower() or "top" in res.summary.lower()
    assert len(res.key_findings) == 3


@pytest.mark.asyncio
async def test_q18_how_much_did_i_spend_on_shopping_last_month(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much did I spend on shopping last month?", reference_date=ref)
    assert "shopping" in res.summary.lower()
    # October shopping was 4,000
    assert "4,000" in res.summary


@pytest.mark.asyncio
async def test_q19_how_much_have_i_spent_on_groceries(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much have I spent on groceries?", reference_date=ref)
    assert "groceries" in res.summary.lower()
    assert "2,500" in res.summary


@pytest.mark.asyncio
async def test_q20_show_all_my_healthcare_expenses(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Show all my healthcare expenses.", reference_date=ref)
    assert "health" in res.summary.lower()
    assert len(res.key_findings) >= 1


@pytest.mark.asyncio
async def test_q21_how_much_did_i_spend_on_education(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much did I spend on education?", reference_date=ref)
    assert "education" in res.summary.lower()


@pytest.mark.asyncio
async def test_q22_what_are_my_biggest_transportation_expenses(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What are my biggest transportation expenses?", reference_date=ref)
    assert "transport" in res.summary.lower()
    assert len(res.key_findings) >= 1


@pytest.mark.asyncio
async def test_q23_how_much_did_i_spend_on_subscriptions(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much did I spend on subscriptions?", reference_date=ref)
    assert "subscriptions" in res.summary.lower()
    assert "500" in res.summary


@pytest.mark.asyncio
async def test_q24_which_category_has_most_transactions(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Which category has the most transactions?", reference_date=ref)
    assert "most transactions" in res.summary.lower()


@pytest.mark.asyncio
async def test_q25_percentage_of_expenses_went_towards_housing(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What percentage of my total expenses went towards housing?", reference_date=ref)
    assert "housing" in res.summary.lower()
    assert "%" in res.summary


@pytest.mark.asyncio
async def test_q26_what_is_my_primary_source_of_income(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What is my primary source of income?", reference_date=ref)
    assert "salary" in res.summary.lower()


@pytest.mark.asyncio
async def test_q27_how_much_income_did_i_earn_from_freelancing(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much income did I earn from freelancing?", reference_date=ref)
    assert "freelance" in res.summary.lower()
    # 15,000 (May) + 25,000 (June) + 10,000 (Nov) = 50,000
    assert "50,000" in res.summary


@pytest.mark.asyncio
async def test_q28_which_month_generated_highest_freelance_income(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Which month generated the highest freelance income?", reference_date=ref)
    assert "highest freelance income" in res.summary.lower()
    # June had 25,000
    assert "2026-06" in res.summary


@pytest.mark.asyncio
async def test_q29_what_is_my_total_cash_inflow(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What is my total cash inflow?", reference_date=ref)
    assert "total cash inflow" in res.summary.lower()


@pytest.mark.asyncio
async def test_q30_money_left_after_deducting_expenses_from_income(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much money is left after deducting my expenses from my income?", reference_date=ref)
    assert "saved" in res.summary.lower() or "income minus" in res.summary.lower()


@pytest.mark.asyncio
async def test_q31_where_did_i_spend_most_in_previous_year_no_data(comprehensive_2026_dataset):
    """PROBLEM B TEST: If no 2025 records exist, MUST state no records for 2025 and NEVER reuse 2026!"""
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Where did I spend the most in the previous year?", reference_date=ref)
    # Must NOT hallucinate or reuse 2026!
    assert "2025" in res.summary
    assert "couldn't find any transaction records" in res.summary.lower() or "do not contain" in res.summary.lower()
    assert "education" not in res.summary.lower()
    assert "housing" not in res.summary.lower()


@pytest.mark.asyncio
async def test_q32_compare_spending_between_2025_and_2026(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Compare my spending between 2025 and 2026.", reference_date=ref)
    # 2025 is missing
    assert "2025" in res.summary
    assert "do not contain transactions for 2025" in res.summary.lower()


@pytest.mark.asyncio
async def test_q33_show_my_expenses_for_december_2025(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Show my expenses for December 2025.", reference_date=ref)
    assert "no transaction data found" in res.summary.lower() or "december 2025" in res.summary.lower()


@pytest.mark.asyncio
async def test_q34_what_was_my_highest_expense_transaction_ever(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What was my highest expense transaction ever?", reference_date=ref)
    # Highest is ₹45,000 for tuition on 2026-03-15
    assert "45,000" in res.summary
    assert "2026-03-15" in res.summary


@pytest.mark.asyncio
async def test_q35_complete_financial_summary_from_january_to_november_2026(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Give me a complete financial summary from January to November 2026.", reference_date=ref)
    assert "earned income was" in res.summary.lower()
    assert "operating expenses were" in res.summary.lower()


@pytest.mark.asyncio
async def test_q36_how_much_did_i_spend_yesterday(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("How much did I spend yesterday?", reference_date=ref)
    # Yesterday is 2026-11-22 (no transactions)
    assert "no transaction data found" in res.summary.lower() or "2026-11-22" in res.summary.lower()


@pytest.mark.asyncio
async def test_q37_show_transactions_for_a_date_when_no_records(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Show transactions for 2026-04-01.", reference_date=ref)
    assert "no transaction data found" in res.summary.lower() or "2026-04-01" in res.summary.lower()


@pytest.mark.asyncio
async def test_q38_did_i_spend_anything_on_medical_expenses_in_2025(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Did I spend anything on medical expenses in 2025?", reference_date=ref)
    assert "2025" in res.summary
    assert "couldn't find any transaction records" in res.summary.lower() or "no transactions" in res.summary.lower()


@pytest.mark.asyncio
async def test_q39_what_is_my_average_monthly_spending(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("What is my average monthly spending?", reference_date=ref)
    assert "average monthly spending was" in res.summary.lower()
    assert "active month" in res.summary.lower() or "active month" in str(res.key_findings).lower()


@pytest.mark.asyncio
async def test_q40_am_i_spending_more_than_earning(comprehensive_2026_dataset):
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine(comprehensive_2026_dataset)
    res = await engine.execute_qa("Am I spending more than I am earning?", reference_date=ref)
    assert "living within your means" in res.summary.lower() or "income and expenses" in res.summary.lower()


# ==============================================================================
# SECTION 9: VERIFY ALL 10 DATABASE CONDITIONS
# ==============================================================================

@pytest.mark.asyncio
async def test_scenario_a_only_november_2026_records():
    """Scenario A: Only November 2026 records exist. Asking for 'this year' must disclose partial coverage."""
    ref = date(2026, 11, 23)
    txs = [
        make_transaction(1, "2026-11-05", 10000.0, "housing", "expense"),
        make_transaction(2, "2026-11-15", 3000.0, "food", "expense"),
    ]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("Where did I spend the most this year?", reference_date=ref)
    assert "housing" in res.summary.lower()
    # Discloses partial coverage
    assert any("available records from 2026-11-05 to 2026-11-15" in note for note in res.limitations)


@pytest.mark.asyncio
async def test_scenario_b_jan_to_nov_2026_records():
    """Scenario B: Full Jan-Nov 2026 records exist."""
    ref = date(2026, 11, 23)
    txs = [
        make_transaction(1, "2026-01-10", 5000.0, "food", "expense"),
        make_transaction(2, "2026-06-10", 8000.0, "food", "expense"),
        make_transaction(3, "2026-11-10", 9000.0, "housing", "expense"),
    ]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("Where did I spend the most this year?", reference_date=ref)
    # Food is 5,000 + 8,000 = 13,000 > Housing 9,000
    assert "food" in res.summary.lower()


@pytest.mark.asyncio
async def test_scenario_c_no_2025_records():
    """Scenario C: No 2025 records exist. Must return clear missing message."""
    ref = date(2026, 11, 23)
    txs = [make_transaction(1, "2026-11-10", 9000.0, "housing", "expense")]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("Where did I spend the most in 2025?", reference_date=ref)
    assert "2025" in res.summary
    assert "couldn't find any transaction records for 2025" in res.summary.lower()


@pytest.mark.asyncio
async def test_scenario_d_partial_2025_records():
    """Scenario D: Partial 2025 records exist (e.g. only Dec 2025). Must disclose coverage."""
    ref = date(2026, 11, 23)
    txs = [
        make_transaction(1, "2025-12-05", 4000.0, "shopping", "expense"),
        make_transaction(2, "2026-11-10", 9000.0, "housing", "expense"),
    ]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("Where did I spend the most in 2025?", reference_date=ref)
    assert "shopping" in res.summary.lower()
    # Mentions available range
    assert any("2025-12-05" in note for note in res.limitations)


@pytest.mark.asyncio
async def test_scenario_e_no_records_exist():
    """Scenario E: Empty database."""
    ref = date(2026, 11, 23)
    engine, _, _ = create_test_engine([])
    res = await engine.execute_qa("Where did I spend the most this year?", reference_date=ref)
    assert "no transaction data found in your account" in res.summary.lower()


@pytest.mark.asyncio
async def test_scenario_f_multiple_transaction_types():
    """Scenario F: Multiple transaction types exist (all 8 types). Must not mix investments/loans with expenses."""
    ref = date(2026, 11, 23)
    txs = [
        make_transaction(1, "2026-11-01", 50000.0, "salary", "income"),
        make_transaction(2, "2026-11-02", 5000.0, "food", "expense"),
        make_transaction(3, "2026-11-03", 25000.0, "equity", "investment"),
        make_transaction(4, "2026-11-04", 1000.0, "dividend", "investment_return"),
        make_transaction(5, "2026-11-05", 20000.0, "bank", "loan_taken"),
        make_transaction(6, "2026-11-06", 4000.0, "personal", "loan_repaid"),
        make_transaction(7, "2026-11-07", 3000.0, "friend", "loan_given"),
        make_transaction(8, "2026-11-08", 2000.0, "friend", "loan_collected"),
    ]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("Where did I spend the most this month?", reference_date=ref)
    # Highest operating expense category is Food (₹5,000), NOT Equity (₹25,000 investment)
    assert "food" in res.summary.lower()
    assert "equity" not in res.summary.lower()


@pytest.mark.asyncio
async def test_scenario_g_tied_categories():
    """Scenario G: Multiple categories have equal spending (ties). Must report all ties."""
    ref = date(2026, 11, 23)
    txs = [
        make_transaction(1, "2026-11-01", 5000.0, "food", "expense"),
        make_transaction(2, "2026-11-02", 5000.0, "shopping", "expense"),
        make_transaction(3, "2026-11-03", 2000.0, "utilities", "expense"),
    ]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("Where did I spend the most this month?", reference_date=ref)
    assert "tie" in res.summary.lower()
    assert "food" in res.summary.lower()
    assert "shopping" in res.summary.lower()


@pytest.mark.asyncio
async def test_scenario_h_boundary_dates():
    """Scenario H: Transactions exist on date-range boundaries (Jan 1 and Dec 31)."""
    ref = date(2026, 11, 23)
    txs = [
        make_transaction(1, "2026-01-01", 3000.0, "books", "expense"),
        make_transaction(2, "2026-11-23", 4000.0, "books", "expense"),
    ]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("How much did I spend this year?", reference_date=ref)
    # Both boundaries included: 3,000 + 4,000 = 7,000
    assert "7,000" in res.summary


@pytest.mark.asyncio
async def test_scenario_i_income_exists_expenses_do_not():
    """Scenario I: Only income exists, no expenses."""
    ref = date(2026, 11, 23)
    txs = [make_transaction(1, "2026-11-01", 50000.0, "salary", "income")]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("Where did I spend the most this month?", reference_date=ref)
    assert "no recorded operating expenses" in res.summary.lower()


@pytest.mark.asyncio
async def test_scenario_j_expenses_exist_income_does_not():
    """Scenario J: Only expenses exist, no income."""
    ref = date(2026, 11, 23)
    txs = [make_transaction(1, "2026-11-01", 8000.0, "food", "expense")]
    engine, _, _ = create_test_engine(txs)
    res = await engine.execute_qa("What was my total income this month?", reference_date=ref)
    assert "0.00" in res.summary
