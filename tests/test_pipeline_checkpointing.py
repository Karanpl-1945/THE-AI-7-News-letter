"""Tests for checkpoint-aware pipeline execution."""

from datetime import datetime
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.workflow_repository import WorkflowTracking
from graph.pipeline import (
    build_thread_id,
    invoke_checkpointed_pipeline,
    node_publish,
    route_after_publish,
    run_pipeline,
)


class PublishNodeTests(unittest.TestCase):
    def setUp(self):
        self.issue_id = UUID("12345678-1234-5678-1234-567812345678")
        self.run_id = UUID("87654321-4321-8765-4321-876543218765")
        self.state = {
            "html_path": "output/newsletter.html",
            "pdf_path": "output/newsletter.pdf",
            "issue_id": str(self.issue_id),
            "workflow_run_id": str(self.run_id),
            "dry_run": True,
        }

    @patch("storage.artifact_service.publish_artifact")
    def test_publish_node_uploads_both_files_and_returns_object_keys(self, mock_publish):
        html_result = MagicMock()
        html_result.record.object_key = "newsletters/issue/run/newsletter.html"
        pdf_result = MagicMock()
        pdf_result.record.object_key = "newsletters/issue/run/newsletter.pdf"
        mock_publish.side_effect = [html_result, pdf_result]

        result = node_publish(self.state)

        self.assertEqual(mock_publish.call_count, 2)
        first_call = mock_publish.call_args_list[0]
        self.assertEqual(first_call.args[0], "output/newsletter.html")
        self.assertEqual(first_call.kwargs["issue_id"], self.issue_id)
        self.assertEqual(first_call.kwargs["workflow_run_id"], self.run_id)
        self.assertEqual(
            result["pdf_object_key"],
            "newsletters/issue/run/newsletter.pdf",
        )

    @patch("storage.artifact_service.publish_artifact")
    def test_missing_rendered_path_stops_before_upload(self, mock_publish):
        state = {**self.state, "pdf_path": None}

        with self.assertRaisesRegex(RuntimeError, "paths are required"):
            node_publish(state)

        mock_publish.assert_not_called()

    def test_dry_run_publishes_but_skips_email(self):
        self.assertEqual(route_after_publish(self.state), "finish")

    def test_normal_run_continues_to_email(self):
        self.assertEqual(
            route_after_publish({**self.state, "dry_run": False}),
            "email",
        )


class ThreadIdTests(unittest.TestCase):
    def test_weekly_thread_id_is_stable(self):
        morning = datetime(2026, 7, 15, 8, 0)
        evening = datetime(2026, 7, 15, 20, 0)

        self.assertEqual(build_thread_id(morning), "newsletter-2026-W29")
        self.assertEqual(build_thread_id(evening), "newsletter-2026-W29")

    def test_forced_thread_id_is_separate(self):
        now = datetime(2026, 7, 15, 8, 30, 45, 123456)

        self.assertEqual(
            build_thread_id(now, force=True),
            "newsletter-2026-W29-forced-20260715T083045123456",
        )


class CheckpointExecutionTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = MagicMock()
        self.initial_state = {"issue_date": "July 15, 2026"}
        self.config = {"configurable": {"thread_id": "newsletter-2026-W29"}}

    def test_new_thread_starts_with_initial_state(self):
        self.pipeline.get_state.return_value = MagicMock(values={}, next=())
        expected = {**self.initial_state, "email_sent": False}
        self.pipeline.invoke.return_value = expected

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_called_once_with(
            self.initial_state,
            config=self.config,
        )
        self.assertEqual(result, expected)

    def test_incomplete_thread_resumes_without_new_input(self):
        self.pipeline.get_state.return_value = MagicMock(
            values={"issue_date": "July 15, 2026"},
            next=("summarize",),
        )
        expected = {**self.initial_state, "email_sent": False}
        self.pipeline.invoke.return_value = expected

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_called_once_with(None, config=self.config)
        self.assertEqual(result, expected)

    def test_completed_thread_reuses_saved_state(self):
        saved = {"issue_date": "July 15, 2026", "email_sent": False}
        self.pipeline.get_state.return_value = MagicMock(values=saved, next=())

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_not_called()
        self.assertEqual(result, saved)


class WorkflowLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tracking = WorkflowTracking(
            issue_id=UUID("12345678-1234-5678-1234-567812345678"),
            run_id=UUID("87654321-4321-8765-4321-876543218765"),
        )
        self.checkpointer_context = MagicMock()
        self.checkpointer_context.__enter__.return_value = MagicMock()

    @patch("observability.configure_langfuse")
    @patch("database.workflow_repository.fail_workflow_run")
    @patch("database.workflow_repository.complete_workflow_run")
    @patch("database.workflow_repository.begin_workflow_run")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.pipeline.invoke_checkpointed_pipeline")
    @patch("graph.pipeline.build_pipeline")
    def test_successful_pipeline_completes_workflow_record(
        self,
        mock_build_pipeline,
        mock_invoke,
        mock_postgres_checkpointer,
        mock_begin,
        mock_complete,
        mock_fail,
        _mock_configure_langfuse,
    ):
        mock_begin.return_value = self.tracking
        mock_postgres_checkpointer.return_value = self.checkpointer_context
        mock_build_pipeline.return_value = MagicMock()
        mock_invoke.return_value = {"email_sent": False, "pdf_path": "output/test.pdf"}

        result = run_pipeline(dry_run=True)

        initial_state = mock_invoke.call_args.args[1]
        self.assertEqual(initial_state["issue_id"], str(self.tracking.issue_id))
        self.assertEqual(initial_state["workflow_run_id"], str(self.tracking.run_id))
        mock_complete.assert_called_once_with(self.tracking, email_sent=False)
        mock_fail.assert_not_called()
        self.assertEqual(result["pdf_path"], "output/test.pdf")

    @patch("observability.configure_langfuse")
    @patch("database.workflow_repository.fail_workflow_run")
    @patch("database.workflow_repository.complete_workflow_run")
    @patch("database.workflow_repository.begin_workflow_run")
    @patch("database.checkpointer.postgres_checkpointer")
    @patch("graph.pipeline.invoke_checkpointed_pipeline")
    @patch("graph.pipeline.build_pipeline")
    def test_failed_pipeline_records_workflow_failure(
        self,
        mock_build_pipeline,
        mock_invoke,
        mock_postgres_checkpointer,
        mock_begin,
        mock_complete,
        mock_fail,
        _mock_configure_langfuse,
    ):
        error = RuntimeError("pipeline failed")
        mock_begin.return_value = self.tracking
        mock_postgres_checkpointer.return_value = self.checkpointer_context
        mock_build_pipeline.return_value = MagicMock()
        mock_invoke.side_effect = error

        with self.assertRaisesRegex(RuntimeError, "pipeline failed"):
            run_pipeline(dry_run=True)

        mock_fail.assert_called_once_with(self.tracking, error)
        mock_complete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
