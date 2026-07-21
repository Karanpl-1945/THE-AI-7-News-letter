"""Persistence operations for newsletter issues and workflow executions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os
from typing import Any, Dict
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from database.connection import database_connection


VALID_TRIGGER_TYPES = {"local", "github_manual", "github_schedule"}


@dataclass(frozen=True)
class WorkflowTracking:
    issue_id: UUID
    run_id: UUID


@dataclass(frozen=True)
class IssueLookup:
    issue_id: UUID
    status: str
    thread_id: str
    workflow_run_id: UUID


@dataclass(frozen=True)
class SentIssueLookup:
    issue_id: UUID
    workflow_run_id: UUID
    issue_date: date


def _trigger_type() -> str:
    value = os.getenv("WORKFLOW_TRIGGER", "local").strip().lower()
    if value not in VALID_TRIGGER_TYPES:
        allowed = ", ".join(sorted(VALID_TRIGGER_TYPES))
        raise ValueError(f"WORKFLOW_TRIGGER must be one of: {allowed}")
    return value


def _run_metadata() -> Dict[str, Any]:
    """Capture useful GitHub identifiers without storing secrets."""
    keys = (
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_REPOSITORY",
        "GITHUB_SHA",
    )
    return {
        key.lower(): os.environ[key]
        for key in keys
        if os.getenv(key)
    }


def begin_workflow_run(
    *,
    issue_key: str,
    issue_date: date,
    iso_year: int,
    iso_week: int,
    thread_id: str,
    dry_run: bool,
    database_url: str | None = None,
) -> WorkflowTracking:
    """Create or resume the application records for one checkpoint thread."""
    issue_id = uuid4()
    run_id = uuid4()

    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO newsletter_issues (
                    id, issue_key, issue_date, iso_year, iso_week, status
                )
                VALUES (%s, %s, %s, %s, %s, 'running')
                ON CONFLICT (issue_key) DO UPDATE SET
                    issue_date = EXCLUDED.issue_date,
                    status = 'running',
                    updated_at = NOW(),
                    completed_at = NULL
                RETURNING id
                """,
                (issue_id, issue_key, issue_date, iso_year, iso_week),
            )
            issue_row = cursor.fetchone()
            if not issue_row:
                raise RuntimeError("PostgreSQL did not return a newsletter issue ID.")
            issue_id = issue_row[0]

            cursor.execute(
                """
                INSERT INTO workflow_runs (
                    id, issue_id, thread_id, trigger_type, dry_run,
                    status, run_metadata
                )
                VALUES (%s, %s, %s, %s, %s, 'running', %s)
                ON CONFLICT (thread_id) DO UPDATE SET
                    issue_id = EXCLUDED.issue_id,
                    trigger_type = EXCLUDED.trigger_type,
                    dry_run = EXCLUDED.dry_run,
                    status = 'running',
                    attempt_count = workflow_runs.attempt_count + 1,
                    run_metadata = workflow_runs.run_metadata || EXCLUDED.run_metadata,
                    last_error = NULL,
                    updated_at = NOW(),
                    finished_at = NULL
                RETURNING id
                """,
                (
                    run_id,
                    issue_id,
                    thread_id,
                    _trigger_type(),
                    dry_run,
                    Jsonb(_run_metadata()),
                ),
            )
            run_row = cursor.fetchone()
            if not run_row:
                raise RuntimeError("PostgreSQL did not return a workflow run ID.")
            run_id = run_row[0]

    return WorkflowTracking(issue_id=issue_id, run_id=run_id)


def complete_workflow_run(
    tracking: WorkflowTracking,
    *,
    admin_notified: bool,
    database_url: str | None = None,
) -> None:
    """Mark the run complete and update the business issue status.

    The issue moves to `reviewing` (awaiting the admin's approve/request-changes
    decision) once notified, rather than being considered sent — sending to
    subscribers now only happens after approval, via `graph/review.py`.
    """
    issue_status = "reviewing" if admin_notified else "generated"
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE workflow_runs
                SET status = 'completed', updated_at = NOW(), finished_at = NOW()
                WHERE id = %s
                """,
                (tracking.run_id,),
            )
            cursor.execute(
                """
                UPDATE newsletter_issues
                SET status = %s, updated_at = NOW(), completed_at = NOW()
                WHERE id = %s
                """,
                (issue_status, tracking.issue_id),
            )


def get_issue_by_key(
    issue_key: str,
    *,
    database_url: str | None = None,
) -> IssueLookup | None:
    """Look up an issue and its latest workflow run's checkpoint thread."""
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT i.id, i.status, r.thread_id, r.id
                FROM newsletter_issues i
                JOIN workflow_runs r ON r.issue_id = i.id
                WHERE i.issue_key = %s
                ORDER BY r.started_at DESC
                LIMIT 1
                """,
                (issue_key,),
            )
            row = cursor.fetchone()

    if not row:
        return None
    return IssueLookup(issue_id=row[0], status=row[1], thread_id=row[2], workflow_run_id=row[3])


def get_latest_sent_issue(
    *,
    database_url: str | None = None,
) -> SentIssueLookup | None:
    """Look up the most recently delivered issue, for welcoming new subscribers."""
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT i.id, r.id, i.issue_date
                FROM newsletter_issues i
                JOIN workflow_runs r ON r.issue_id = i.id
                WHERE i.status = 'sent'
                ORDER BY i.completed_at DESC
                LIMIT 1
                """,
            )
            row = cursor.fetchone()

    if not row:
        return None
    return SentIssueLookup(issue_id=row[0], workflow_run_id=row[1], issue_date=row[2])


def update_issue_status(
    issue_id: UUID,
    status: str,
    *,
    database_url: str | None = None,
) -> None:
    """Move a newsletter issue to a new status (e.g. approved, sent, failed)."""
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE newsletter_issues
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (status, issue_id),
            )


def fail_workflow_run(
    tracking: WorkflowTracking,
    error: Exception,
    *,
    database_url: str | None = None,
) -> None:
    """Record a recoverable failure without changing LangGraph checkpoints."""
    message = str(error)[:4000]
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE workflow_runs
                SET status = 'failed', last_error = %s,
                    updated_at = NOW(), finished_at = NOW()
                WHERE id = %s
                """,
                (message, tracking.run_id),
            )
            cursor.execute(
                """
                UPDATE newsletter_issues
                SET status = 'failed', updated_at = NOW()
                WHERE id = %s
                """,
                (tracking.issue_id,),
            )
