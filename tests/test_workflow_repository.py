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

        complete_workflow_run(tracking, email_sent=False)

        self.assertEqual(self.cursor.execute.call_count, 2)
        self.assertEqual(
            self.cursor.execute.call_args_list[1].args[1],
            ("generated", self.issue_id),
        )

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
