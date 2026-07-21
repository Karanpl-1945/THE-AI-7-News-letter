"""Tests for resuming the paused pipeline graph with an admin's decision."""

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


def _snapshot(next_nodes, values=None):
    snapshot = MagicMock()
    snapshot.next = next_nodes
    snapshot.values = values or {}
    return snapshot


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
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_issue_not_paused_at_approval_is_rejected(
        self, mock_build_pipeline, mock_postgres_checkpointer, mock_get_issue
    ):
        """The graph's own paused position gates the decision, not a status flag."""
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.return_value = _snapshot(next_nodes=())  # already at END
        mock_build_pipeline.return_value = pipeline

        with self.assertRaisesRegex(ReviewError, "not awaiting review"):
            handle_review_decision("2026-W29", "approve")

    @patch("database.workflow_repository.update_issue_status")
    @patch("database.workflow_repository.get_issue_by_key")
    @patch("database.review_repository.record_approval_decision")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_approve_resumes_the_graph_and_marks_sent(
        self,
        mock_build_pipeline,
        mock_postgres_checkpointer,
        mock_record_approval,
        mock_get_issue,
        mock_update_status,
    ):
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.side_effect = [
            _snapshot(next_nodes=("approval",), values={"revision_number": 1}),
            _snapshot(next_nodes=()),  # reached END via "send"
        ]
        pipeline.invoke.return_value = {
            "send_result": {"sent": 3, "failed": 0, "skipped": 1},
        }
        mock_build_pipeline.return_value = pipeline

        result = handle_review_decision("2026-W29", "approve")

        resume_arg = pipeline.invoke.call_args.args[0]
        self.assertEqual(resume_arg.resume, {"decision": "approve", "feedback": None})
        mock_record_approval.assert_called_once()
        self.assertEqual(mock_record_approval.call_args.kwargs["decision"], "approved")
        mock_update_status.assert_called_once_with(ISSUE.issue_id, "sent")
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["sent"], 3)

    @patch("database.workflow_repository.update_issue_status")
    @patch("database.workflow_repository.get_issue_by_key")
    @patch("database.review_repository.record_approval_decision")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_approve_with_zero_successful_sends_marks_failed(
        self,
        mock_build_pipeline,
        mock_postgres_checkpointer,
        mock_record_approval,
        mock_get_issue,
        mock_update_status,
    ):
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.side_effect = [
            _snapshot(next_nodes=("approval",), values={"revision_number": 1}),
            _snapshot(next_nodes=()),
        ]
        pipeline.invoke.return_value = {
            "send_result": {"sent": 0, "failed": 2, "skipped": 0},
        }
        mock_build_pipeline.return_value = pipeline

        result = handle_review_decision("2026-W29", "approve")

        self.assertEqual(result["status"], "failed")

    @patch("database.workflow_repository.update_issue_status")
    @patch("database.workflow_repository.get_issue_by_key")
    @patch("database.review_repository.record_approval_decision")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_approve_with_no_subscribers_stays_approved_not_sent(
        self,
        mock_build_pipeline,
        mock_postgres_checkpointer,
        mock_record_approval,
        mock_get_issue,
        mock_update_status,
    ):
        """Nobody to deliver to is not the same as a successful send."""
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.side_effect = [
            _snapshot(next_nodes=("approval",), values={"revision_number": 1}),
            _snapshot(next_nodes=()),
        ]
        pipeline.invoke.return_value = {
            "send_result": {"sent": 0, "failed": 0, "skipped": 0},
        }
        mock_build_pipeline.return_value = pipeline

        result = handle_review_decision("2026-W29", "approve")

        self.assertEqual(result["status"], "approved")

    @patch("database.workflow_repository.update_issue_status")
    @patch("database.workflow_repository.get_issue_by_key")
    @patch("delivery.broadcast.send_to_subscribers")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_reapproving_a_finished_issue_retries_the_send_directly(
        self,
        mock_build_pipeline,
        mock_postgres_checkpointer,
        mock_send,
        mock_get_issue,
        mock_update_status,
    ):
        """No pending interrupt to resume — retry delivery without touching the graph."""
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.return_value = _snapshot(
            next_nodes=(),
            values={"review_decision": "approve", "html_content": "<html></html>"},
        )
        mock_build_pipeline.return_value = pipeline
        mock_send.return_value = {"sent": 1, "failed": 0, "skipped": 2}

        result = handle_review_decision("2026-W29", "approve")

        mock_send.assert_called_once()
        pipeline.invoke.assert_not_called()  # no graph resume for a retry
        mock_update_status.assert_called_once_with(ISSUE.issue_id, "sent")
        self.assertTrue(result["retried"])
        self.assertEqual(result["sent"], 1)

    @patch("database.workflow_repository.get_issue_by_key")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_request_changes_is_rejected_once_the_issue_is_finished(
        self, mock_build_pipeline, mock_postgres_checkpointer, mock_get_issue
    ):
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.return_value = _snapshot(
            next_nodes=(), values={"review_decision": "approve"}
        )
        mock_build_pipeline.return_value = pipeline

        with self.assertRaisesRegex(ReviewError, "not awaiting review"):
            handle_review_decision("2026-W29", "request_changes", feedback="too late")

    @patch("database.workflow_repository.update_issue_status")
    @patch("database.workflow_repository.get_issue_by_key")
    @patch("database.review_repository.record_approval_decision")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.review.build_pipeline")
    def test_request_changes_resumes_and_stays_reviewing(
        self,
        mock_build_pipeline,
        mock_postgres_checkpointer,
        mock_record_approval,
        mock_get_issue,
        mock_update_status,
    ):
        mock_get_issue.return_value = ISSUE
        mock_postgres_checkpointer.return_value = _checkpointer_context()
        pipeline = MagicMock()
        pipeline.get_state.side_effect = [
            _snapshot(next_nodes=("approval",), values={"revision_number": 1}),
            _snapshot(next_nodes=("approval",)),  # looped back and paused again
        ]
        pipeline.invoke.return_value = {
            "revision_number": 2,
            "admin_notified": True,
        }
        mock_build_pipeline.return_value = pipeline

        result = handle_review_decision(
            "2026-W29", "request_changes", feedback="Shorten the TL;DR"
        )

        resume_arg = pipeline.invoke.call_args.args[0]
        self.assertEqual(
            resume_arg.resume,
            {"decision": "request_changes", "feedback": "Shorten the TL;DR"},
        )
        mock_record_approval.assert_called_once()
        self.assertEqual(
            mock_record_approval.call_args.kwargs["decision"], "changes_requested"
        )
        self.assertEqual(mock_record_approval.call_args.kwargs["revision_number"], 2)
        mock_update_status.assert_called_once_with(ISSUE.issue_id, "reviewing")
        self.assertEqual(result["status"], "reviewing")
        self.assertEqual(result["revision_number"], 2)


if __name__ == "__main__":
    unittest.main()
