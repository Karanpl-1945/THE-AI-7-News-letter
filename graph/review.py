"""Resumes the paused pipeline graph with an admin's approve/request-changes decision.

The graph itself pauses at the "approval" node (via LangGraph's `interrupt()`);
this module's job is just to look up the right checkpoint thread and resume it
with `Command(resume=...)` — the graph's own conditional edge then routes to
"send" (approve) or loops back to "edit" (request_changes).
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, cast

from dotenv import load_dotenv
from langfuse import observe
from langgraph.types import Command

from graph.pipeline import NewsletterState, build_pipeline


class ReviewError(ValueError):
    """Raised when a review decision cannot be applied as requested."""


@observe(name="handle_review_decision", as_type="agent")
def handle_review_decision(
    issue_key: str,
    decision: str,
    feedback: str | None = None,
) -> Dict[str, Any]:
    from database.checkpointer import postgres_checkpointer
    from database.review_repository import record_approval_decision
    from database.workflow_repository import get_issue_by_key, update_issue_status
    from observability import configure_langfuse

    configure_langfuse()

    if decision not in {"approve", "request_changes"}:
        raise ReviewError("decision must be 'approve' or 'request_changes'")
    if decision == "request_changes" and not feedback:
        raise ReviewError("feedback is required when decision is 'request_changes'")

    issue = get_issue_by_key(issue_key)
    if issue is None:
        raise ReviewError(f"No newsletter issue found for issue_key={issue_key!r}")

    config = {"configurable": {"thread_id": issue.thread_id}}

    with postgres_checkpointer() as checkpointer:
        pipeline = build_pipeline(checkpointer=checkpointer)
        snapshot = pipeline.get_state(config)

        # The graph's own paused position is the source of truth for "is this
        # actually awaiting review" — not a parallel status flag we'd have to
        # keep in sync by hand. One exception: an issue that already finished
        # via "send" can still be re-approved to retry a partially failed
        # broadcast — see the branch below.
        already_sent = not snapshot.next and snapshot.values.get("review_decision") == "approve"
        if snapshot.next != ("approval",) and not (decision == "approve" and already_sent):
            raise ReviewError(
                f"Issue {issue_key} is not awaiting review (next={snapshot.next!r})"
            )

        if already_sent:
            # The graph already reached END through "send" — there is no
            # pending interrupt to resume, so retry the delivery step
            # directly instead. send_to_subscribers's own per-subscriber
            # status='sent' check means this only retries whoever didn't
            # get through last time; nobody already delivered is re-sent.
            from delivery.broadcast import send_to_subscribers

            state = cast(NewsletterState, dict(snapshot.values))
            result = send_to_subscribers(state, issue.issue_id)
            delivered = result["sent"] + result["skipped"]
            if delivered == 0:
                final_status = "failed" if result["failed"] > 0 else "approved"
            else:
                final_status = "sent"
            update_issue_status(issue.issue_id, final_status)
            return {
                "decision": "approve",
                "issue_key": issue_key,
                **result,
                "status": final_status,
                "retried": True,
            }

        current_revision = snapshot.values.get("revision_number", 1)
        next_revision = current_revision + 1 if decision == "request_changes" else current_revision

        record_approval_decision(
            issue_id=issue.issue_id,
            workflow_run_id=issue.workflow_run_id,
            decision="approved" if decision == "approve" else "changes_requested",
            feedback=feedback if decision == "request_changes" else None,
            revision_number=next_revision,
        )

        final_state = cast(
            NewsletterState,
            pipeline.invoke(
                Command(resume={"decision": decision, "feedback": feedback}),
                config=config,
            ),
        )
        new_snapshot = pipeline.get_state(config)

        if new_snapshot.next:
            # Looped back through edit → ... → notify_admin → approval again.
            update_issue_status(issue.issue_id, "reviewing")
            return {
                "decision": "request_changes",
                "issue_key": issue_key,
                "revision_number": final_state.get("revision_number", next_revision),
                "admin_notified": final_state.get("admin_notified"),
                "status": "reviewing",
            }

        # Reached END via the "send" node.
        result = final_state.get("send_result") or {"sent": 0, "failed": 0, "skipped": 0}
        delivered = result["sent"] + result["skipped"]
        if delivered == 0:
            final_status = "failed" if result["failed"] > 0 else "approved"
        else:
            final_status = "sent"
        update_issue_status(issue.issue_id, final_status)
        return {"decision": "approve", "issue_key": issue_key, **result, "status": final_status}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply an admin review decision to an issue.")
    parser.add_argument("--issue-key", required=True)
    parser.add_argument("--decision", required=True, choices=["approve", "request_changes"])
    parser.add_argument("--feedback", default=None)
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    from observability import flush_langfuse

    args = _parse_args()
    try:
        try:
            result = handle_review_decision(args.issue_key, args.decision, args.feedback or None)
        except ReviewError as exc:
            print(f"[Review] {exc}")
            return 1
    finally:
        flush_langfuse()

    print(f"[Review] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
