"""Tests for Cloudflare R2 configuration and read-only verification."""

import os
import unittest
from unittest.mock import MagicMock, patch

from storage.r2_client import (
    R2ConfigurationError,
    R2Settings,
    check_r2_connection,
    create_r2_client,
)


VALID_ENVIRONMENT = {
    "R2_ACCOUNT_ID": "account-id",
    "R2_ACCESS_KEY_ID": "access-key",
    "R2_SECRET_ACCESS_KEY": "secret-key",
    "R2_BUCKET_NAME": "ai-newsletter-artifacts",
    "R2_PRESIGNED_URL_EXPIRY_SECONDS": "3600",
}


class R2SettingsTests(unittest.TestCase):
    def test_required_settings_are_loaded(self):
        with patch.dict(os.environ, VALID_ENVIRONMENT, clear=True):
            settings = R2Settings.from_environment()

        self.assertEqual(settings.bucket_name, "ai-newsletter-artifacts")
        self.assertEqual(
            settings.endpoint_url,
            "https://account-id.r2.cloudflarestorage.com",
        )

    def test_missing_secret_is_rejected(self):
        environment = {**VALID_ENVIRONMENT}
        del environment["R2_SECRET_ACCESS_KEY"]

        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(R2ConfigurationError, "R2_SECRET_ACCESS_KEY"):
                R2Settings.from_environment()

    def test_expiry_cannot_exceed_cloudflare_limit(self):
        environment = {
            **VALID_ENVIRONMENT,
            "R2_PRESIGNED_URL_EXPIRY_SECONDS": "604801",
        }

        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(R2ConfigurationError):
                R2Settings.from_environment()


class R2ClientTests(unittest.TestCase):
    @patch("storage.r2_client.boto3.client")
    def test_client_uses_r2_endpoint_and_auto_region(self, mock_boto_client):
        settings = R2Settings(
            account_id="account-id",
            access_key_id="access-key",
            secret_access_key="secret-key",
            bucket_name="bucket",
        )

        create_r2_client(settings)

        call = mock_boto_client.call_args
        self.assertEqual(call.kwargs["service_name"], "s3")
        self.assertEqual(
            call.kwargs["endpoint_url"],
            "https://account-id.r2.cloudflarestorage.com",
        )
        self.assertEqual(call.kwargs["region_name"], "auto")

    @patch("storage.r2_client.create_r2_client")
    def test_connection_check_is_read_only(self, mock_create_client):
        client = MagicMock()
        mock_create_client.return_value = client
        settings = R2Settings(
            account_id="account-id",
            access_key_id="access-key",
            secret_access_key="secret-key",
            bucket_name="private-bucket",
        )

        check_r2_connection(settings)

        client.list_objects_v2.assert_called_once_with(
            Bucket="private-bucket",
            MaxKeys=1,
        )
        client.put_object.assert_not_called()
        client.delete_object.assert_not_called()


if __name__ == "__main__":
    unittest.main()
