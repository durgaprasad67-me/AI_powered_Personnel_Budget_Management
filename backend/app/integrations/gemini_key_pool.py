"""Thread-safe Gemini API-key rotation with per-key cooldowns."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from pydantic import SecretStr

logger = logging.getLogger(__name__)

T = TypeVar("T")

COOLDOWNS = {
    "rate_limit": 65.0,
    "daily_quota": 60.0 * 60.0,
    "bad_key": 60.0 * 60.0,
}
ROTATABLE_KINDS = frozenset(COOLDOWNS)


class AllKeysExhausted(RuntimeError):
    def __init__(self, retry_in: float) -> None:
        self.retry_in = max(0.0, float(retry_in))
        super().__init__("All configured Gemini keys are temporarily unavailable.")


class GeminiKeyPool:
    """Round-robin key pool. Keys are stored as SecretStr values."""

    def __init__(
        self,
        keys: Iterable[str | SecretStr],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        unique: list[SecretStr] = []
        seen: set[str] = set()
        for candidate in keys:
            value = (
                candidate.get_secret_value()
                if isinstance(candidate, SecretStr)
                else str(candidate)
            ).strip()
            if value and value not in seen:
                seen.add(value)
                unique.append(SecretStr(value))

        self._keys = tuple(unique)
        self._clock = clock
        self._cooldowns: dict[str, float] = {}
        self._cursor = 0
        self._lock = threading.RLock()

    @property
    def key_count(self) -> int:
        return len(self._keys)

    @staticmethod
    def _raw(key: str | SecretStr) -> str:
        return key.get_secret_value() if isinstance(key, SecretStr) else str(key)

    @staticmethod
    def _mask(key: str | SecretStr) -> str:
        raw = GeminiKeyPool._raw(key)
        return f"****{raw[-4:]}" if len(raw) > 4 else "****"

    def acquire(self) -> SecretStr:
        with self._lock:
            now = self._clock()
            count = len(self._keys)
            for offset in range(count):
                index = (self._cursor + offset) % count
                key = self._keys[index]
                if self._cooldowns.get(self._raw(key), 0.0) <= now:
                    self._cursor = (index + 1) % count
                    return key

            retry_in = self._retry_in_locked(now)
            raise AllKeysExhausted(retry_in)

    def penalize(self, key: str | SecretStr, kind: str) -> None:
        cooldown = COOLDOWNS.get(kind)
        if cooldown is None:
            return
        raw = self._raw(key)
        with self._lock:
            if raw not in {self._raw(item) for item in self._keys}:
                return
            self._cooldowns[raw] = max(
                self._cooldowns.get(raw, 0.0),
                self._clock() + cooldown,
            )

    def retry_in(self) -> float:
        with self._lock:
            return self._retry_in_locked(self._clock())

    def _retry_in_locked(self, now: float) -> float:
        remaining = [
            until - now
            for until in self._cooldowns.values()
            if until > now
        ]
        return min(remaining) if remaining else 0.0

    def status(self) -> list[dict[str, str | bool | float]]:
        with self._lock:
            now = self._clock()
            return [
                {
                    "key": self._mask(key),
                    "available": self._cooldowns.get(self._raw(key), 0.0) <= now,
                    "cooldown_remaining": round(
                        max(0.0, self._cooldowns.get(self._raw(key), 0.0) - now),
                        3,
                    ),
                }
                for key in self._keys
            ]


def _exception_chain(exc: BaseException) -> list[BaseException]:
    pending = [exc]
    visited: set[int] = set()
    chain: list[BaseException] = []
    while pending:
        current = pending.pop(0)
        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)
        chain.append(current)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return chain


def classify(exc: BaseException) -> str:
    """Classify Gemini errors, including wrapped SDK/LangChain exceptions."""
    statuses: set[str] = set()
    messages: list[str] = []
    for current in _exception_chain(exc):
        messages.append(f"{type(current).__name__} {current}")
        for attribute in ("status_code", "code", "status"):
            value = getattr(current, attribute, None)
            if value is not None:
                statuses.add(str(getattr(value, "value", value)).upper())

    text = " ".join(messages).upper()
    status_text = " ".join(statuses)

    if (
        "DAILY QUOTA" in text
        or "PER-DAY QUOTA" in text
        or "PER DAY QUOTA" in text
        or "QUOTA PER DAY" in text
        or ("QUOTA" in text and "DAY" in text and "EXCEEDED" in text)
    ):
        return "daily_quota"

    if (
        "401" in status_text
        or "403" in status_text
        or re.search(r"\b(?:401|403)\b", text)
        or "API_KEY_INVALID" in text
        or "INVALID API KEY" in text
        or "API KEY NOT VALID" in text
        or "PERMISSION_DENIED" in text
    ):
        return "bad_key"

    if (
        "429" in status_text
        or "503" in status_text
        or re.search(r"\b(?:429|503)\b", text)
        or "RESOURCE_EXHAUSTED" in text
        or "RATE LIMIT" in text
        or "TOO MANY REQUESTS" in text
        or "QUOTA EXCEEDED" in text
    ):
        return "rate_limit"

    return "other"


def call_with_rotation(pool: GeminiKeyPool, fn: Callable[[SecretStr], T]) -> T:
    last_error: BaseException | None = None
    attempts = 0
    while attempts < pool.key_count:
        try:
            key = pool.acquire()
        except AllKeysExhausted as exc:
            if last_error is not None:
                raise AllKeysExhausted(exc.retry_in) from last_error
            raise

        try:
            return fn(key)
        except Exception as exc:
            kind = classify(exc)
            if kind not in ROTATABLE_KINDS:
                raise
            pool.penalize(key, kind)
            logger.warning(
                json.dumps(
                    {
                        "event": "gemini_key_rotation",
                        "key_id": pool._mask(key),
                        "error_kind": kind,
                    },
                    separators=(",", ":"),
                )
            )
            last_error = exc
            attempts += 1

    raise AllKeysExhausted(pool.retry_in()) from last_error


async def acall_with_rotation(
    pool: GeminiKeyPool,
    fn: Callable[[SecretStr], Any],
) -> Any:
    last_error: BaseException | None = None
    attempts = 0
    while attempts < pool.key_count:
        try:
            key = pool.acquire()
        except AllKeysExhausted as exc:
            if last_error is not None:
                raise AllKeysExhausted(exc.retry_in) from last_error
            raise

        try:
            result = fn(key)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as exc:
            kind = classify(exc)
            if kind not in ROTATABLE_KINDS:
                raise
            pool.penalize(key, kind)
            logger.warning(
                json.dumps(
                    {
                        "event": "gemini_key_rotation",
                        "key_id": pool._mask(key),
                        "error_kind": kind,
                    },
                    separators=(",", ":"),
                )
            )
            last_error = exc
            attempts += 1

    raise AllKeysExhausted(pool.retry_in()) from last_error
