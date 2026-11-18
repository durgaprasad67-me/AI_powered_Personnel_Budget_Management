import asyncio
import json
import logging

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.gemini_key_pool import (
    AllKeysExhausted,
    GeminiKeyPool,
    acall_with_rotation,
    call_with_rotation,
    classify,
)
from app.main import gemini_keys_exhausted_handler


class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def secret_value(key):
    return key.get_secret_value()


def test_round_robin_skips_cooling_keys_and_recovers():
    clock = FakeClock()
    pool = GeminiKeyPool(["first-key", "second-key"], clock=clock)

    first = pool.acquire()
    assert secret_value(first) == "first-key"
    pool.penalize(first, "rate_limit")
    assert secret_value(pool.acquire()) == "second-key"

    clock.advance(65)
    assert secret_value(pool.acquire()) == "first-key"


def test_all_keys_exhausted_reports_earliest_recovery():
    clock = FakeClock()
    pool = GeminiKeyPool(["daily-key", "busy-key"], clock=clock)
    pool.penalize("daily-key", "daily_quota")
    pool.penalize("busy-key", "rate_limit")

    with pytest.raises(AllKeysExhausted) as error:
        pool.acquire()

    assert error.value.retry_in == 65


def test_classify_walks_wrapped_exception_chain():
    class SdkFailure(Exception):
        code = 429

    try:
        try:
            raise SdkFailure("RESOURCE_EXHAUSTED")
        except SdkFailure as cause:
            raise RuntimeError("LangChain request failed") from cause
    except RuntimeError as wrapped:
        assert classify(wrapped) == "rate_limit"

    assert classify(RuntimeError("daily quota exceeded per day")) == "daily_quota"
    assert classify(RuntimeError("HTTP 403 API_KEY_INVALID")) == "bad_key"
    assert classify(RuntimeError("invalid payload")) == "other"


def test_sync_rotation_retries_on_a_different_key():
    pool = GeminiKeyPool(["first-key", "second-key"], clock=FakeClock())
    seen = []

    def invoke(key):
        seen.append(secret_value(key))
        if len(seen) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "ok"

    assert call_with_rotation(pool, invoke) == "ok"
    assert seen == ["first-key", "second-key"]


def test_rotation_log_is_json_and_masks_key(caplog):
    pool = GeminiKeyPool(["my-secret-1234", "second-key"], clock=FakeClock())

    def invoke(key):
        if secret_value(key) == "my-secret-1234":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "ok"

    with caplog.at_level(logging.WARNING, logger="app.integrations.gemini_key_pool"):
        assert call_with_rotation(pool, invoke) == "ok"

    record = next(
        item
        for item in caplog.records
        if item.name == "app.integrations.gemini_key_pool"
    )
    event = json.loads(record.message)
    assert event == {
        "event": "gemini_key_rotation",
        "key_id": "****1234",
        "error_kind": "rate_limit",
    }
    assert "my-secret-1234" not in record.message


def test_other_sync_error_is_not_retried():
    pool = GeminiKeyPool(["first-key", "second-key"], clock=FakeClock())
    error = RuntimeError("invalid request")
    calls = []

    def invoke(key):
        calls.append(secret_value(key))
        raise error

    with pytest.raises(RuntimeError) as caught:
        call_with_rotation(pool, invoke)

    assert caught.value is error
    assert calls == ["first-key"]


def test_async_rotation_retries_on_a_different_key():
    pool = GeminiKeyPool(["first-key", "second-key"], clock=FakeClock())
    seen = []

    async def invoke(key):
        seen.append(secret_value(key))
        if len(seen) == 1:
            raise RuntimeError("503 service unavailable")
        return "ok"

    assert asyncio.run(acall_with_rotation(pool, invoke)) == "ok"
    assert seen == ["first-key", "second-key"]


def test_status_masks_keys_and_deduplicates():
    pool = GeminiKeyPool(
        [SecretStr("my-secret-1234"), "my-secret-1234", "tiny"],
        clock=FakeClock(),
    )

    status = pool.status()

    assert [item["key"] for item in status] == ["****1234", "****"]
    assert all("my-secret" not in str(item) for item in status)


def test_settings_parse_key_pool_and_legacy_fallback():
    pool_settings = Settings(
        gemini_api_keys=" first-key,second-key, first-key ",
        _env_file=None,
    )
    assert [secret_value(key) for key in pool_settings.configured_gemini_keys()] == [
        "first-key",
        "second-key",
    ]

    legacy_settings = Settings(gemini_api_key="legacy-key", _env_file=None)
    assert [secret_value(key) for key in legacy_settings.configured_gemini_keys()] == [
        "legacy-key"
    ]

    numbered_settings = Settings(
        gemini_api_key_1=" first-numbered ",
        gemini_api_key_2="second-numbered",
        gemini_api_key_3="first-numbered",
        _env_file=None,
    )
    assert [
        secret_value(key) for key in numbered_settings.configured_gemini_keys()
    ] == ["first-numbered", "second-numbered"]


def test_all_keys_exhausted_maps_to_503_with_retry_after():
    response = asyncio.run(
        gemini_keys_exhausted_handler(None, AllKeysExhausted(6.2))
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "7"
    assert b"temporarily unavailable" in response.body
