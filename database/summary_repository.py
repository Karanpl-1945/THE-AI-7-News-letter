"""Persistence boundary for source items and item-level summary caching."""

from __future__ import annotations

from contextlib import contextmanager
import json
from typing import Any, Dict, Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from database.connection import database_connection


def canonicalize_url(value: str) -> str:
    """Normalize URLs so tracking parameters do not create duplicate sources."""
    if not value:
        return ""
    parts = urlsplit(value.strip())
    query = urlencode(
        [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        ]
    )
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            query,
            "",
        )
    )


def _json_safe(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert collector-specific objects into JSON-compatible metadata."""
    return json.loads(json.dumps(item, default=str))


class SummaryRepository:
    """Read and write summaries using an existing PostgreSQL connection."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def upsert_source_item(
        self,
        *,
        item: Dict[str, Any],
        item_type: str,
        content_hash: str,
        raw_content: str,
    ) -> UUID:
        """Store the latest extracted source content and return its stable ID."""
        canonical_url = canonicalize_url(str(item.get("url", "")))
        source_key = f"{item_type}:{canonical_url or content_hash}"
        source_id = uuid4()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO source_items (
                    id, source_key, item_type, canonical_url, title,
                    content_hash, raw_content, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_key) DO UPDATE SET
                    item_type = EXCLUDED.item_type,
                    canonical_url = EXCLUDED.canonical_url,
                    title = EXCLUDED.title,
                    content_hash = EXCLUDED.content_hash,
                    raw_content = EXCLUDED.raw_content,
                    metadata = EXCLUDED.metadata,
                    last_seen_at = NOW()
                RETURNING id
                """,
                (
                    source_id,
                    source_key,
                    item_type,
                    canonical_url or None,
                    str(item.get("title", "")),
                    content_hash,
                    raw_content,
                    Jsonb(_json_safe(item)),
                ),
            )
            stored_id = cursor.fetchone()

        if not stored_id:
            raise RuntimeError("PostgreSQL did not return a source item ID.")
        self.connection.commit()
        return stored_id[0]

    def get_cached_summary(
        self,
        *,
        source_item_id: UUID,
        content_hash: str,
        model_name: str,
        prompt_fingerprint: str,
    ) -> Dict[str, Any] | None:
        """Return an exact cache hit and update its last-used timestamp."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, summary_json
                FROM article_summaries
                WHERE source_item_id = %s
                  AND content_hash = %s
                  AND model_name = %s
                  AND prompt_fingerprint = %s
                """,
                (
                    source_item_id,
                    content_hash,
                    model_name,
                    prompt_fingerprint,
                ),
            )
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                """
                UPDATE article_summaries
                SET last_used_at = NOW()
                WHERE id = %s
                """,
                (row[0],),
            )

        self.connection.commit()
        summary = row[1]
        return summary if isinstance(summary, dict) else None

    def save_summary(
        self,
        *,
        source_item_id: UUID,
        content_hash: str,
        model_name: str,
        prompt_version: str,
        prompt_fingerprint: str,
        summary: Dict[str, Any],
    ) -> None:
        """Commit one valid Groq summary immediately for retry safety."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO article_summaries (
                    id, source_item_id, content_hash, model_name,
                    prompt_version, prompt_fingerprint, summary_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    source_item_id, content_hash, model_name, prompt_fingerprint
                ) DO UPDATE SET
                    summary_json = EXCLUDED.summary_json,
                    last_used_at = NOW()
                """,
                (
                    uuid4(),
                    source_item_id,
                    content_hash,
                    model_name,
                    prompt_version,
                    prompt_fingerprint,
                    Jsonb(_json_safe(summary)),
                ),
            )
        self.connection.commit()


@contextmanager
def summary_repository(
    database_url: str | None = None,
) -> Iterator[SummaryRepository]:
    """Yield one repository connection for a summary batch."""
    with database_connection(database_url) as connection:
        yield SummaryRepository(connection)
