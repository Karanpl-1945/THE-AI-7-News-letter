"""Handles an admin's approve/request-changes decision on a reviewing issue."""

from __future__ import annotations

import argparse
from typing import Any, Dict, cast
from uuid import UUID

from dotenv import load_dotenv

from graph.pipeline import (
    NewsletterState,
    build_pipeline,
    node_edit,
    node_format,
    node_notify_admin,
    node_pdf,
    node_publish,
)


class ReviewError(ValueError):
    """Raised when a review decision cannot be applied as requested."""


def handle_review_decision(
    issue_key: str,
    decision: str,
    feedback: str | None = None,
) -> Dict[str, Any]:
    from database.checkpointer import postgres_checkpointer
    from database.review_repository import record_approval_decision
    from database.workflow_repository import get_issue_by_key, update_issue_status
    from delivery.broadcast import send_to_subscribers

    if decision not in {"approve", "request_changes"}:
        raise ReviewError("decision must be 'approve' or 'request_changes'")
    if decision == "request_changes" and not feedback:
        raise ReviewError("feedback is required when decision is 'request_changes'")

    issue = get_issue_by_key(issue_key)
    if issue is None:
        raise ReviewError(f"No newsletter issue found for issue_key={issue_key!r}")
    if issue.status != "reviewing":
        raise ReviewError(
            f"Issue {issue_key} is not awaiting review (status={issue.status!r})"
        )

    config = {"configurable": {"thread_id": issue.thread_id}}

    with postgres_checkpointer() as checkpointer:
        pipeline = build_pipeline(checkpointer=checkpointer)
        snapshot = pipeline.get_state(config)
        if not snapshot.values:
            raise ReviewError(f"No checkpointed state found for issue_key={issue_key}")
        state = cast(NewsletterState, dict(snapshot.values))

        if decision == "approve":
            record_approval_decision(
                issue_id=issue.issue_id,
                workflow_run_id=issue.workflow_run_id,
                decision="approved",
                feedback=None,
                revision_number=1,
            )
            update_issue_status(issue.issue_id, "approved")
            result = send_to_subscribers(state, issue.issue_id)
            final_status = "sent" if result["sent"] > 0 or result["failed"] == 0 else "failed"
            update_issue_status(issue.issue_id, final_status)
            return {"decision": "approve", "issue_key": issue_key, **result, "status": final_status}

        revision_number = state.get("revision_number", 1) + 1
        record_approval_decision(
            issue_id=issue.issue_id,
            workflow_run_id=issue.workflow_run_id,
            decision="changes_requested",
            feedback=feedback,
            revision_number=revision_number,
        )

        state["editorial_feedback"] = feedback
        state["revision_number"] = revision_number
        state = cast(NewsletterState, node_edit(state))
        state = cast(NewsletterState, node_format(state))
        state = cast(NewsletterState, node_pdf(state))
        state = cast(NewsletterState, node_publish(state))
        state = cast(NewsletterState, node_notify_admin(state, revision_number=revision_number))

        pipeline.update_state(config, state)
        update_issue_status(issue.issue_id, "reviewing")
        return {
            "decision": "request_changes",
            "issue_key": issue_key,
            "revision_number": revision_number,
            "admin_notified": state["admin_notified"],
            "status": "reviewing",
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply an admin review decision to an issue.")
    parser.add_argument("--issue-key", required=True)
    parser.add_argument("--decision", required=True, choices=["approve", "request_changes"])
    parser.add_argument("--feedback", default=None)
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = _parse_args()
    try:
        result = handle_review_decision(args.issue_key, args.decision, args.feedback or None)
    except ReviewError as exc:
        print(f"[Review] {exc}")
        return 1

    print(f"[Review] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
