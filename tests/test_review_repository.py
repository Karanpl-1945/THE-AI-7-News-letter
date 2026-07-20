"""Tests for approval-decision and per-subscriber delivery persistence."""

import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.review_repository import (
    get_sent_subscriber_ids,
    record_approval_decision,
    record_delivery,
)


class ReviewRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connection_context = MagicMock()
        self.connection_context.__enter__.return_value = self.connection
        self.issue_id = UUID("12345678-1234-5678-1234-567812345678")
        self.run_id = UUID("87654321-4321-8765-4321-876543218765")
        self.subscriber_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    @patch("database.review_repository.database_connection")
    def test_approval_decision_is_recorded(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context

        record_approval_decision(
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            decision="approved",
            feedback=None,
            revision_number=1,
        )

        sql = self.cursor.execute.call_args.args[0]
        self.assertIn("INSERT INTO approvals", sql)

    def test_invalid_decision_is_rejected_before_database_access(self):
        with self.assertRaisesRegex(ValueError, "decision"):
            record_approval_decision(
                issue_id=self.issue_id,
                workflow_run_id=self.run_id,
                decision="maybe",
                feedback=None,
                revision_number=1,
            )

    def test_invalid_delivery_status_is_rejected_before_database_access(self):
        with self.assertRaisesRegex(ValueError, "status"):
            record_delivery(
                issue_id=self.issue_id,
                subscriber_id=self.subscriber_id,
                status="bounced",
            )

    @patch("database.review_repository.database_connection")
    def test_delivery_upsert_overwrites_a_prior_failed_attempt(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context

        record_delivery(
            issue_id=self.issue_id,
            subscriber_id=self.subscriber_id,
            status="sent",
        )

        sql = self.cursor.execute.call_args.args[0]
        self.assertIn("ON CONFLICT (issue_id, subscriber_id) DO UPDATE", sql)

    @patch("database.review_repository.database_connection")
    def test_sent_subscriber_ids_exclude_a_previously_failed_delivery(
        self, mock_database_connection
    ):
        """The key guarantee: a `failed` row must NOT count as already delivered."""
        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchall.return_value = []

        sent_ids = get_sent_subscriber_ids(self.issue_id)

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("WHERE issue_id = %s AND status = 'sent'", sql)
        self.assertEqual(params, (self.issue_id,))
        self.assertEqual(sent_ids, set())

    @patch("database.review_repository.database_connection")
    def test_sent_subscriber_ids_include_a_successfully_delivered_subscriber(
        self, mock_database_connection
    ):
        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchall.return_value = [(self.subscriber_id,)]

        sent_ids = get_sent_subscriber_ids(self.issue_id)

        self.assertEqual(sent_ids, {self.subscriber_id})


if __name__ == "__main__":
    unittest.main()
