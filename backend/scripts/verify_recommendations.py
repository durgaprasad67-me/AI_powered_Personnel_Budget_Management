import asyncio
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.client import get_database, close_database
from app.repositories.analytics import AnalyticsRepository
from app.repositories.transactions import TransactionRepository
from app.services.analytics import AnalyticsService
from app.services.transactions import TransactionService
from app.services.insights import InsightService
from app.schemas.insights import SpendingInsightRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rec_verifier")

PASS = "[PASS]"
FAIL = "[FAIL]"

async def run_recommendation_tests():
    db = get_database()
    tx_repo = TransactionRepository(db['transactions'])
    tx_svc = TransactionService(tx_repo)
    analytics_repo = AnalyticsRepository(db['transactions'])
    analytics_svc = AnalyticsService(analytics_repo)
    insight_svc = InsightService(analytics_svc, transaction_service=tx_svc)
    user_id = "default_dashboard_user"

    print("================================================================================")
    print("STARTING DATA-DRIVEN RECOMMENDATION VERIFICATION")
    print("================================================================================\n")

    results = []

    # -------------------------------------------------------------------------
    # TEST 1 — Spending Reduction: "Where can I reduce my spending?"
    # -------------------------------------------------------------------------
    print("--- TEST 1: Where can I reduce my spending? ---")
    q1 = "Where can I reduce my spending?"
    res1 = await insight_svc.spending_insights(
        SpendingInsightRequest(question=q1, include_recommendations=True),
        user_id=user_id,
    )
    print(f"Summary: {res1.summary}")
    print(f"Key findings: {res1.key_findings}")
    print(f"Recommendations count: {len(res1.recommendations)}")
    for r in res1.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")
        print(f"    Savings: {r.estimated_monthly_savings}")

    t1_pass = (
        len(res1.recommendations) > 0
        and all("Observation:" in r.explanation and "Why it matters:" in r.explanation and "Action:" in r.explanation for r in res1.recommendations)
        and any(r.estimated_monthly_savings is not None and r.estimated_monthly_savings > 0 for r in res1.recommendations)
        and "Education" in res1.summary
        and "9,600" in res1.summary
    )
    st1 = PASS if t1_pass else FAIL
    results.append(("TEST 1 — Where can I reduce my spending?", st1, res1.summary, len(res1.recommendations)))
    print(f"Result: {st1}\n")

    # -------------------------------------------------------------------------
    # TEST 2 — Biggest Spending Category: "What is my biggest spending category?"
    # -------------------------------------------------------------------------
    print("--- TEST 2: What is my biggest spending category? ---")
    q2 = "What is my biggest spending category?"
    res2 = await insight_svc.spending_insights(
        SpendingInsightRequest(question=q2, include_recommendations=True),
        user_id=user_id,
    )
    print(f"Summary: {res2.summary}")
    print(f"Key findings: {res2.key_findings}")
    print(f"Recommendations count: {len(res2.recommendations)}")
    for r in res2.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")

    t2_pass = (
        "Education" in res2.summary
        and "9,600" in res2.summary
        and len(res2.recommendations) > 0
        and "Education" in res2.recommendations[0].title
        and "Observation:" in res2.recommendations[0].explanation
    )
    st2 = PASS if t2_pass else FAIL
    results.append(("TEST 2 — What is my biggest spending category?", st2, res2.summary, len(res2.recommendations)))
    print(f"Result: {st2}\n")

    # -------------------------------------------------------------------------
    # TEST 3 — Spending Pattern: "What spending pattern should I watch?"
    # -------------------------------------------------------------------------
    print("--- TEST 3: What spending pattern should I watch? ---")
    q3 = "What spending pattern should I watch?"
    res3 = await insight_svc.spending_insights(
        SpendingInsightRequest(question=q3, include_recommendations=True),
        user_id=user_id,
    )
    print(f"Summary: {res3.summary}")
    print(f"Key findings: {res3.key_findings}")
    print(f"Recommendations count: {len(res3.recommendations)}")
    for r in res3.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")

    t3_pass = (
        len(res3.recommendations) > 0
        and all("Observation:" in r.explanation and "Action:" in r.explanation for r in res3.recommendations)
    )
    st3 = PASS if t3_pass else FAIL
    results.append(("TEST 3 — What spending pattern should I watch?", st3, res3.summary, len(res3.recommendations)))
    print(f"Result: {st3}\n")

    # -------------------------------------------------------------------------
    # TEST 4 — Savings Assessment: "Am I saving enough based on my income and expenses?"
    # -------------------------------------------------------------------------
    print("--- TEST 4: Am I saving enough based on my income and expenses? ---")
    q4 = "Am I saving enough based on my income and expenses?"
    res4 = await insight_svc.spending_insights(
        SpendingInsightRequest(question=q4, include_recommendations=True),
        user_id=user_id,
    )
    print(f"Summary: {res4.summary}")
    print(f"Key findings: {res4.key_findings}")
    print(f"Recommendations count: {len(res4.recommendations)}")
    for r in res4.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")

    t4_pass = (
        "55,800" in res4.summary
        and "86,000" in res4.summary
        and "30,200" in res4.summary
        and len(res4.recommendations) > 0
        and any("Savings" in r.title or "Goal" in r.title for r in res4.recommendations)
        and all("Observation:" in r.explanation for r in res4.recommendations)
    )
    st4 = PASS if t4_pass else FAIL
    results.append(("TEST 4 — Am I saving enough based on my income and expenses?", st4, res4.summary, len(res4.recommendations)))
    print(f"Result: {st4}\n")

    # -------------------------------------------------------------------------
    # TEST 5 — Budget Exceedance: "Which categories are exceeding their budgets?"
    # -------------------------------------------------------------------------
    print("--- TEST 5: Which categories are exceeding their budgets? ---")
    q5 = "Which categories are exceeding their budgets?"
    res5 = await insight_svc.spending_insights(
        SpendingInsightRequest(question=q5, include_recommendations=True),
        user_id=user_id,
    )
    print(f"Summary: {res5.summary}")
    print(f"Key findings: {res5.key_findings}")
    print(f"Recommendations count: {len(res5.recommendations)}")
    for r in res5.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")

    t5_pass = (
        ("None of your configured budgets" in res5.summary or "exceeding" in res5.summary)
        and len(res5.recommendations) > 0
        and any("Budget" in r.title for r in res5.recommendations)
        and all("Observation:" in r.explanation for r in res5.recommendations)
    )
    st5 = PASS if t5_pass else FAIL
    results.append(("TEST 5 — Which categories are exceeding their budgets?", st5, res5.summary, len(res5.recommendations)))
    print(f"Result: {st5}\n")

    # -------------------------------------------------------------------------
    # TEST 6 — Unusual Expenses: "Do I have any unusually high expenses?"
    # -------------------------------------------------------------------------
    print("--- TEST 6: Do I have any unusually high expenses? ---")
    q6 = "Do I have any unusually high expenses?"
    res6 = await insight_svc.spending_insights(
        SpendingInsightRequest(question=q6, include_recommendations=True),
        user_id=user_id,
    )
    print(f"Summary: {res6.summary}")
    print(f"Key findings: {res6.key_findings}")
    print(f"Recommendations count: {len(res6.recommendations)}")
    for r in res6.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")

    t6_pass = (
        ("No statistical outliers" in res6.summary or "outlier" in res6.summary or "unusually high" in res6.summary)
        and "30,200" in str(res6.key_findings)
    )
    st6 = PASS if t6_pass else FAIL
    results.append(("TEST 6 — Do I have any unusually high expenses?", st6, res6.summary, len(res6.recommendations)))
    print(f"Result: {st6}\n")

    # -------------------------------------------------------------------------
    # TEST 7 — Budget Improvement: "How can I improve my monthly budget?"
    # -------------------------------------------------------------------------
    print("--- TEST 7: How can I improve my monthly budget? ---")
    q7 = "How can I improve my monthly budget?"
    res7 = await insight_svc.spending_insights(
        SpendingInsightRequest(question=q7, include_recommendations=True),
        user_id=user_id,
    )
    print(f"Summary: {res7.summary}")
    print(f"Key findings: {res7.key_findings}")
    print(f"Recommendations count: {len(res7.recommendations)}")
    for r in res7.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")

    t7_pass = (
        len(res7.recommendations) > 0
        and all("Observation:" in r.explanation and "Action:" in r.explanation for r in res7.recommendations)
    )
    st7 = PASS if t7_pass else FAIL
    results.append(("TEST 7 — How can I improve my monthly budget?", st7, res7.summary, len(res7.recommendations)))
    print(f"Result: {st7}\n")

    # -------------------------------------------------------------------------
    # TEST 8 — Practical Savings: "Suggest one practical way to save money."
    # -------------------------------------------------------------------------
    print("--- TEST 8: Suggest one practical way to save money. ---")
    q8 = "Suggest one practical way to save money."
    res8 = await insight_svc.spending_insights(
        SpendingInsightRequest(question=q8, include_recommendations=True),
        user_id=user_id,
    )
    print(f"Summary: {res8.summary}")
    print(f"Key findings: {res8.key_findings}")
    print(f"Recommendations count: {len(res8.recommendations)}")
    for r in res8.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")
        print(f"    Savings: {r.estimated_monthly_savings}")

    t8_pass = (
        len(res8.recommendations) >= 1
        and res8.recommendations[0].estimated_monthly_savings is not None
        and res8.recommendations[0].estimated_monthly_savings > 0
        and "Observation:" in res8.recommendations[0].explanation
        and "Action:" in res8.recommendations[0].explanation
    )
    st8 = PASS if t8_pass else FAIL
    results.append(("TEST 8 — Suggest one practical way to save money.", st8, res8.summary, len(res8.recommendations)))
    print(f"Result: {st8}\n")

    # -------------------------------------------------------------------------
    # EDGE CASE 1: Empty transaction history
    # -------------------------------------------------------------------------
    print("--- EDGE CASE 1: Empty transaction history ---")
    res_empty = await insight_svc.spending_insights(
        SpendingInsightRequest(question="Where can I reduce my spending?", include_recommendations=True),
        user_id="user_nonexistent_empty_12345",
    )
    print(f"Summary: {res_empty.summary}")
    print(f"Recommendations: {res_empty.recommendations}")
    t_empty_pass = (
        "No transaction data found" in res_empty.summary
        and len(res_empty.recommendations) == 0
    )
    st_empty = PASS if t_empty_pass else FAIL
    results.append(("EDGE CASE 1 — Empty transaction history", st_empty, res_empty.summary, len(res_empty.recommendations)))
    print(f"Result: {st_empty}\n")

    # -------------------------------------------------------------------------
    # EDGE CASE 2: Insufficient historical data (1 single transaction)
    # -------------------------------------------------------------------------
    print("--- EDGE CASE 2: Insufficient historical data ---")
    # Temporarily create 1 transaction for an isolated test user
    test_user_single = "test_user_single_tx"
    await db["transactions"].delete_many({"user_id": test_user_single})
    await db["transactions"].insert_one({
        "_id": 999901,
        "user_id": test_user_single,
        "amount": 500.0,
        "category": "food",
        "transaction_type": "expense",
        "description": "Lunch",
        "date": "2026-11-20",
    })
    res_single = await insight_svc.spending_insights(
        SpendingInsightRequest(question="What spending pattern should I watch?", include_recommendations=True),
        user_id=test_user_single,
    )
    print(f"Summary: {res_single.summary}")
    print(f"Recommendations: {res_single.recommendations}")
    t_single_pass = (
        len(res_single.recommendations) == 0  # Does not claim a pattern from 1 single transaction!
    )
    st_single = PASS if t_single_pass else FAIL
    results.append(("EDGE CASE 2 — Insufficient historical data (1 tx)", st_single, res_single.summary, len(res_single.recommendations)))
    print(f"Result: {st_single}\n")

    # -------------------------------------------------------------------------
    # EDGE CASE 3: No configured budgets
    # -------------------------------------------------------------------------
    print("--- EDGE CASE 3: No configured budgets ---")
    test_user_nobudget = "test_user_nobudget_tx"
    await db["transactions"].delete_many({"user_id": test_user_nobudget})
    await db["budgets"].delete_many({"user_id": test_user_nobudget})
    await db["transactions"].insert_many([
        {"_id": 999911, "user_id": test_user_nobudget, "amount": 4000.0, "category": "groceries", "transaction_type": "expense", "description": "Grocery", "date": "2026-11-10"},
        {"_id": 999912, "user_id": test_user_nobudget, "amount": 6000.0, "category": "groceries", "transaction_type": "expense", "description": "Supermarket", "date": "2026-11-15"},
    ])
    res_nobudget = await insight_svc.spending_insights(
        SpendingInsightRequest(question="Which categories are exceeding their budgets?", include_recommendations=True),
        user_id=test_user_nobudget,
    )
    print(f"Summary: {res_nobudget.summary}")
    print(f"Recommendations count: {len(res_nobudget.recommendations)}")
    for r in res_nobudget.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")
    t_nobudget_pass = (
        "no configured budgets" in res_nobudget.summary.lower()
        and any("Set Up Category Budgets" in r.title for r in res_nobudget.recommendations)
    )
    st_nobudget = PASS if t_nobudget_pass else FAIL
    results.append(("EDGE CASE 3 — No configured budgets", st_nobudget, res_nobudget.summary, len(res_nobudget.recommendations)))
    print(f"Result: {st_nobudget}\n")

    # -------------------------------------------------------------------------
    # EDGE CASE 4: User with only income records
    # -------------------------------------------------------------------------
    print("--- EDGE CASE 4: User with only income records ---")
    test_user_only_inc = "test_user_only_income_tx"
    await db["transactions"].delete_many({"user_id": test_user_only_inc})
    await db["transactions"].insert_many([
        {"_id": 999921, "user_id": test_user_only_inc, "amount": 50000.0, "category": "salary", "transaction_type": "income", "description": "Salary", "date": "2026-11-01"},
        {"_id": 999922, "user_id": test_user_only_inc, "amount": 15000.0, "category": "freelance", "transaction_type": "income", "description": "Gig", "date": "2026-11-15"},
    ])
    res_only_inc = await insight_svc.spending_insights(
        SpendingInsightRequest(question="Where can I reduce my spending?", include_recommendations=True),
        user_id=test_user_only_inc,
    )
    print(f"Summary: {res_only_inc.summary}")
    print(f"Recommendations: {res_only_inc.recommendations}")
    t_only_inc_pass = (
        "no recorded operating expenses" in res_only_inc.summary.lower()
        and len(res_only_inc.recommendations) == 0
    )
    st_only_inc = PASS if t_only_inc_pass else FAIL
    results.append(("EDGE CASE 4 — User with only income records", st_only_inc, res_only_inc.summary, len(res_only_inc.recommendations)))
    print(f"Result: {st_only_inc}\n")

    # -------------------------------------------------------------------------
    # EDGE CASE 5: User with only expense records (deficit)
    # -------------------------------------------------------------------------
    print("--- EDGE CASE 5: User with only expense records ---")
    test_user_only_exp = "test_user_only_exp_tx"
    await db["transactions"].delete_many({"user_id": test_user_only_exp})
    await db["transactions"].insert_many([
        {"_id": 999931, "user_id": test_user_only_exp, "amount": 8000.0, "category": "rent", "transaction_type": "expense", "description": "Room rent", "date": "2026-11-02"},
        {"_id": 999932, "user_id": test_user_only_exp, "amount": 4000.0, "category": "utilities", "transaction_type": "expense", "description": "Power", "date": "2026-11-12"},
    ])
    res_only_exp = await insight_svc.spending_insights(
        SpendingInsightRequest(question="Am I saving enough based on my income and expenses?", include_recommendations=True),
        user_id=test_user_only_exp,
    )
    print(f"Summary: {res_only_exp.summary}")
    print(f"Recommendations count: {len(res_only_exp.recommendations)}")
    for r in res_only_exp.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")
    t_only_exp_pass = (
        "12,000" in res_only_exp.summary
        and len(res_only_exp.recommendations) > 0
        and any("Deficit" in r.title for r in res_only_exp.recommendations)
    )
    st_only_exp = PASS if t_only_exp_pass else FAIL
    results.append(("EDGE CASE 5 — User with only expense records", st_only_exp, res_only_exp.summary, len(res_only_exp.recommendations)))
    print(f"Result: {st_only_exp}\n")

    # -------------------------------------------------------------------------
    # EDGE CASE 6: Multi-tenant user isolation
    # -------------------------------------------------------------------------
    print("--- EDGE CASE 6: Multi-tenant user data isolation ---")
    # Verify User B cannot see User A's data in recommendations
    test_user_a = "tenant_user_a_private"
    test_user_b = "tenant_user_b_private"
    await db["transactions"].delete_many({"user_id": {"$in": [test_user_a, test_user_b]}})
    await db["transactions"].insert_one({
        "_id": 999941, "user_id": test_user_a, "amount": 45000.0, "category": "secret_investment", "transaction_type": "expense", "description": "User A Private Vault", "date": "2026-11-05"
    })
    await db["transactions"].insert_many([
        {"_id": 999942, "user_id": test_user_b, "amount": 3000.0, "category": "books", "transaction_type": "expense", "description": "Textbook", "date": "2026-11-06"},
        {"_id": 999943, "user_id": test_user_b, "amount": 2000.0, "category": "books", "transaction_type": "expense", "description": "Novel", "date": "2026-11-16"},
    ])
    res_user_b = await insight_svc.spending_insights(
        SpendingInsightRequest(question="Where can I reduce my spending?", include_recommendations=True),
        user_id=test_user_b,
    )
    print(f"User B Summary: {res_user_b.summary}")
    for r in res_user_b.recommendations:
        print(f"  * Title: {r.title}")
        print(f"    Explanation: {r.explanation}")
    t_iso_pass = (
        "secret_investment" not in res_user_b.summary.lower()
        and "45000" not in res_user_b.summary
        and not any("secret_investment" in r.explanation.lower() or "45000" in r.explanation for r in res_user_b.recommendations)
        and "books" in res_user_b.summary.lower()
        and "5,000" in res_user_b.summary
    )
    st_iso = PASS if t_iso_pass else FAIL
    results.append(("EDGE CASE 6 — Multi-tenant data isolation", st_iso, res_user_b.summary, len(res_user_b.recommendations)))
    print(f"Result: {st_iso}\n")

    # Cleanup temporary test users
    await db["transactions"].delete_many({"user_id": {"$in": [test_user_single, test_user_nobudget, test_user_only_inc, test_user_only_exp, test_user_a, test_user_b]}})

    await close_database()

    print("================================================================================")
    print("FINAL SUMMARY OF RECOMMENDATION TESTS")
    print("================================================================================")
    all_passed = True
    for name, st, summary_text, rec_cnt in results:
        print(f"{st} {name} (Recs: {rec_cnt})")
        if st != PASS:
            all_passed = False

    if all_passed:
        print("\nALL RECOMMENDATION TESTS PASSED 100% ON LIVE DATA!")
    else:
        print("\nSOME RECOMMENDATION TESTS FAILED.")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(run_recommendation_tests())
