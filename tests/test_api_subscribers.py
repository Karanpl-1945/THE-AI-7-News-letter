"""Tests for the public subscribe / token-restricted unsubscribe endpoints."""

import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app
from api.security import make_unsubscribe_token
from database.subscriber_repository import SubscriberRecord


ENV = {"API_SIGNING_SECRET": "test-secret-key"}


class SubscribeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.env_patch = patch.dict(os.environ, ENV, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    @patch("api.routers.subscribers.add_subscriber")
    def test_subscribe_with_valid_email(self, mock_add):
        mock_add.return_value = SubscriberRecord(
            id=uuid4(), email="reader@example.com", status="active"
        )

        response = self.client.post("/subscribe", json={"email": "reader@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "active")
        mock_add.assert_called_once_with("reader@example.com")

    @patch("api.routers.subscribers.add_subscriber")
    def test_subscribe_with_invalid_email_is_rejected(self, mock_add):
        response = self.client.post("/subscribe", json={"email": "not-an-email"})

        self.assertEqual(response.status_code, 422)
        mock_add.assert_not_called()

    def test_unsubscribe_confirm_page_does_not_mutate_state(self):
        token = make_unsubscribe_token("reader@example.com")

        with patch("api.routers.subscribers.remove_subscriber") as mock_remove:
            response = self.client.get(f"/unsubscribe/confirm?token={token}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Confirm Unsubscribe", response.text)
        mock_remove.assert_not_called()

    @patch("api.routers.subscribers.remove_subscriber")
    def test_unsubscribe_post_calls_remove_subscriber(self, mock_remove):
        token = make_unsubscribe_token("reader@example.com")

        response = self.client.post("/unsubscribe", data={"token": token})

        mock_remove.assert_called_once_with("reader@example.com")
        self.assertIn("has been unsubscribed", response.text)

    def test_invalid_unsubscribe_token_is_rejected(self):
        with patch("api.routers.subscribers.remove_subscriber") as mock_remove:
            response = self.client.post("/unsubscribe", data={"token": "garbage"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("invalid", response.text.lower())
        mock_remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
