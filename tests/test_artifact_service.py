"""Tests for publishing generated newsletter files to private R2 storage."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from botocore.exceptions import ClientError

from database.artifact_repository import ArtifactRecord
from storage.artifact_service import (
    PublishedArtifact,
    build_object_key,
    publish_artifact,
    reconcile_artifacts,
    verify_artifact,
)
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
        self.html_record = ArtifactRecord(
            id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            artifact_type="html",
            bucket_name="private-bucket",
            object_key=f"newsletters/{self.issue_id}/{self.run_id}/newsletter.html",
            content_type="text/html; charset=utf-8",
            size_bytes=128,
            sha256="a" * 64,
            etag="html-etag",
        )
        self.pdf_record = ArtifactRecord(
            id=UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff"),
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            artifact_type="pdf",
            bucket_name="private-bucket",
            object_key=f"newsletters/{self.issue_id}/{self.run_id}/newsletter.pdf",
            content_type="application/pdf",
            size_bytes=256,
            sha256="b" * 64,
            etag="pdf-etag",
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

    def test_matching_head_metadata_verifies_artifact(self):
        client = MagicMock()
        client.head_object.return_value = {
            "ContentLength": 128,
            "ContentType": "text/html; charset=utf-8",
            "Metadata": {"sha256": "a" * 64},
            "ETag": '"html-etag"',
        }

        verified = verify_artifact(
            self.html_record,
            settings=self.settings,
            r2_client=client,
        )

        self.assertTrue(verified)
        client.head_object.assert_called_once_with(
            Bucket="private-bucket",
            Key=self.html_record.object_key,
        )

    def test_deleted_r2_object_is_not_verified(self):
        client = MagicMock()
        client.head_object.side_effect = ClientError(
            {
                "Error": {"Code": "404", "Message": "Not Found"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            },
            "HeadObject",
        )

        self.assertFalse(
            verify_artifact(
                self.html_record,
                settings=self.settings,
                r2_client=client,
            )
        )

    def test_r2_access_denied_is_not_treated_as_a_missing_object(self):
        client = MagicMock()
        client.head_object.side_effect = ClientError(
            {
                "Error": {"Code": "AccessDenied", "Message": "Denied"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            },
            "HeadObject",
        )

        with self.assertRaises(ClientError):
            verify_artifact(
                self.html_record,
                settings=self.settings,
                r2_client=client,
            )

    def test_mismatched_hash_is_not_verified(self):
        client = MagicMock()
        client.head_object.return_value = {
            "ContentLength": 128,
            "ContentType": "text/html; charset=utf-8",
            "Metadata": {"sha256": "different"},
            "ETag": '"html-etag"',
        }

        self.assertFalse(
            verify_artifact(
                self.html_record,
                settings=self.settings,
                r2_client=client,
            )
        )

    @patch("storage.artifact_service.publish_artifact")
    @patch("storage.artifact_service.verify_artifact", return_value=True)
    @patch("storage.artifact_service.get_artifacts_for_run")
    def test_healthy_artifacts_are_reused_without_upload(
        self,
        mock_get_artifacts,
        _mock_verify,
        mock_publish,
    ):
        mock_get_artifacts.return_value = {
            "html": self.html_record,
            "pdf": self.pdf_record,
        }

        records = reconcile_artifacts(
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            html_path="newsletter.html",
            pdf_path="newsletter.pdf",
            settings=self.settings,
            r2_client=MagicMock(),
        )

        mock_publish.assert_not_called()
        self.assertEqual(records["html"], self.html_record)
        self.assertEqual(records["pdf"], self.pdf_record)

    @patch("storage.artifact_service.publish_artifact")
    @patch("storage.artifact_service.verify_artifact", return_value=True)
    @patch("storage.artifact_service.get_artifacts_for_run")
    def test_missing_neon_record_is_repaired_by_upload(
        self,
        mock_get_artifacts,
        _mock_verify,
        mock_publish,
    ):
        mock_get_artifacts.return_value = {"html": self.html_record}
        mock_publish.return_value = PublishedArtifact(
            record=self.pdf_record,
            endpoint_url=self.settings.endpoint_url,
        )

        records = reconcile_artifacts(
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            html_path="newsletter.html",
            pdf_path="newsletter.pdf",
            settings=self.settings,
            r2_client=MagicMock(),
        )

        mock_publish.assert_called_once()
        self.assertEqual(mock_publish.call_args.args[0], Path("newsletter.pdf"))
        self.assertEqual(records["pdf"], self.pdf_record)

    @patch("storage.artifact_service.publish_artifact")
    @patch("storage.artifact_service.verify_artifact")
    @patch("storage.artifact_service.get_artifacts_for_run")
    def test_mismatched_r2_object_is_repaired_by_upload(
        self,
        mock_get_artifacts,
        mock_verify,
        mock_publish,
    ):
        mock_get_artifacts.return_value = {
            "html": self.html_record,
            "pdf": self.pdf_record,
        }
        mock_verify.side_effect = [False, True]
        mock_publish.return_value = PublishedArtifact(
            record=self.html_record,
            endpoint_url=self.settings.endpoint_url,
        )

        records = reconcile_artifacts(
            issue_id=self.issue_id,
            workflow_run_id=self.run_id,
            html_path="newsletter.html",
            pdf_path="newsletter.pdf",
            settings=self.settings,
            r2_client=MagicMock(),
        )

        mock_publish.assert_called_once()
        self.assertEqual(mock_publish.call_args.args[0], Path("newsletter.html"))
        self.assertEqual(records["html"], self.html_record)
        self.assertEqual(records["pdf"], self.pdf_record)


if __name__ == "__main__":
    unittest.main()
