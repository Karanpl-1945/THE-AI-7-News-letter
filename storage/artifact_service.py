"""Upload generated newsletter files to R2 and persist their metadata."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from database.artifact_repository import ArtifactRecord, save_artifact_metadata
from storage.r2_client import R2Settings, create_r2_client


ARTIFACT_CONTENT_TYPES = {
    ".html": ("html", "text/html; charset=utf-8"),
    ".pdf": ("pdf", "application/pdf"),
}


@dataclass(frozen=True)
class PublishedArtifact:
    """The R2 location and persisted database record for one uploaded file."""

    record: ArtifactRecord
    endpoint_url: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_details(path: Path) -> tuple[str, str]:
    try:
        return ARTIFACT_CONTENT_TYPES[path.suffix.lower()]
    except KeyError as exc:
        allowed = ", ".join(sorted(ARTIFACT_CONTENT_TYPES))
        raise ValueError(f"Artifact file must use one of these extensions: {allowed}") from exc


def build_object_key(
    *,
    issue_id: UUID,
    workflow_run_id: UUID,
    artifact_type: str,
) -> str:
    """Build the stable private R2 key used when a run is retried."""
    return (
        f"newsletters/{issue_id}/{workflow_run_id}/"
        f"newsletter.{artifact_type}"
    )


def publish_artifact(
    path: str | Path,
    *,
    issue_id: UUID,
    workflow_run_id: UUID,
    settings: R2Settings | None = None,
    r2_client: Any | None = None,
    database_url: str | None = None,
) -> PublishedArtifact:
    """Upload one HTML/PDF artifact and then persist its R2 metadata in Neon."""
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact file does not exist: {artifact_path}")

    artifact_type, content_type = _artifact_details(artifact_path)
    settings = settings or R2Settings.from_environment()
    client = r2_client or create_r2_client(settings)
    object_key = build_object_key(
        issue_id=issue_id,
        workflow_run_id=workflow_run_id,
        artifact_type=artifact_type,
    )
    size_bytes = artifact_path.stat().st_size
    sha256 = _sha256(artifact_path)

    with artifact_path.open("rb") as file_handle:
        response = client.put_object(
            Bucket=settings.bucket_name,
            Key=object_key,
            Body=file_handle,
            ContentType=content_type,
            Metadata={
                "sha256": sha256,
                "issue-id": str(issue_id),
                "workflow-run-id": str(workflow_run_id),
            },
        )

    raw_etag = response.get("ETag")
    etag = raw_etag.strip('"') if isinstance(raw_etag, str) else None
    record = save_artifact_metadata(
        issue_id=issue_id,
        workflow_run_id=workflow_run_id,
        artifact_type=artifact_type,
        bucket_name=settings.bucket_name,
        object_key=object_key,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        etag=etag,
        database_url=database_url,
    )
    return PublishedArtifact(record=record, endpoint_url=settings.endpoint_url)
