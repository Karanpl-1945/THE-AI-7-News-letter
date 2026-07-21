"""Configure and verify Cloudflare R2 through its S3-compatible API."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import boto3
from botocore.config import Config
from dotenv import load_dotenv


MAX_PRESIGNED_URL_EXPIRY_SECONDS = 604_800


class R2ConfigurationError(ValueError):
    """Raised when required R2 settings are missing or invalid."""


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise R2ConfigurationError(f"{name} is not set.")
    return value


@dataclass(frozen=True)
class R2Settings:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    presigned_url_expiry_seconds: int = 3600

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"

    @classmethod
    def from_environment(cls) -> "R2Settings":
        raw_expiry = os.getenv("R2_PRESIGNED_URL_EXPIRY_SECONDS", "3600")
        try:
            expiry = int(raw_expiry)
        except ValueError as exc:
            raise R2ConfigurationError(
                "R2_PRESIGNED_URL_EXPIRY_SECONDS must be an integer."
            ) from exc

        if not 1 <= expiry <= MAX_PRESIGNED_URL_EXPIRY_SECONDS:
            raise R2ConfigurationError(
                "R2_PRESIGNED_URL_EXPIRY_SECONDS must be between 1 and 604800."
            )

        return cls(
            account_id=_required_environment("R2_ACCOUNT_ID"),
            access_key_id=_required_environment("R2_ACCESS_KEY_ID"),
            secret_access_key=_required_environment("R2_SECRET_ACCESS_KEY"),
            bucket_name=_required_environment("R2_BUCKET_NAME"),
            presigned_url_expiry_seconds=expiry,
        )


def create_r2_client(settings: R2Settings | None = None) -> Any:
    """Create an S3 client configured only for the selected R2 account."""
    settings = settings or R2Settings.from_environment()
    return boto3.client(
        service_name="s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def generate_presigned_url(
    object_key: str,
    *,
    settings: R2Settings | None = None,
    r2_client: Any | None = None,
) -> str:
    """Return a temporary, signed GET URL for one object in the private bucket."""
    settings = settings or R2Settings.from_environment()
    client = r2_client or create_r2_client(settings)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.bucket_name, "Key": object_key},
        ExpiresIn=settings.presigned_url_expiry_seconds,
    )


def check_r2_connection(settings: R2Settings | None = None) -> None:
    """Verify read access without creating, changing, or deleting any object."""
    settings = settings or R2Settings.from_environment()
    client = create_r2_client(settings)
    client.list_objects_v2(Bucket=settings.bucket_name, MaxKeys=1)


def main() -> int:
    load_dotenv()
    try:
        settings = R2Settings.from_environment()
        check_r2_connection(settings)
    except Exception as exc:
        print(f"[R2] Connection failed: {exc}")
        return 1

    print(f"[R2] Private bucket connection successful: {settings.bucket_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
