"""Tests for checkpoint-aware pipeline execution."""

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.workflow_repository import WorkflowTracking
from graph.pipeline import (
    build_thread_id,
    invoke_checkpointed_pipeline,
    node_notify_admin,
    node_publish,
    route_after_publish,
    run_pipeline,
)


class PublishNodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        directory = Path(self.temporary_directory.name)
        self.html_path = directory / "newsletter.html"
        self.pdf_path = directory / "newsletter.pdf"
        self.html_path.write_text("<html>checkpoint content</html>", encoding="utf-8")
        self.pdf_path.write_bytes(b"checkpoint pdf")
        self.issue_id = UUID("12345678-1234-5678-1234-567812345678")
        self.run_id = UUID("87654321-4321-8765-4321-876543218765")
        self.state = {
            "html_content": "<html>checkpoint content</html>",
            "html_path": str(self.html_path),
            "pdf_path": str(self.pdf_path),
            "issue_date": "July 16, 2026",
            "issue_id": str(self.issue_id),
            "workflow_run_id": str(self.run_id),
            "issue_key": "2026-W29",
            "dry_run": True,
        }

    @patch("storage.artifact_service.reconcile_artifacts")
    def test_publish_node_reconciles_both_files_and_returns_object_keys(
        self,
        mock_reconcile,
    ):
        html_result = MagicMock()
        html_result.record.object_key = "newsletters/issue/run/newsletter.html"
        pdf_result = MagicMock()
        pdf_result.record.object_key = "newsletters/issue/run/newsletter.pdf"
        mock_reconcile.return_value = {
            "html": html_result.record,
            "pdf": pdf_result.record,
        }

        result = node_publish(self.state)

        mock_reconcile.assert_called_once_with(
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            html_path=str(self.html_path),
            pdf_path=str(self.pdf_path),
        )
        self.assertEqual(
            result["pdf_object_key"],
            "newsletters/issue/run/newsletter.pdf",
        )

    @patch("storage.artifact_service.reconcile_artifacts")
    @patch("formatter.pdf_generator.html_to_pdf")
    @patch("graph.pipeline._html_output_path")
    def test_missing_runner_files_are_restored_before_upload(
        self,
        mock_html_output_path,
        mock_html_to_pdf,
        mock_reconcile,
    ):
        restored_html = Path(self.temporary_directory.name) / "restored.html"
        restored_pdf = Path(self.temporary_directory.name) / "restored.pdf"
        mock_html_output_path.return_value = restored_html

        def generate_pdf(_html_content, _issue_date):
            restored_pdf.write_bytes(b"regenerated pdf")
            return str(restored_pdf)

        mock_html_to_pdf.side_effect = generate_pdf
        html_result = MagicMock()
        html_result.record.object_key = "newsletters/issue/run/newsletter.html"
        pdf_result = MagicMock()
        pdf_result.record.object_key = "newsletters/issue/run/newsletter.pdf"
        mock_reconcile.return_value = {
            "html": html_result.record,
            "pdf": pdf_result.record,
        }
        state = {
            **self.state,
            "html_path": "/old-runner/output/newsletter.html",
            "pdf_path": "/old-runner/output/newsletter.pdf",
        }

        result = node_publish(state)

        self.assertEqual(
            restored_html.read_text(encoding="utf-8"),
            self.state["html_content"],
        )
        mock_html_to_pdf.assert_called_once_with(
            self.state["html_content"],
            self.state["issue_date"],
        )
        self.assertEqual(
            mock_reconcile.call_args.kwargs["html_path"],
            str(restored_html),
        )
        self.assertEqual(
            mock_reconcile.call_args.kwargs["pdf_path"],
            str(restored_pdf),
        )
        self.assertEqual(result["html_path"], str(restored_html))
        self.assertEqual(result["pdf_path"], str(restored_pdf))

    @patch("storage.artifact_service.reconcile_artifacts")
    def test_missing_files_without_checkpointed_html_stops_upload(
        self,
        mock_reconcile,
    ):
        state = {
            **self.state,
            "html_content": "",
            "html_path": "/old-runner/missing.html",
            "pdf_path": "/old-runner/missing.pdf",
        }

        with self.assertRaisesRegex(RuntimeError, "no HTML content"):
            node_publish(state)

        mock_reconcile.assert_not_called()

    @patch("delivery.email_sender.send_admin_review_email")
    @patch("formatter.pdf_generator.html_to_pdf")
    @patch("graph.pipeline._html_output_path")
    def test_notify_admin_resume_restores_files_on_a_new_runner(
        self,
        mock_html_output_path,
        mock_html_to_pdf,
        mock_send_admin_review_email,
    ):
        restored_html = Path(self.temporary_directory.name) / "email-restored.html"
        restored_pdf = Path(self.temporary_directory.name) / "email-restored.pdf"
        mock_html_output_path.return_value = restored_html

        def generate_pdf(_html_content, _issue_date):
            restored_pdf.write_bytes(b"regenerated email pdf")
            return str(restored_pdf)

        mock_html_to_pdf.side_effect = generate_pdf
        mock_send_admin_review_email.return_value = True
        state = {
            **self.state,
            "html_path": "/old-runner/missing.html",
            "pdf_path": "/old-runner/missing.pdf",
            "dry_run": False,
        }

        result = node_notify_admin(state)

        mock_send_admin_review_email.assert_called_once_with(
            self.state["html_content"],
            str(restored_pdf),
            self.state["issue_date"],
            issue_key=self.state["issue_key"],
            revision_number=1,
        )
        self.assertTrue(result["admin_notified"])
        self.assertEqual(result["html_path"], str(restored_html))

    def test_dry_run_publishes_but_skips_admin_notification(self):
        self.assertEqual(route_after_publish(self.state), "finish")

    def test_normal_run_continues_to_notify_admin(self):
        self.assertEqual(
            route_after_publish({**self.state, "dry_run": False}),
            "notify_admin",
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
        expected = {**self.initial_state, "admin_notified": False}
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
        expected = {**self.initial_state, "admin_notified": False}
        self.pipeline.invoke.return_value = expected

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_called_once_with(None, config=self.config)
        self.assertEqual(result, expected)

    def test_completed_thread_reuses_saved_state(self):
        saved = {"issue_date": "July 15, 2026", "admin_notified": False}
        self.pipeline.get_state.return_value = MagicMock(values=saved, next=())

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_not_called()
        self.assertEqual(result, saved)

    @patch("storage.artifact_service.reconcile_artifacts")
    @patch("graph.pipeline._ensure_local_artifacts")
    def test_completed_thread_restores_output_for_current_runner(
        self,
        mock_ensure_local_artifacts,
        mock_reconcile,
    ):
        issue_id = UUID("12345678-1234-5678-1234-567812345678")
        run_id = UUID("87654321-4321-8765-4321-876543218765")
        saved = {
            "issue_date": "July 15, 2026",
            "html_content": "<html>saved output</html>",
            "html_path": "/old-runner/output/newsletter.html",
            "pdf_path": "/old-runner/output/newsletter.pdf",
            "issue_id": str(issue_id),
            "workflow_run_id": str(run_id),
            "admin_notified": False,
        }
        self.pipeline.get_state.return_value = MagicMock(values=saved, next=())
        mock_ensure_local_artifacts.return_value = (
            "/current-runner/output/newsletter.html",
            "/current-runner/output/newsletter.pdf",
        )
        html_record = MagicMock()
        html_record.object_key = "newsletters/issue/run/newsletter.html"
        pdf_record = MagicMock()
        pdf_record.object_key = "newsletters/issue/run/newsletter.pdf"
        mock_reconcile.return_value = {
            "html": html_record,
            "pdf": pdf_record,
        }

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_not_called()
        mock_ensure_local_artifacts.assert_called_once()
        mock_reconcile.assert_called_once_with(
            issue_id=issue_id,
            workflow_run_id=run_id,
            html_path="/current-runner/output/newsletter.html",
            pdf_path="/current-runner/output/newsletter.pdf",
        )
        self.assertEqual(
            result["html_path"],
            "/current-runner/output/newsletter.html",
        )
        self.assertEqual(
            result["pdf_path"],
            "/current-runner/output/newsletter.pdf",
        )
        self.assertEqual(
            result["pdf_object_key"],
            "newsletters/issue/run/newsletter.pdf",
        )


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
        mock_invoke.return_value = {"admin_notified": False, "pdf_path": "output/test.pdf"}

        result = run_pipeline(dry_run=True)

        initial_state = mock_invoke.call_args.args[1]
        self.assertEqual(initial_state["issue_id"], str(self.tracking.issue_id))
        self.assertEqual(initial_state["workflow_run_id"], str(self.tracking.run_id))
        mock_complete.assert_called_once_with(self.tracking, admin_notified=False)
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
