"""Tests for Cloudflare R2 artifact metadata persistence."""

import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.artifact_repository import get_artifacts_for_run, save_artifact_metadata


class ArtifactRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.connection_context = MagicMock()
        self.connection_context.__enter__.return_value = self.connection
        self.issue_id = UUID("12345678-1234-5678-1234-567812345678")
        self.run_id = UUID("87654321-4321-8765-4321-876543218765")
        self.artifact_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    @patch("database.artifact_repository.database_connection")
    def test_metadata_is_upserted_by_run_and_type(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = (self.artifact_id,)

        record = save_artifact_metadata(
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            artifact_type="pdf",
            bucket_name="ai-newsletter-artifacts",
            object_key="newsletters/2026/W29/run/newsletter.pdf",
            content_type="application/pdf",
            size_bytes=2048,
            sha256="a" * 64,
            etag="etag-value",
        )

        sql = self.cursor.execute.call_args.args[0]
        self.assertIn("INSERT INTO newsletter_artifacts", sql)
        self.assertIn("ON CONFLICT (workflow_run_id, artifact_type)", sql)
        self.assertEqual(record.id, self.artifact_id)
        self.assertEqual(record.object_key, "newsletters/2026/W29/run/newsletter.pdf")

    @patch("database.artifact_repository.database_connection")
    def test_artifacts_are_loaded_by_workflow_run(self, mock_database_connection):
        mock_database_connection.return_value = self.connection_context
        self.cursor.fetchall.return_value = [
            (
                self.artifact_id,
                self.issue_id,
                self.run_id,
                "html",
                "private-bucket",
                "newsletters/issue/run/newsletter.html",
                "text/html; charset=utf-8",
                512,
                "a" * 64,
                "html-etag",
            ),
        ]

        records = get_artifacts_for_run(self.run_id)

        sql, parameters = self.cursor.execute.call_args.args
        self.assertIn("FROM newsletter_artifacts", sql)
        self.assertEqual(parameters, (self.run_id,))
        self.assertEqual(records["html"].workflow_run_id, self.run_id)
        self.assertEqual(
            records["html"].object_key,
            "newsletters/issue/run/newsletter.html",
        )

    def test_invalid_artifact_type_is_rejected_before_database_access(self):
        with self.assertRaisesRegex(ValueError, "artifact_type"):
            save_artifact_metadata(
                issue_id=self.issue_id,
                workflow_run_id=self.run_id,
                artifact_type="executable",
                bucket_name="bucket",
                object_key="file.exe",
                content_type="application/octet-stream",
                size_bytes=1,
                sha256="a" * 64,
                etag=None,
            )

    def test_invalid_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "sha256"):
            save_artifact_metadata(
                issue_id=self.issue_id,
                workflow_run_id=self.run_id,
                artifact_type="html",
                bucket_name="bucket",
                object_key="newsletter.html",
                content_type="text/html; charset=utf-8",
                size_bytes=10,
                sha256="short",
                etag=None,
            )


if __name__ == "__main__":
    unittest.main()
