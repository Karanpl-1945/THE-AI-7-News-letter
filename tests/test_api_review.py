"""Tests for the one-tap admin review HTTP endpoints."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from api.security import make_review_token
from graph.review import ReviewError


ENV = {"API_SIGNING_SECRET": "test-secret-key"}


class ReviewEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.env_patch = patch.dict(os.environ, ENV, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_confirm_page_does_not_mutate_state(self):
        token = make_review_token("2026-W30", "approve")

        with patch("api.routers.review.handle_review_decision") as mock_handle:
            response = self.client.get(f"/review/confirm?token={token}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Confirm Approve", response.text)
        mock_handle.assert_not_called()

    def test_confirm_page_shows_feedback_form_for_request_changes(self):
        token = make_review_token("2026-W30", "request_changes")

        response = self.client.get(f"/review/confirm?token={token}")

        self.assertIn("textarea", response.text)
        self.assertIn("/review/request-changes", response.text)

    def test_invalid_token_shows_error_not_crash(self):
        response = self.client.get("/review/confirm?token=garbage")

        self.assertEqual(response.status_code, 200)
        self.assertIn("invalid", response.text.lower())

    @patch("api.routers.review.handle_review_decision")
    def test_approve_post_calls_handler_with_approve(self, mock_handle):
        mock_handle.return_value = {"sent": 3, "failed": 0, "skipped": 1}
        token = make_review_token("2026-W30", "approve")

        response = self.client.post("/review/approve", data={"token": token})

        mock_handle.assert_called_once_with("2026-W30", "approve")
        self.assertIn("Sent!", response.text)

    @patch("api.routers.review.handle_review_decision")
    def test_second_approve_attempt_shows_friendly_message_not_500(self, mock_handle):
        mock_handle.side_effect = ReviewError("Issue 2026-W30 is not awaiting review")
        token = make_review_token("2026-W30", "approve")

        response = self.client.post("/review/approve", data={"token": token})

        self.assertEqual(response.status_code, 200)
        self.assertIn("not awaiting review", response.text)

    @patch("api.routers.review.handle_review_decision")
    def test_request_changes_requires_feedback_field(self, mock_handle):
        token = make_review_token("2026-W30", "request_changes")

        response = self.client.post("/review/request-changes", data={"token": token})

        self.assertEqual(response.status_code, 422)
        mock_handle.assert_not_called()

    @patch("api.routers.review.handle_review_decision")
    def test_request_changes_passes_feedback_through(self, mock_handle):
        mock_handle.return_value = {"revision_number": 2}
        token = make_review_token("2026-W30", "request_changes")

        response = self.client.post(
            "/review/request-changes",
            data={"token": token, "feedback": "Shorten the TL;DR"},
        )

        mock_handle.assert_called_once_with(
            "2026-W30", "request_changes", feedback="Shorten the TL;DR"
        )
        self.assertIn("revision 2", response.text)


if __name__ == "__main__":
    unittest.main()
