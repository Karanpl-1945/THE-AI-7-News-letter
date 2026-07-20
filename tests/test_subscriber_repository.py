"""Tests for the admin-managed subscriber list."""

import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.subscriber_repository import (
    add_subscriber,
    list_active_subscribers,
    remove_subscriber,
)


class SubscriberRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connection_context = MagicMock()
        self.connection_context.__enter__.return_value = self.connection
        self.subscriber_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    @patch("database.subscriber_repository.database_connection")
    def test_add_subscriber_upserts_and_normalizes_email(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = (self.subscriber_id, "reader@example.com", "active")

        record = add_subscriber("Reader@Example.com  ")

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("ON CONFLICT (email) DO UPDATE", sql)
        self.assertEqual(params[1], "reader@example.com")
        self.assertEqual(record.status, "active")

    @patch("database.subscriber_repository.database_connection")
    def test_remove_subscriber_marks_unsubscribed(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context

        remove_subscriber("reader@example.com")

        sql, params = self.cursor.execute.call_args.args
        self.assertIn("SET status = 'unsubscribed'", sql)
        self.assertEqual(params, ("reader@example.com",))

    @patch("database.subscriber_repository.database_connection")
    def test_list_active_subscribers_filters_by_status(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchall.return_value = [(self.subscriber_id, "reader@example.com", "active")]

        subscribers = list_active_subscribers()

        sql = self.cursor.execute.call_args.args[0]
        self.assertIn("WHERE status = 'active'", sql)
        self.assertEqual(len(subscribers), 1)
        self.assertEqual(subscribers[0].email, "reader@example.com")


if __name__ == "__main__":
    unittest.main()
