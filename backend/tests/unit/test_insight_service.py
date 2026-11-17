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
