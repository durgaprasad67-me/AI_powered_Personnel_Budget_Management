import asyncio

import pytest

from app.core.config import get_settings
from app.integrations.llm import get_embedding_model
from app.services.rag.answering import generate_response

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not get_settings().configured_gemini_keys(),
        reason="Gemini environment keys are not configured",
    ),
]


def test_live_gemini_embedding_and_generation():
    vector = get_embedding_model().embed_query("FinSight live connectivity probe")
    assert len(vector) == get_settings().gemini_embedding_dim

    answer = asyncio.run(
        generate_response(
            "What amount does the context record for the Fresh Mart purchase?",
            context="Transaction record: Fresh Mart grocery purchase, amount ₹42.75.",
        )
    )
    assert "42.75" in answer
