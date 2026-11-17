import math
from types import SimpleNamespace

from pydantic import SecretStr

from app.core.config import Settings
from app.integrations import llm
from app.integrations.gemini_key_pool import GeminiKeyPool


def test_gemini_client_uses_explicit_timeout_and_single_attempt(monkeypatch):
    settings = Settings(gemini_api_keys="unit-test-key", _env_file=None)
    captured = {}

    def client_factory(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm.genai, "Client", client_factory)

    llm.get_gemini_client(SecretStr("unit-test-key"))

    options = captured["http_options"]
    assert options.timeout == 30_000
    assert options.retry_options.attempts == 1
    assert isinstance(
        options.async_client_args["transport"], llm._GeminiHttpxTransport
    )


def test_chat_model_sets_retry_timeout_and_output_limit(monkeypatch):
    settings = Settings(
        gemini_api_keys="unit-test-key",
        gemini_request_timeout_seconds=12,
        gemini_max_output_tokens=256,
        _env_file=None,
    )
    captured = {}

    def model_factory(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "ChatGoogleGenerativeAI", model_factory)

    llm.get_chat_model(SecretStr("unit-test-key"))

    assert captured["retries"] == 1
    assert captured["request_timeout"] == 12
    assert captured["max_tokens"] == 256
    assert isinstance(
        captured["client_args"]["transport"], llm._GeminiHttpxTransport
    )
    assert captured["google_api_key"].get_secret_value() == "unit-test-key"


def test_embedding_function_uses_retrieval_tasks_and_normalizes(monkeypatch):
    settings = Settings(gemini_api_keys="unit-test-key", _env_file=None)
    calls = []

    class FakeModels:
        def embed_content(self, **kwargs):
            calls.append(kwargs)
            count = len(kwargs["contents"]) if isinstance(kwargs["contents"], list) else 1
            values = [3.0] + [0.0] * 767
            return SimpleNamespace(
                embeddings=[SimpleNamespace(values=values) for _ in range(count)]
            )

    client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "get_gemini_key_pool", lambda: GeminiKeyPool(["unit-key"]))
    monkeypatch.setattr(llm, "get_gemini_client", lambda _key: client)

    embeddings = llm.RotatingGeminiEmbeddings()
    document_vector = embeddings.embed_documents(["stored text"])[0]
    query_vector = embeddings.embed_query("question")

    assert calls[0]["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert calls[1]["config"].task_type == "RETRIEVAL_QUERY"
    assert calls[0]["config"].output_dimensionality == 768
    assert len(document_vector) == len(query_vector) == 768
    assert math.isclose(sum(value * value for value in document_vector), 1.0)
    assert math.isclose(sum(value * value for value in query_vector), 1.0)
