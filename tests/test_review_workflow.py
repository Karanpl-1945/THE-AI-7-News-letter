"""Tests for applying an admin's approve/request-changes decision."""

from dataclasses import replace
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.workflow_repository import IssueLookup
from graph.review import ReviewError, handle_review_decision


ISSUE = IssueLookup(
    issue_id=UUID("12345678-1234-5678-1234-567812345678"),
    status="reviewing",
    thread_id="newsletter-2026-W29",
    workflow_run_id=UUID("87654321-4321-8765-4321-876543218765"),
)


def _checkpointer_context():
    context = MagicMock()
    context.__enter__.return_value = MagicMock()
    return context


class ReviewDecisionTests(unittest.TestCase):
    def test_request_changes_without_feedback_is_rejected(self):
        with self.assertRaisesRegex(ReviewError, "feedback is required"):
            handle_review_decision("2026-W29", "request_changes", feedback=None)

    def test_unknown_decision_is_rejected(self):
        with self.assertRaisesRegex(ReviewError, "decision must be"):
            handle_review_decision("2026-W29", "reject")

    @patch("database.workflow_repository.get_issue_by_key")
    def test_missing_issue_raises(self, mock_get_issue):
        mock_get_issue.return_value = None

        with self.assertRaisesRegex(ReviewError, "No newsletter issue"):
            handle_review_decision("2026-W99", "approve")

    @patch("database.workflow_repository.get_issue_by_key")
    def test_issue_not_awaiting_review_is_rejected(self, mock_get_issue):
        mock_get_issue.return_value = replace(ISSUE, status="sent")

        with self.assertRaisesRegex(ReviewError, "not awaiting review"):
            handle_review_decision("2026-W29", "approve")

    @patch("database.workflow_repository.update_issue_status")
    @patch("database.workflow_repository.get_issue_by_key")
    @patch("database.review_repository.record_approval_decision")
    @patch("delivery.broadcast.send_to_subscribers")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_approve_broadcasts_and_marks_sent(
        self,
        mock_build_pipeline,
        mock_postgres_checkpointer,
        mock_broadcast,
        mock_record_approval,
        mock_get_issue,
        mock_update_status,
    ):
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.return_value = MagicMock(
            values={"html_content": "<html></html>", "issue_date": "July 20, 2026"}
        )
        mock_build_pipeline.return_value = pipeline
        mock_broadcast.return_value = {"sent": 3, "failed": 0, "skipped": 1}

        result = handle_review_decision("2026-W29", "approve")

        mock_record_approval.assert_called_once()
        self.assertEqual(mock_record_approval.call_args.kwargs["decision"], "approved")
        mock_update_status.assert_any_call(ISSUE.issue_id, "approved")
        mock_update_status.assert_called_with(ISSUE.issue_id, "sent")
        self.assertEqual(result["status"], "sent")

    @patch("database.workflow_repository.update_issue_status")
    @patch("database.workflow_repository.get_issue_by_key")
    @patch("database.review_repository.record_approval_decision")
    @patch("delivery.broadcast.send_to_subscribers")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_approve_with_zero_successful_sends_marks_failed(
        self,
        mock_build_pipeline,
        mock_postgres_checkpointer,
        mock_broadcast,
        mock_record_approval,
        mock_get_issue,
        mock_update_status,
    ):
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.return_value = MagicMock(
            values={"html_content": "<html></html>", "issue_date": "July 20, 2026"}
        )
        mock_build_pipeline.return_value = pipeline
        mock_broadcast.return_value = {"sent": 0, "failed": 2, "skipped": 0}

        result = handle_review_decision("2026-W29", "approve")

        self.assertEqual(result["status"], "failed")

    @patch("graph.review.node_notify_admin")
    @patch("graph.review.node_publish")
    @patch("graph.review.node_pdf")
    @patch("graph.review.node_format")
    @patch("graph.review.node_edit")
    @patch("database.workflow_repository.update_issue_status")
    @patch("database.workflow_repository.get_issue_by_key")
    @patch("database.review_repository.record_approval_decision")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_request_changes_regenerates_editor_and_stays_reviewing(
        self,
        mock_build_pipeline,
        mock_postgres_checkpointer,
        mock_record_approval,
        mock_get_issue,
        mock_update_status,
        mock_node_edit,
        mock_node_format,
        mock_node_pdf,
        mock_node_publish,
        mock_node_notify_admin,
    ):
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        base_state = {
            "html_content": "<html></html>",
            "issue_date": "July 20, 2026",
            "revision_number": 1,
        }
        pipeline.get_state.return_value = MagicMock(values=base_state)
        mock_build_pipeline.return_value = pipeline

        mock_node_edit.side_effect = lambda state: {**state, "edited": True}
        mock_node_format.side_effect = lambda state: {**state, "formatted": True}
        mock_node_pdf.side_effect = lambda state: {**state, "pdf": True}
        mock_node_publish.side_effect = lambda state: {**state, "published": True}
        mock_node_notify_admin.side_effect = lambda state, revision_number: {
            **state,
            "admin_notified": True,
        }

        result = handle_review_decision(
            "2026-W29", "request_changes", feedback="Shorten the TL;DR"
        )

        edit_input = mock_node_edit.call_args.args[0]
        self.assertEqual(edit_input["editorial_feedback"], "Shorten the TL;DR")
        self.assertEqual(edit_input["revision_number"], 2)
        mock_node_notify_admin.assert_called_once()
        self.assertEqual(mock_node_notify_admin.call_args.kwargs["revision_number"], 2)
        mock_update_status.assert_called_once_with(ISSUE.issue_id, "reviewing")
        self.assertEqual(result["status"], "reviewing")
        self.assertEqual(result["revision_number"], 2)
        pipeline.update_state.assert_called_once()


if __name__ == "__main__":
    unittest.main()
