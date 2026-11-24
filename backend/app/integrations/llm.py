from __future__ import annotations

import math
from collections.abc import Sequence
from functools import lru_cache

import httpx
from google import genai
from google.genai import types
from langchain_core.embeddings import Embeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from app.core.config import get_settings
from app.integrations.gemini_key_pool import (
    GeminiKeyPool,
    acall_with_rotation,
    call_with_rotation,
)


class LLMNotConfiguredError(RuntimeError):
    """Raised when no Gemini API key is configured."""


class _GeminiHttpxTransport(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """HTTPX transport for SDK sync and async clients; avoids its aiohttp path."""

    def __init__(self) -> None:
        self._sync_transport = httpx.HTTPTransport()
        self._async_transport = httpx.AsyncHTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._sync_transport.handle_request(request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._async_transport.handle_async_request(request)

    def close(self) -> None:
        self._sync_transport.close()

    async def aclose(self) -> None:
        await self._async_transport.aclose()


@lru_cache(maxsize=1)
def get_gemini_key_pool() -> GeminiKeyPool:
    keys = get_settings().configured_gemini_keys()
    if not keys:
        raise LLMNotConfiguredError(
            "Set GEMINI_API_KEYS, GEMINI_API_KEY_1 through GEMINI_API_KEY_3, "
            "or the legacy GEMINI_API_KEY in the environment."
        )
    return GeminiKeyPool(keys)


def _key_value(api_key: str | SecretStr) -> str:
    return api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key


def _http_options():
    settings = get_settings()
    return types.HttpOptions(
        timeout=max(1, int(settings.gemini_request_timeout_seconds * 1000)),
        retry_options=types.HttpRetryOptions(attempts=1),
        async_client_args={"transport": _GeminiHttpxTransport()},
    )


def get_gemini_client(api_key: str | SecretStr) -> genai.Client:
    """Create a fresh SDK client for the key selected by the pool."""
    if not _key_value(api_key):
        raise LLMNotConfiguredError("Gemini API key is empty.")
    return genai.Client(api_key=_key_value(api_key), http_options=_http_options())


def get_chat_model(api_key: str | SecretStr) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    if not _key_value(api_key):
        raise LLMNotConfiguredError("Gemini API key is empty.")
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=SecretStr(_key_value(api_key)),
        temperature=0.0,
        retries=1,
        request_timeout=settings.gemini_request_timeout_seconds,
        max_tokens=settings.gemini_max_output_tokens,
        client_args={"transport": _GeminiHttpxTransport()},
    )


class RotatingGeminiEmbeddings(Embeddings):
    """LangChain embedding interface backed by per-request pooled clients."""

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.gemini_embedding_model
        self.dimensions = settings.gemini_embedding_dim
        self.batch_size = settings.gemini_embedding_batch_size
        self.pool = get_gemini_key_pool()

    def _normalise(self, vector: Sequence[float]) -> list[float]:
        values = [float(value) for value in vector]
        if self.dimensions < 3072:
            norm = math.sqrt(sum(value * value for value in values))
            if norm == 0:
                raise ValueError("Gemini returned a zero-length embedding vector.")
            values = [value / norm for value in values]
        if len(values) != self.dimensions:
            raise ValueError(
                "Gemini embedding dimension mismatch: "
                f"expected {self.dimensions}, got {len(values)}."
            )
        return values

    def _embed_batch(self, texts: list[str], task_type: str) -> list[list[float]]:
        def embed(api_key: SecretStr) -> list[list[float]]:
            client = get_gemini_client(api_key)
            response = client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.dimensions,
                ),
            )
            embeddings = response.embeddings or []
            if len(embeddings) != len(texts):
                raise ValueError(
                    "Gemini returned a different number of embeddings than inputs."
                )
            return [self._normalise(item.values or []) for item in embeddings]

        return call_with_rotation(self.pool, embed)

    async def _aembed_batch(
        self,
        texts: list[str],
        task_type: str,
    ) -> list[list[float]]:
        async def embed(api_key: SecretStr) -> list[list[float]]:
            client = get_gemini_client(api_key)
            response = await client.aio.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.dimensions,
                ),
            )
            embeddings = response.embeddings or []
            if len(embeddings) != len(texts):
                raise ValueError(
                    "Gemini returned a different number of embeddings than inputs."
                )
            return [self._normalise(item.values or []) for item in embeddings]

        return await acall_with_rotation(self.pool, embed)

    def _batches(self, texts: list[str]):
        for offset in range(0, len(texts), self.batch_size):
            yield texts[offset : offset + self.batch_size]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for batch in self._batches(texts):
            result.extend(self._embed_batch(batch, "RETRIEVAL_DOCUMENT"))
        return result

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text], "RETRIEVAL_QUERY")[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for batch in self._batches(texts):
            result.extend(await self._aembed_batch(batch, "RETRIEVAL_DOCUMENT"))
        return result

    async def aembed_query(self, text: str) -> list[float]:
        return (await self._aembed_batch([text], "RETRIEVAL_QUERY"))[0]


def get_embedding_model() -> RotatingGeminiEmbeddings:
    return RotatingGeminiEmbeddings()
