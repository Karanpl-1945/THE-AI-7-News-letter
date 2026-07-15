"""Shared Groq client with explicit pacing, retries, and error classification."""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from groq import (
    APIConnectionError,
    APITimeoutError,
    Groq,
    InternalServerError,
    RateLimitError,
)


class GroqRequestError(RuntimeError):
    """Base error for a Groq request that the adapter cannot complete."""


class GroqRateLimitError(GroqRequestError):
    """A rate limit remained after the configured retry policy."""

    def __init__(self, message: str, retry_after_seconds: Optional[float] = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class GroqQuotaExhaustedError(GroqRateLimitError):
    """The provider's daily token quota is exhausted."""


@dataclass(frozen=True)
class GroqRequestSettings:
    max_retries: int = 2
    max_retry_wait_seconds: float = 60.0
    request_timeout_seconds: float = 45.0
    min_request_interval_seconds: float = 1.0

    @classmethod
    def from_environment(cls) -> "GroqRequestSettings":
        return cls(
            max_retries=max(0, int(os.getenv("GROQ_MAX_RETRIES", "2"))),
            max_retry_wait_seconds=max(
                0.0, float(os.getenv("GROQ_MAX_RETRY_WAIT_SECONDS", "60"))
            ),
            request_timeout_seconds=max(
                1.0, float(os.getenv("GROQ_REQUEST_TIMEOUT_SECONDS", "45"))
            ),
            min_request_interval_seconds=max(
                0.0, float(os.getenv("GROQ_MIN_REQUEST_INTERVAL_SECONDS", "1"))
            ),
        )


_DURATION_PART = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(ms|h|m|s)", re.IGNORECASE)


def _parse_duration_seconds(value: Any) -> Optional[float]:
    """Parse seconds or compact durations such as ``15m43.488s``."""
    if value is None:
        return None
    text = str(value).strip().lower()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    matches = list(_DURATION_PART.finditer(text))
    if not matches:
        return None
    multipliers = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return sum(float(match.group(1)) * multipliers[match.group(2).lower()] for match in matches)


def _error_message(error: RateLimitError) -> str:
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        detail = body.get("error", body)
        if isinstance(detail, dict) and detail.get("message"):
            return str(detail["message"])
    return str(error)


def _retry_after_seconds(error: RateLimitError) -> Optional[float]:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}

    retry_after_ms = headers.get("retry-after-ms")
    if retry_after_ms is not None:
        raw_milliseconds = str(retry_after_ms).strip().lower()
        if raw_milliseconds.endswith("ms"):
            return _parse_duration_seconds(raw_milliseconds)
        try:
            return max(0.0, float(raw_milliseconds) / 1000.0)
        except ValueError:
            pass

    for name in (
        "retry-after",
        "x-ratelimit-reset-tokens",
        "x-ratelimit-reset-requests",
    ):
        parsed = _parse_duration_seconds(headers.get(name))
        if parsed is not None:
            return parsed

    match = re.search(
        r"try again in\s+([0-9.]+(?:ms|h|m|s)(?:[0-9.]+(?:ms|h|m|s))*)",
        _error_message(error),
        re.IGNORECASE,
    )
    return _parse_duration_seconds(match.group(1)) if match else None


def _is_daily_token_limit(error: RateLimitError) -> bool:
    message = _error_message(error).lower()
    return "tokens per day" in message or "(tpd)" in message or "`tpd`" in message


class GroqRequestGateway:
    """Own the retry policy for Groq JSON chat-completion requests."""

    def __init__(
        self,
        client: Any = None,
        settings: Optional[GroqRequestSettings] = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = lambda: random.uniform(0.0, 0.25),
    ) -> None:
        self.settings = settings or GroqRequestSettings.from_environment()
        self._client = client or Groq(
            api_key=os.environ["GROQ_API_KEY"],
            timeout=self.settings.request_timeout_seconds,
            max_retries=0,
        )
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._pace_lock = threading.Lock()
        self._last_request_at: Optional[float] = None

    def _pace_request(self) -> None:
        with self._pace_lock:
            now = self._monotonic()
            if self._last_request_at is not None:
                remaining = (
                    self.settings.min_request_interval_seconds
                    - (now - self._last_request_at)
                )
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._monotonic()
            self._last_request_at = now

    def _short_retry_delay(self, attempt: int, suggested: Optional[float]) -> float:
        base = suggested if suggested is not None else float(2**attempt)
        return min(base + self._jitter(), self.settings.max_retry_wait_seconds)

    def create_json_completion(
        self,
        *,
        prompt: str,
        model: str,
        max_tokens: int,
    ) -> Dict[str, Any]:
        attempts_allowed = self.settings.max_retries + 1

        for attempt in range(attempts_allowed):
            self._pace_request()
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                )
                content = (response.choices[0].message.content or "{}").strip()
                result = json.loads(content)
                if (
                    isinstance(result, list)
                    and len(result) == 1
                    and isinstance(result[0], dict)
                ):
                    result = result[0]
                if not isinstance(result, dict):
                    raise GroqRequestError("Groq JSON response must be an object")
                return result
            except RateLimitError as error:
                retry_after = _retry_after_seconds(error)
                if _is_daily_token_limit(error):
                    raise GroqQuotaExhaustedError(
                        "Groq daily token quota is exhausted; retry after the provider reset.",
                        retry_after_seconds=retry_after,
                    ) from error

                if (
                    retry_after is not None
                    and retry_after > self.settings.max_retry_wait_seconds
                ):
                    raise GroqRateLimitError(
                        "Groq requested a retry wait longer than this workflow allows.",
                        retry_after_seconds=retry_after,
                    ) from error

                if attempt >= self.settings.max_retries:
                    raise GroqRateLimitError(
                        "Groq rate limit remained after all configured retries.",
                        retry_after_seconds=retry_after,
                    ) from error

                self._sleep(self._short_retry_delay(attempt, retry_after))
            except (APITimeoutError, APIConnectionError, InternalServerError) as error:
                if attempt >= self.settings.max_retries:
                    raise GroqRequestError(
                        "Groq transient request failed after all configured retries."
                    ) from error
                self._sleep(self._short_retry_delay(attempt, suggested=None))

        raise GroqRequestError("Groq request ended without a response")


_gateway: Optional[GroqRequestGateway] = None
_gateway_lock = threading.Lock()


def get_groq_gateway() -> GroqRequestGateway:
    global _gateway
    if _gateway is None:
        with _gateway_lock:
            if _gateway is None:
                _gateway = GroqRequestGateway()
    return _gateway
