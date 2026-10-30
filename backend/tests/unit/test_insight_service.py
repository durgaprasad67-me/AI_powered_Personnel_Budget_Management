import asyncio
from types import SimpleNamespace

import pytest

from app.core.exceptions import ExternalServiceError
from app.integrations.llm import LLMNotConfiguredError
from app.schemas.insights import (
    SpendingInsightRequest,
    SpendingSummary,
    TransactionTextRequest,
)
from app.services.insights import InsightService


class FakeAnalytics:
    async def spending_summary(self, start_date, end_date):
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
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
    )


def test_spending_insights_valid_json_clears_recommendations():
    client = fake_client(
        '{"summary":"Good progress","key_findings":[],"recommendations":'
        '[{"title":"Save","explanation":"Save more","estimated_monthly_savings":10}],'
        '"limitations":[]}'
    )
    service = InsightService(FakeAnalytics(), lambda: client)

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
    ("response_text", "detail"),
    [
        ("not json", "The AI returned an invalid response structure."),
        ("", "The AI returned an empty or invalid response."),
    ],
)
def test_spending_insights_maps_invalid_responses(response_text, detail):
    service = InsightService(FakeAnalytics(), lambda: fake_client(response_text))

    with pytest.raises(ExternalServiceError, match=detail):
        asyncio.run(
            service.spending_insights(
                SpendingInsightRequest(question="How can I save?")
            )
        )


def test_missing_key_returns_service_unavailable():
    def missing_key():
        raise LLMNotConfiguredError

    service = InsightService(FakeAnalytics(), missing_key)

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
    service = InsightService(FakeAnalytics(), lambda: client)

    result = asyncio.run(
        service.extract_transaction(
            TransactionTextRequest(text="Spent 10 on lunch")
        )
    )

    assert result.requires_confirmation is True
