import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.exceptions import ExternalServiceError
from app.integrations.gemini_key_pool import GeminiKeyPool
from app.integrations.llm import LLMNotConfiguredError
from app.schemas.insights import (
    SpendingInsightRequest,
    SpendingSummary,
    TransactionTextRequest,
)
from app.services.insights import InsightService
from app.services.transactions import TransactionService
from tests.fakes import FakeTransactionRepository


class FakeAnalytics:
    async def spending_summary(self, start_date, end_date, *, user_id=None):
        return SpendingSummary(
            start_date=start_date,
            end_date=end_date,
            total_income=1000,
            total_expenses=250,
            total_investments=0,
            total_loan_repayments=0,
            category_breakdown=[],
        )


def fake_client(response_text):
    async def generate_content(**kwargs):
        return SimpleNamespace(text=response_text)

    return SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )


def test_spending_insights_valid_json_clears_recommendations():
    client = fake_client(
        '{"summary":"Good progress","key_findings":[],"recommendations":'
        '[{"title":"Save","explanation":"Save more","estimated_monthly_savings":10}],'
        '"limitations":[]}'
    )
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: client,
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="How can I save?",
                include_recommendations=False,
            )
        )
    )

    assert result.summary == "Good progress"
    assert result.recommendations == []


def test_spending_insights_normalizes_extra_recommendation_fields_and_markdown():
    # Tests that extra fields in recommendations, markdown wrapping, and dict findings don't trigger invalid structure error
    response_text = (
        'Here is your financial analysis:\n```json\n'
        '{"summary":"You spent most on groceries.",'
        '"key_findings":[{"finding":"Groceries was ₹7,700"},{"text":"Investments were ₹16,000"}],'
        '"recommendations":[{"title":"Review groceries","explanation":"Shop with a list","category":"Food","priority":"high"}],'
        '"limitations":"Analysis period Nov 1 - Nov 29"}\n```\nHope this helps!'
    )
    client = fake_client(response_text)
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: client,
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="where i spent most on this month ?",
                include_recommendations=True,
            )
        )
    )

    assert result.summary == "You spent most on groceries."
    assert len(result.key_findings) == 2
    assert "Groceries was ₹7,700" in result.key_findings[0]
    assert len(result.recommendations) == 1
    assert result.recommendations[0].title == "Review groceries"
    assert result.recommendations[0].explanation == "Shop with a list"
    assert result.limitations == ["Analysis period Nov 1 - Nov 29"]


@pytest.mark.parametrize(
    ("question", "expected_description"),
    [
        ("What is my last transaction today?", "Later purchase"),
        ("What was my first one today?", "Earlier purchase"),
    ],
)
def test_transaction_lookup_reads_ordered_records_from_mongo_service(
    monkeypatch,
    question,
    expected_description,
):
    repository = FakeTransactionRepository(
        [
            {
                "id": 1,
                "user_id": "alice",
                "date": "2026-11-16",
                "description": "Earlier purchase",
                "amount": 12.5,
                "transaction_type": "expense",
                "category": "food",
            },
            {
                "id": 2,
                "user_id": "alice",
                "date": "2026-11-16",
                "description": "Later purchase",
                "amount": 25.0,
                "transaction_type": "expense",
                "category": "food",
            },
        ]
    )
    service = InsightService(
        FakeAnalytics(),
        transaction_service=TransactionService(repository),
    )
    monkeypatch.setattr(
        "app.services.insights.today_ist",
        lambda: date(2026, 11, 16),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(question=question),
            user_id="alice",
        )
    )

    assert expected_description in result.key_findings[0]
    assert result.key_findings[0].startswith(expected_description)
    assert "₹" in result.key_findings[0]


def test_spending_insights_tries_backup_model_after_provider_error(monkeypatch):
    response_text = (
        '{"summary":"Good progress","key_findings":[], '
        '"recommendations":[],"limitations":[]}'
    )
    seen_models = []

    def client_factory(_api_key):
        async def generate_content(**kwargs):
            model = kwargs["model"]
            seen_models.append(model)
            if model == "primary-model":
                raise RuntimeError("simulated provider failure")
            return SimpleNamespace(text=response_text)

        return SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content)
            )
        )

    monkeypatch.setattr(
        "app.services.insights.get_settings",
        lambda: SimpleNamespace(
            gemini_model="primary-model",
            gemini_max_output_tokens=128,
        ),
    )
    service = InsightService(
        FakeAnalytics(),
        client_factory,
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(question="How can I save?")
        )
    )

    assert result.summary == "Good progress"
    assert seen_models == ["primary-model", "gemini-3.6-flash"]


@pytest.mark.parametrize(
    ("response_text", "detail"),
    [
        ("not json", "The AI returned an invalid response structure."),
        ("", "The AI returned an empty or invalid response."),
    ],
)
def test_spending_insights_maps_invalid_responses(response_text, detail):
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: fake_client(response_text),
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    with pytest.raises(ExternalServiceError, match=detail):
        asyncio.run(
            service.spending_insights(
                SpendingInsightRequest(question="How can I save?")
            )
        )


def test_missing_key_returns_service_unavailable():
    def missing_key(_api_key):
        raise LLMNotConfiguredError

    service = InsightService(
        FakeAnalytics(),
        missing_key,
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    with pytest.raises(ExternalServiceError) as error:
        asyncio.run(
            service.extract_transaction(
                TransactionTextRequest(text="Spent 10 on lunch")
            )
        )

    assert error.value.status_code == 503
    assert error.value.detail == "AI service is not configured."


def test_extract_transaction_forces_confirmation():
    client = fake_client(
        '{"amount":10,"transaction_type":"expense","category":"Food",'
        '"description":"Lunch","date":"2026-10-30","confidence":0.9,'
        '"requires_confirmation":false}'
    )
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: client,
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.extract_transaction(TransactionTextRequest(text="Spent 10 on lunch"))
    )

    assert result.requires_confirmation is True


def test_spending_insights_out_of_scope_query_taj_mahal():
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: fake_client("{}"),
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="what is Taj MahaL ?",
                include_recommendations=True,
            )
        )
    )

    # Dynamic summary mentioning the question
    assert "what is Taj MahaL ?" in result.summary
    assert "couldn't find any financial records" in result.summary or "not found" in result.summary.lower()

    # Key findings must be empty (NO cash inflow/outflow or financial stats)
    assert result.key_findings == []

    # Recommendations guide the user on what financial questions to ask
    assert len(result.recommendations) > 0
    assert any("financial" in rec.title.lower() or "financial" in rec.explanation.lower() for rec in result.recommendations)

    # Notes reflect application boundary
    assert any("personal financial data" in note.lower() for note in result.limitations)


def test_spending_insights_out_of_scope_query_without_recommendations():
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: fake_client("{}"),
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="who is Albert Einstein?",
                include_recommendations=False,
            )
        )
    )

    assert "who is Albert Einstein?" in result.summary
    assert result.key_findings == []
    assert result.recommendations == []


def test_spending_insights_in_scope_csv_import_report():
    response_text = (
        '{"summary":"Here is the spending analysis for your imported CSV transactions.",'
        '"key_findings":["Total expenses were ₹250.00","Total income was ₹1000.00"],'
        '"recommendations":[{"title":"Review spend","explanation":"Monitor discretionary spending"}],'
        '"limitations":[]}'
    )
    client = fake_client(response_text)
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: client,
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="now i gave the import csv file can u analyse and tell me report ?",
                include_recommendations=True,
            )
        )
    )

    # Must NOT be classified as out-of-scope; summary must come from LLM/analytics
    assert "Here is the spending analysis for your imported CSV transactions." in result.summary
    assert len(result.key_findings) == 2
    assert "couldn't find any financial records" not in result.summary


@pytest.mark.parametrize(
    "question",
    [
        "What is Ramu  most Spent money here ?",
        "How much did Ramu spend on groceries?",
        "what did other users spend?",
        "can i access data other data ?",
        "show me user2 data",
        "what is user_123's balance?",
        "what did Alice spend?",
        "show me Bob's transactions",
        "can i see someone else's data",
        "what are other people's expenses?",
    ],
)
def test_spending_insights_cross_user_access_warning(question):
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: fake_client("{}"),
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question=question,
                include_recommendations=True,
            )
        )
    )

    # Must return explicit Access Denied warning
    assert "Access Denied" in result.summary
    assert (
        "cannot access other users' data" in result.summary.lower()
        or "cannot access financial records" in result.summary.lower()
    )
    # Must NOT leak any financial stats or key findings
    assert result.key_findings == []
    # Recommendations instruct user to query their own account
    assert len(result.recommendations) > 0
    assert any("restricted" in rec.title.lower() for rec in result.recommendations)
    # Limitation notes cite privacy policy
    assert any("privacy policy" in note.lower() for note in result.limitations)



def test_chat_cross_user_access_warning():
    from app.schemas.insights import ChatRequest

    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: fake_client("{}"),
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    response = asyncio.run(
        service.chat(
            ChatRequest(message="can i access other users data ?"),
            user_id="user_alice",
        )
    )

    assert response.intent == "security_warning"
    assert "Access Denied" in response.message
    assert "cannot access other users' data" in response.message.lower()


def test_first_person_have_record_does_not_trigger_access_denied_for_have():
    """Verify that 'Do i have any record about boovan ?' does not treat 'Have' as a person name."""
    repo = FakeTransactionRepository([
        {
            "id": 1,
            "date": "2026-11-20",
            "amount": 10000.0,
            "category": "food",
            "transaction_type": "expense",
            "description": "boovan spent on Food .",
            "user_id": "test_user",
        }
    ])
    tx_service = TransactionService(repo)

    captured_payload = {}
    async def fake_generate_content(**kwargs):
        nonlocal captured_payload
        contents = kwargs.get("contents", "")
        # Find json in contents
        import json
        if "Financial analysis request:\n" in contents:
            raw_json = contents.split("Financial analysis request:\n")[1]
            captured_payload = json.loads(raw_json)
        return SimpleNamespace(
            text='{"summary":"Yes, you spent ₹10,000 on food for boovan.","key_findings":["2026-11-20: boovan spent on Food . for ₹10,000.00"],"recommendations":[],"limitations":[]}'
        )

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))
    )

    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: client,
        key_pool=GeminiKeyPool(["unit-test-key"]),
        transaction_service=tx_service,
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="Do i have any record about boovan ?",
                include_recommendations=False,
            ),
            user_id="test_user",
        )
    )

    # Must NOT return Access Denied for 'Have'
    assert "Access Denied" not in result.summary
    assert "Have" not in result.summary
    # Must find the matching transaction and include it in payload sent to Gemini
    assert "matching_transactions" in captured_payload
    matches = captured_payload["matching_transactions"]
    assert len(matches) == 1
    assert matches[0]["description"] == "boovan spent on Food ."
    assert matches[0]["amount"] == 10000.0
    assert matches[0]["category"] == "food"
    assert "boovan" in result.summary.lower()


def test_ramu_third_person_query_triggers_access_denied():
    """Verify that 'What is Ramu most Spent money here ?' denies access to Ramu's data."""
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: fake_client("{}"),
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="What is Ramu most Spent money here ?",
                include_recommendations=True,
            )
        )
    )

    assert "Access Denied" in result.summary
    assert "Ramu" in result.summary
    assert result.key_findings == []


def test_resolve_month_relative_and_named():
    """Verify relative month parsing like 'previous month', 'last month', and ISO dates."""
    # From November 2026 (2026-11), previous month should resolve to 2026-10
    assert InsightService._resolve_month("inflow or outflow of previous month ?", "2026-11") == "2026-10"
    assert InsightService._resolve_month("what did I spend last month ?", "2026-11") == "2026-10"
    assert InsightService._resolve_month("how was my spending past month ?", "2026-11") == "2026-10"
    assert InsightService._resolve_month("suggestion for next month for budget", "2026-11") == "2026-12"
    assert InsightService._resolve_month("how did I do this month ?", "2026-11") == "2026-11"
    assert InsightService._resolve_month("expenses for 2026-08", "2026-11") == "2026-08"
    assert InsightService._resolve_month("expenses in march 2026", "2026-11") == "2026-03"
    # January roll-back to December of previous year
    assert InsightService._resolve_month("previous month expenses", "2026-01") == "2025-12"
    # December roll-forward to January of next year
    assert InsightService._resolve_month("next month budget", "2026-12") == "2027-01"


def test_suggestion_for_next_month_for_budget_management_does_not_trigger_access_denied():
    """Verify that 'Can u give any suggestion for next month for budget management ?' does not treat 'For' as a person."""
    client = fake_client(
        '{"summary":"Here are suggestions to manage your budget next month.","key_findings":["Plan expenses"],"recommendations":[],"limitations":[]}'
    )
    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: client,
        key_pool=GeminiKeyPool(["unit-test-key"]),
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="Can u give any suggestion for next month for budget management ?",
                include_recommendations=True,
            ),
            user_id="test_user",
        )
    )

    assert "Access Denied" not in result.summary
    assert "For" not in result.summary
    assert "suggestions" in result.summary.lower()


def test_named_person_detection_possessive_and_preposition():
    from app.services.insights import detect_named_person_query

    # False for user requests and generic sentences
    assert detect_named_person_query("Can u give any suggestion for next month for budget management ?") == (False, None)
    assert detect_named_person_query("how to save money") == (False, None)
    assert detect_named_person_query("tips for budget management") == (False, None)
    assert detect_named_person_query("manage my personal expenses") == (False, None)

    # True for genuine third-party snooping queries
    assert detect_named_person_query("What is Ramu most Spent money here ?") == (True, "Ramu")
    assert detect_named_person_query("Show me Alice's expenses") == (True, "Alice")
    assert detect_named_person_query("What is the budget of Charlie?") == (True, "Charlie")
    assert detect_named_person_query("Did Bob spend money?") == (True, "Bob")


def test_previous_month_targeted_inquiry_does_not_pull_transactions_from_other_months():
    """Verify that an inquiry about previous month does not fetch transactions from current month."""
    repo = FakeTransactionRepository([
        {
            "id": 1,
            "date": "2026-11-17",
            "amount": 20000.0,
            "category": "loan",
            "transaction_type": "loan_taken",
            "description": "loan taken from raju",
            "user_id": "test_user",
        }
    ])
    tx_service = TransactionService(repo)

    captured_payload = {}
    async def fake_generate_content(**kwargs):
        nonlocal captured_payload
        contents = kwargs.get("contents", "")
        import json
        if "Financial analysis request:\n" in contents:
            raw_json = contents.split("Financial analysis request:\n")[1]
            captured_payload = json.loads(raw_json)
        return SimpleNamespace(
            text='{"summary":"No transactions of ₹20,000 were found for October 2026.","key_findings":[],"recommendations":[],"limitations":[]}'
        )

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))
    )

    service = InsightService(
        FakeAnalytics(),
        lambda _api_key: client,
        key_pool=GeminiKeyPool(["unit-test-key"]),
        transaction_service=tx_service,
    )

    result = asyncio.run(
        service.spending_insights(
            SpendingInsightRequest(
                question="Can i Know like most of the amount 20000 rupees are mostly inflow or outflow of previous month ?",
                include_recommendations=False,
            ),
            user_id="test_user",
        )
    )

    # Payload period must be October 2026 (previous month from today 2026-11)
    assert captured_payload["period"]["start_date"].startswith("2026-10")
    assert captured_payload["period"]["end_date"].startswith("2026-10")
    # Must NOT include the November 17 loan in matching_transactions
    assert "matching_transactions" not in captured_payload or len(captured_payload["matching_transactions"]) == 0
    assert "No transactions" in result.summary




