"""Tests for the welcome email sent to brand-new subscribers."""

import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.artifact_repository import ArtifactRecord
from database.workflow_repository import SentIssueLookup
from delivery.email_sender import send_welcome_email


ISSUE_ID = UUID("12345678-1234-5678-1234-567812345678")
RUN_ID = UUID("87654321-4321-8765-4321-876543218765")


class WelcomeEmailTests(unittest.TestCase):
    @patch("delivery.email_sender.get_email_transport")
    @patch("database.workflow_repository.get_latest_sent_issue")
    def test_no_prior_issue_sends_a_plain_welcome(self, mock_latest, mock_get_transport):
        mock_latest.return_value = None
        transport = MagicMock()
        transport.send.return_value = True
        mock_get_transport.return_value = transport

        result = send_welcome_email("reader@example.com")

        self.assertTrue(result)
        call = transport.send.call_args.kwargs
        self.assertEqual(call["to"], "reader@example.com")
        self.assertIn("Welcome", call["subject"])
        self.assertIn("every Sunday", call["html"])

    @patch("storage.r2_client.generate_presigned_url")
    @patch("database.artifact_repository.get_artifacts_for_run")
    @patch("delivery.email_sender.get_email_transport")
    @patch("database.workflow_repository.get_latest_sent_issue")
    def test_prior_issue_links_a_presigned_url_not_full_content(
        self, mock_latest, mock_get_transport, mock_get_artifacts, mock_presign
    ):
        from datetime import date

        mock_latest.return_value = SentIssueLookup(
            issue_id=ISSUE_ID, workflow_run_id=RUN_ID, issue_date=date(2026, 7, 20)
        )
        mock_get_artifacts.return_value = {
            "html": ArtifactRecord(
                id=UUID(int=1),
                issue_id=ISSUE_ID,
                workflow_run_id=RUN_ID,
                artifact_type="html",
                bucket_name="ai-newsletter-artifacts",
                object_key="newsletters/issue/run/newsletter.html",
                content_type="text/html; charset=utf-8",
                size_bytes=100,
                sha256="a" * 64,
                etag=None,
            )
        }
        mock_presign.return_value = "https://signed.example/newsletter.html"
        transport = MagicMock()
        transport.send.return_value = True
        mock_get_transport.return_value = transport

        result = send_welcome_email("reader@example.com")

        self.assertTrue(result)
        call = transport.send.call_args.kwargs
        self.assertIn("https://signed.example/newsletter.html", call["html"])
        self.assertIn("July 20, 2026", call["html"])
        # Only a link is included — the full HTML body is never re-embedded.
        mock_get_artifacts.assert_called_once_with(RUN_ID)

    @patch("delivery.email_sender.get_email_transport")
    @patch("database.workflow_repository.get_latest_sent_issue")
    def test_no_html_artifact_still_sends_a_welcome_without_a_broken_link(
        self, mock_latest, mock_get_transport
    ):
        from datetime import date

        mock_latest.return_value = SentIssueLookup(
            issue_id=ISSUE_ID, workflow_run_id=RUN_ID, issue_date=date(2026, 7, 20)
        )
        transport = MagicMock()
        transport.send.return_value = True
        mock_get_transport.return_value = transport

        with patch(
            "database.artifact_repository.get_artifacts_for_run", return_value={}
        ):
            result = send_welcome_email("reader@example.com")

        self.assertTrue(result)
        call = transport.send.call_args.kwargs
        self.assertNotIn("Read the", call["html"])


if __name__ == "__main__":
    unittest.main()
