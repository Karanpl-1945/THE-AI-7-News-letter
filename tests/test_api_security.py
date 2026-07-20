"""Tests for signed one-click email link tokens."""

import os
import time
import unittest
from unittest.mock import patch

from api.security import (
    TokenError,
    make_review_token,
    make_unsubscribe_token,
    verify_review_token,
    verify_unsubscribe_token,
)


ENV = {"API_SIGNING_SECRET": "test-secret-key"}


class ReviewTokenTests(unittest.TestCase):
    def test_valid_token_round_trips(self):
        with patch.dict(os.environ, ENV, clear=False):
            token = make_review_token("2026-W30", "approve")
            payload = verify_review_token(token)

        self.assertEqual(payload["issue_key"], "2026-W30")
        self.assertEqual(payload["decision"], "approve")

    def test_tampered_token_is_rejected(self):
        with patch.dict(os.environ, ENV, clear=False):
            token = make_review_token("2026-W30", "approve")
            # Flip a character in the middle rather than the last one — a
            # base64 string's final character can have insignificant padding
            # bits, so some last-character edits decode to the same byte and
            # don't actually corrupt the signature.
            middle = len(token) // 2
            tampered = (
                token[:middle] + ("a" if token[middle] != "a" else "b") + token[middle + 1:]
            )

            with self.assertRaises(TokenError):
                verify_review_token(tampered)

    def test_expired_token_is_rejected(self):
        with patch.dict(os.environ, ENV, clear=False):
            token = make_review_token("2026-W30", "approve")
            time.sleep(1.1)

            with self.assertRaisesRegex(TokenError, "expired"):
                verify_review_token(token, max_age=0)

    def test_missing_signing_secret_raises_token_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(TokenError):
                make_review_token("2026-W30", "approve")


class UnsubscribeTokenTests(unittest.TestCase):
    def test_valid_token_round_trips(self):
        with patch.dict(os.environ, ENV, clear=False):
            token = make_unsubscribe_token("reader@example.com")
            email = verify_unsubscribe_token(token)

        self.assertEqual(email, "reader@example.com")

    def test_tampered_token_is_rejected(self):
        with patch.dict(os.environ, ENV, clear=False):
            token = make_unsubscribe_token("reader@example.com")
            # See the equivalent review-token test for why the middle
            # character is flipped instead of the last one.
            middle = len(token) // 2
            tampered = (
                token[:middle] + ("a" if token[middle] != "a" else "b") + token[middle + 1:]
            )

            with self.assertRaises(TokenError):
                verify_unsubscribe_token(tampered)

    def test_unsubscribe_token_cannot_be_used_as_a_review_token(self):
        with patch.dict(os.environ, ENV, clear=False):
            token = make_unsubscribe_token("reader@example.com")

            with self.assertRaises(TokenError):
                verify_review_token(token)


if __name__ == "__main__":
    unittest.main()
