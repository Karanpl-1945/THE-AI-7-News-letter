"""Tests for publishing generated newsletter files to private R2 storage."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from database.artifact_repository import ArtifactRecord
from storage.artifact_service import build_object_key, publish_artifact
from storage.r2_client import R2Settings


class ArtifactServiceTests(unittest.TestCase):
    def setUp(self):
        self.issue_id = UUID("12345678-1234-5678-1234-567812345678")
        self.run_id = UUID("87654321-4321-8765-4321-876543218765")
        self.settings = R2Settings(
            account_id="account-id",
            access_key_id="access-key",
            secret_access_key="secret-key",
            bucket_name="private-bucket",
        )

    def test_object_key_is_stable_for_run_and_artifact_type(self):
        first = build_object_key(
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            artifact_type="pdf",
        )
        second = build_object_key(
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            artifact_type="pdf",
        )

        self.assertEqual(first, second)
        self.assertEqual(
            first,
            f"newsletters/{self.issue_id}/{self.run_id}/newsletter.pdf",
        )

    @patch("storage.artifact_service.save_artifact_metadata")
    def test_pdf_is_uploaded_before_metadata_is_saved(self, mock_save_metadata):
        client = MagicMock()
        client.put_object.return_value = {"ETag": '"r2-etag"'}
        content = b"fake-pdf-content"
        expected_hash = hashlib.sha256(content).hexdigest()
        record = ArtifactRecord(
            id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            artifact_type="pdf",
            bucket_name=self.settings.bucket_name,
            object_key=f"newsletters/{self.issue_id}/{self.run_id}/newsletter.pdf",
            content_type="application/pdf",
            size_bytes=len(content),
            sha256=expected_hash,
            etag="r2-etag",
        )
        mock_save_metadata.return_value = record

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generated.pdf"
            path.write_bytes(content)
            published = publish_artifact(
                path,
                issue_id=self.issue_id,
                workflow_run_id=self.run_id,
                settings=self.settings,
                r2_client=client,
            )

        upload = client.put_object.call_args.kwargs
        self.assertEqual(upload["Bucket"], "private-bucket")
        self.assertEqual(upload["Key"], record.object_key)
        self.assertEqual(upload["ContentType"], "application/pdf")
        self.assertEqual(upload["Metadata"]["sha256"], expected_hash)
        self.assertEqual(mock_save_metadata.call_args.kwargs["etag"], "r2-etag")
        self.assertEqual(published.record, record)

    @patch("storage.artifact_service.save_artifact_metadata")
    def test_failed_upload_does_not_save_database_metadata(self, mock_save_metadata):
        client = MagicMock()
        client.put_object.side_effect = RuntimeError("R2 unavailable")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generated.html"
            path.write_text("<html></html>", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "R2 unavailable"):
                publish_artifact(
                    path,
                    issue_id=self.issue_id,
                    workflow_run_id=self.run_id,
                    settings=self.settings,
                    r2_client=client,
                )

        mock_save_metadata.assert_not_called()

    def test_missing_file_is_rejected_before_r2_configuration(self):
        with self.assertRaises(FileNotFoundError):
            publish_artifact(
                "missing.pdf",
                issue_id=self.issue_id,
                workflow_run_id=self.run_id,
            )

    def test_unsupported_file_type_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "newsletter.exe"
            path.write_bytes(b"not-supported")
            with self.assertRaisesRegex(ValueError, "extensions"):
                publish_artifact(
                    path,
                    issue_id=self.issue_id,
                    workflow_run_id=self.run_id,
                )


if __name__ == "__main__":
    unittest.main()
