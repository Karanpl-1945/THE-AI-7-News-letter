import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from groq import APITimeoutError, RateLimitError

from llm.groq_client import (
    GroqQuotaExhaustedError,
    GroqRateLimitError,
    GroqRequestError,
    GroqRequestGateway,
    GroqRequestSettings,
    _parse_duration_seconds,
)


def _response(payload):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload))
            )
        ]
    )


def _rate_limit_error(message, retry_after=None):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
    response = httpx.Response(429, headers=headers, request=request)
    return RateLimitError(
        message,
        response=response,
        body={"error": {"message": message, "type": "tokens"}},
    )


def _settings(max_retries=2, max_wait=60):
    return GroqRequestSettings(
        max_retries=max_retries,
        max_retry_wait_seconds=max_wait,
        request_timeout_seconds=45,
        min_request_interval_seconds=0,
    )


def _gateway(side_effect, settings=None):
    client = Mock()
    client.chat.completions.create.side_effect = side_effect
    sleep = Mock()
    gateway = GroqRequestGateway(
        client=client,
        settings=settings or _settings(),
        sleep=sleep,
        jitter=lambda: 0,
    )
    return gateway, client, sleep


class GroqRequestGatewayTests(unittest.TestCase):
    def test_successful_json_request_is_not_retried(self):
        gateway, client, sleep = _gateway([_response({"status": "ok"})])

        result = gateway.create_json_completion(
            prompt="prompt", model="test-model", max_tokens=100
        )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(client.chat.completions.create.call_count, 1)
        sleep.assert_not_called()

    def test_single_object_array_is_safely_unwrapped(self):
        gateway, client, sleep = _gateway([_response([{"status": "ok"}])])

        result = gateway.create_json_completion(
            prompt="prompt", model="test-model", max_tokens=100
        )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(client.chat.completions.create.call_count, 1)
        sleep.assert_not_called()

    def test_multi_object_array_is_rejected_without_another_request(self):
        gateway, client, sleep = _gateway(
            [_response([{"first": 1}, {"second": 2}])]
        )

        with self.assertRaisesRegex(GroqRequestError, "must be an object"):
            gateway.create_json_completion(
                prompt="prompt", model="test-model", max_tokens=100
            )

        self.assertEqual(client.chat.completions.create.call_count, 1)
        sleep.assert_not_called()

    def test_short_rate_limit_waits_then_retries(self):
        error = _rate_limit_error("tokens per minute limit", retry_after="2.5")
        gateway, client, sleep = _gateway([error, _response({"status": "ok"})])

        result = gateway.create_json_completion(
            prompt="prompt", model="test-model", max_tokens=100
        )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(client.chat.completions.create.call_count, 2)
        sleep.assert_called_once_with(2.5)

    def test_daily_token_limit_fails_immediately_without_sleeping(self):
        error = _rate_limit_error(
            "Rate limit reached on tokens per day (TPD). Please try again in 15m43.488s.",
            retry_after="15m43.488s",
        )
        gateway, client, sleep = _gateway([error])

        with self.assertRaises(GroqQuotaExhaustedError) as raised:
            gateway.create_json_completion(
                prompt="prompt", model="test-model", max_tokens=100
            )

        self.assertAlmostEqual(raised.exception.retry_after_seconds, 943.488)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        sleep.assert_not_called()

    def test_repeated_short_rate_limit_stops_after_retry_limit(self):
        error = _rate_limit_error("requests per minute limit", retry_after="1")
        gateway, client, sleep = _gateway(
            [error, error], settings=_settings(max_retries=1)
        )

        with self.assertRaises(GroqRateLimitError):
            gateway.create_json_completion(
                prompt="prompt", model="test-model", max_tokens=100
            )

        self.assertEqual(client.chat.completions.create.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_non_retryable_error_is_not_retried(self):
        gateway, client, sleep = _gateway([RuntimeError("invalid credentials")])

        with self.assertRaises(RuntimeError):
            gateway.create_json_completion(
                prompt="prompt", model="test-model", max_tokens=100
            )

        self.assertEqual(client.chat.completions.create.call_count, 1)
        sleep.assert_not_called()

    def test_transient_timeout_retries_then_succeeds(self):
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        gateway, client, sleep = _gateway(
            [APITimeoutError(request), _response({"status": "ok"})]
        )

        result = gateway.create_json_completion(
            prompt="prompt", model="test-model", max_tokens=100
        )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(client.chat.completions.create.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_compact_duration_parser(self):
        self.assertAlmostEqual(_parse_duration_seconds("15m43.488s"), 943.488)
        self.assertAlmostEqual(_parse_duration_seconds("500ms"), 0.5)


if __name__ == "__main__":
    unittest.main()
