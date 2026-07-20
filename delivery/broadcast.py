"""Sends an approved issue to every active subscriber, skipping ones already sent."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from database.review_repository import get_sent_subscriber_ids, record_delivery
from database.subscriber_repository import list_active_subscribers
from delivery.email_sender import send_to_subscriber


def send_to_subscribers(state: Dict[str, Any], issue_id: UUID) -> Dict[str, int]:
    """Deliver the issue to every active subscriber not already sent this issue.

    A subscriber whose previous attempt failed is retried, since eligibility is
    keyed on delivery status rather than row existence (see
    `database.review_repository.get_sent_subscriber_ids`).
    """
    subscribers = list_active_subscribers()
    already_sent = get_sent_subscriber_ids(issue_id)
    pending = [s for s in subscribers if s.id not in already_sent]

    sent_count = 0
    failed_count = 0

    for subscriber in pending:
        success = send_to_subscriber(
            state["html_content"],
            state.get("pdf_path"),
            state["issue_date"],
            subscriber.email,
        )
        record_delivery(
            issue_id=issue_id,
            subscriber_id=subscriber.id,
            status="sent" if success else "failed",
            error_message=None if success else "Transport reported failure.",
        )
        if success:
            sent_count += 1
        else:
            failed_count += 1

    return {"sent": sent_count, "failed": failed_count, "skipped": len(already_sent)}
