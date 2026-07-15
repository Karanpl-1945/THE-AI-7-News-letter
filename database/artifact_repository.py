"""Persistence operations for metadata about files stored in Cloudflare R2."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from database.connection import database_connection


VALID_ARTIFACT_TYPES = {"html", "pdf", "image"}


@dataclass(frozen=True)
class ArtifactRecord:
    id: UUID
    issue_id: UUID
    workflow_run_id: UUID
    artifact_type: str
    bucket_name: str
    object_key: str
    content_type: str
    size_bytes: int
    sha256: str
    etag: str | None


def save_artifact_metadata(
    *,
    issue_id: UUID,
    workflow_run_id: UUID,
    artifact_type: str,
    bucket_name: str,
    object_key: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    etag: str | None,
    database_url: str | None = None,
) -> ArtifactRecord:
    """Insert or update one artifact for a workflow run and return its record."""
    if artifact_type not in VALID_ARTIFACT_TYPES:
        allowed = ", ".join(sorted(VALID_ARTIFACT_TYPES))
        raise ValueError(f"artifact_type must be one of: {allowed}")
    if size_bytes < 0:
        raise ValueError("size_bytes cannot be negative")
    if len(sha256) != 64:
        raise ValueError("sha256 must be a 64-character hexadecimal digest")

    artifact_id = uuid4()
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO newsletter_artifacts (
                    id, issue_id, workflow_run_id, artifact_type,
                    bucket_name, object_key, content_type,
                    size_bytes, sha256, etag
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (workflow_run_id, artifact_type) DO UPDATE SET
                    issue_id = EXCLUDED.issue_id,
                    bucket_name = EXCLUDED.bucket_name,
                    object_key = EXCLUDED.object_key,
                    content_type = EXCLUDED.content_type,
                    size_bytes = EXCLUDED.size_bytes,
                    sha256 = EXCLUDED.sha256,
                    etag = EXCLUDED.etag,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    artifact_id,
                    issue_id,
                    workflow_run_id,
                    artifact_type,
                    bucket_name,
                    object_key,
                    content_type,
                    size_bytes,
                    sha256,
                    etag,
                ),
            )
            row = cursor.fetchone()

    if not row:
        raise RuntimeError("PostgreSQL did not return an artifact ID.")
    return ArtifactRecord(
        id=row[0],
        issue_id=issue_id,
        workflow_run_id=workflow_run_id,
        artifact_type=artifact_type,
        bucket_name=bucket_name,
        object_key=object_key,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        etag=etag,
    )
