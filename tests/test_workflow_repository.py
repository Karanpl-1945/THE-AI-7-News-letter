"""Tests for newsletter issue and workflow-run persistence."""

from datetime import date
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.workflow_repository import (
    WorkflowTracking,
    begin_workflow_run,
    complete_workflow_run,
    fail_workflow_run,
)


class WorkflowRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connection_context = MagicMock()
        self.connection_context.__enter__.return_value = self.connection
        self.issue_id = UUID("12345678-1234-5678-1234-567812345678")
        self.run_id = UUID("87654321-4321-8765-4321-876543218765")

    @patch("database.workflow_repository.database_connection")
    def test_begin_creates_issue_and_run_records(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchone.side_effect = [(self.issue_id,), (self.run_id,)]

        with patch.dict(os.environ, {"WORKFLOW_TRIGGER": "github_manual"}, clear=True):
            tracking = begin_workflow_run(
                issue_key="2026-W29",
                issue_date=date(2026, 7, 15),
                iso_year=2026,
                iso_week=29,
                thread_id="newsletter-2026-W29",
                dry_run=True,
            )

        self.assertEqual(tracking, WorkflowTracking(self.issue_id, self.run_id))
        self.assertEqual(self.cursor.execute.call_count, 2)
        self.assertIn(
            "INSERT INTO newsletter_issues",
            self.cursor.execute.call_args_list[0].args[0],
        )
        self.assertIn(
            "INSERT INTO workflow_runs",
            self.cursor.execute.call_args_list[1].args[0],
        )

    @patch("database.workflow_repository.database_connection")
    def test_completion_updates_run_and_issue(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context
        tracking = WorkflowTracking(self.issue_id, self.run_id)

        complete_workflow_run(tracking, admin_notified=False)

        self.assertEqual(self.cursor.execute.call_count, 2)
        self.assertEqual(
            self.cursor.execute.call_args_list[1].args[1],
            ("generated", self.issue_id),
        )

    @patch("database.workflow_repository.database_connection")
    def test_completion_awaits_review_once_admin_is_notified(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context
        tracking = WorkflowTracking(self.issue_id, self.run_id)

        complete_workflow_run(tracking, admin_notified=True)

        self.assertEqual(
            self.cursor.execute.call_args_list[1].args[1],
            ("reviewing", self.issue_id),
        )

    @patch("database.workflow_repository.database_connection")
    def test_get_issue_by_key_returns_latest_run_thread(self, mock_database_connection):
        from database.workflow_repository import get_issue_by_key

        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = (
            self.issue_id,
            "reviewing",
            "newsletter-2026-W29",
            self.run_id,
        )

        result = get_issue_by_key("2026-W29")

        self.assertEqual(result.issue_id, self.issue_id)
        self.assertEqual(result.status, "reviewing")
        self.assertEqual(result.thread_id, "newsletter-2026-W29")
        self.assertEqual(result.workflow_run_id, self.run_id)

    @patch("database.workflow_repository.database_connection")
    def test_get_issue_by_key_returns_none_when_missing(self, mock_database_connection):
        from database.workflow_repository import get_issue_by_key

        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = None

        self.assertIsNone(get_issue_by_key("2026-W99"))

    @patch("database.workflow_repository.database_connection")
    def test_failure_records_error_and_failed_status(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context
        tracking = WorkflowTracking(self.issue_id, self.run_id)

        fail_workflow_run(tracking, RuntimeError("Groq unavailable"))

        self.assertEqual(self.cursor.execute.call_count, 2)
        self.assertEqual(
            self.cursor.execute.call_args_list[0].args[1],
            ("Groq unavailable", self.run_id),
        )


if __name__ == "__main__":
    unittest.main()
