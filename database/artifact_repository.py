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


def _record_from_row(row) -> ArtifactRecord:
    return ArtifactRecord(
        id=row[0],
        issue_id=row[1],
        workflow_run_id=row[2],
        artifact_type=row[3],
        bucket_name=row[4],
        object_key=row[5],
        content_type=row[6],
        size_bytes=row[7],
        sha256=row[8],
        etag=row[9],
    )


def get_artifacts_for_run(
    workflow_run_id: UUID,
    *,
    database_url: str | None = None,
) -> dict[str, ArtifactRecord]:
    """Load the persisted artifact metadata for one workflow execution."""
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, issue_id, workflow_run_id, artifact_type,
                       bucket_name, object_key, content_type,
                       size_bytes, sha256, etag
                FROM newsletter_artifacts
                WHERE workflow_run_id = %s
                """,
                (workflow_run_id,),
            )
            rows = cursor.fetchall()

    return {
        record.artifact_type: record
        for record in (_record_from_row(row) for row in rows)
    }


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
    return _record_from_row(
        (
            row[0],
            issue_id,
            workflow_run_id,
            artifact_type,
            bucket_name,
            object_key,
            content_type,
            size_bytes,
            sha256,
            etag,
        )
    )
