"""Tests for delivering an approved issue to the subscriber list."""

import unittest
from unittest.mock import patch
from uuid import UUID

from database.subscriber_repository import SubscriberRecord
from delivery.broadcast import send_to_subscribers


ACTIVE = [
    SubscriberRecord(id=UUID(int=1), email="already-sent@example.com", status="active"),
    SubscriberRecord(id=UUID(int=2), email="previously-failed@example.com", status="active"),
    SubscriberRecord(id=UUID(int=3), email="new@example.com", status="active"),
]


class BroadcastTests(unittest.TestCase):
    def setUp(self):
        self.issue_id = UUID("12345678-1234-5678-1234-567812345678")
        self.state = {
            "html_content": "<html>issue</html>",
            "pdf_path": "output/issue.pdf",
            "issue_date": "July 20, 2026",
        }

    @patch("delivery.broadcast.record_delivery")
    @patch("delivery.broadcast.send_to_subscriber")
    @patch("delivery.broadcast.get_sent_subscriber_ids")
    @patch("delivery.broadcast.list_active_subscribers")
    def test_already_sent_subscribers_are_skipped_but_failed_ones_are_retried(
        self,
        mock_list_active,
        mock_get_sent,
        mock_send,
        mock_record,
    ):
        mock_list_active.return_value = ACTIVE
        # Subscriber 1 already succeeded; subscriber 2's prior attempt failed and
        # must NOT be treated as already delivered.
        mock_get_sent.return_value = {ACTIVE[0].id}
        mock_send.return_value = True

        result = send_to_subscribers(self.state, self.issue_id)

        sent_to = {call.args[3] for call in mock_send.call_args_list}
        self.assertEqual(sent_to, {"previously-failed@example.com", "new@example.com"})
        self.assertEqual(result, {"sent": 2, "failed": 0, "skipped": 1})

    @patch("delivery.broadcast.record_delivery")
    @patch("delivery.broadcast.send_to_subscriber")
    @patch("delivery.broadcast.get_sent_subscriber_ids")
    @patch("delivery.broadcast.list_active_subscribers")
    def test_delivery_outcome_is_recorded_per_recipient(
        self,
        mock_list_active,
        mock_get_sent,
        mock_send,
        mock_record,
    ):
        mock_list_active.return_value = [ACTIVE[2]]
        mock_get_sent.return_value = set()
        mock_send.return_value = False

        send_to_subscribers(self.state, self.issue_id)

        mock_record.assert_called_once_with(
            issue_id=self.issue_id,
            subscriber_id=ACTIVE[2].id,
            status="failed",
            error_message="Transport reported failure.",
        )


if __name__ == "__main__":
    unittest.main()
