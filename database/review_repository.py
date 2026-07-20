"""Persistence operations for admin approval decisions and per-subscriber delivery."""

from __future__ import annotations

from uuid import UUID, uuid4

from database.connection import database_connection


VALID_DECISIONS = {"approved", "changes_requested"}
VALID_DELIVERY_STATUSES = {"sent", "failed"}


def record_approval_decision(
    *,
    issue_id: UUID,
    workflow_run_id: UUID,
    decision: str,
    feedback: str | None,
    revision_number: int,
    database_url: str | None = None,
) -> None:
    """Append an audit record of one admin review decision."""
    if decision not in VALID_DECISIONS:
        allowed = ", ".join(sorted(VALID_DECISIONS))
        raise ValueError(f"decision must be one of: {allowed}")

    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO approvals (
                    id, issue_id, workflow_run_id, decision, feedback, revision_number
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (uuid4(), issue_id, workflow_run_id, decision, feedback, revision_number),
            )


def record_delivery(
    *,
    issue_id: UUID,
    subscriber_id: UUID,
    status: str,
    error_message: str | None = None,
    database_url: str | None = None,
) -> None:
    """Record one subscriber's delivery outcome, retried sends overwrite prior failures."""
    if status not in VALID_DELIVERY_STATUSES:
        allowed = ", ".join(sorted(VALID_DELIVERY_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")

    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO email_deliveries (
                    id, issue_id, subscriber_id, status, error_message, sent_at
                )
                VALUES (%s, %s, %s, %s, %s, CASE WHEN %s = 'sent' THEN NOW() ELSE NULL END)
                ON CONFLICT (issue_id, subscriber_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    sent_at = EXCLUDED.sent_at,
                    updated_at = NOW()
                """,
                (uuid4(), issue_id, subscriber_id, status, error_message, status),
            )


def get_sent_subscriber_ids(
    issue_id: UUID,
    *,
    database_url: str | None = None,
) -> set[UUID]:
    """Return subscriber IDs already successfully delivered this issue.

    Deliberately filters on status = 'sent' rather than "any row exists" — a
    subscriber whose previous attempt failed must be retried, not skipped.
    """
    with database_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT subscriber_id
                FROM email_deliveries
                WHERE issue_id = %s AND status = 'sent'
                """,
                (issue_id,),
            )
            rows = cursor.fetchall()

    return {row[0] for row in rows}
