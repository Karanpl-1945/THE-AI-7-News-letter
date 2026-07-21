"""Sends the newspaper preview to the admin, and the final issue to subscribers."""

import os
from typing import Optional

from delivery.transport import get_email_transport


def _review_action_buttons(issue_key: str) -> str:
    """Real one-tap Approve/Request-changes buttons, when the API is deployed."""
    api_base_url = os.environ.get("API_BASE_URL", "").strip().rstrip("/")
    if not api_base_url:
        return ""

    from api.security import make_review_token

    approve_url = f"{api_base_url}/review/confirm?token={make_review_token(issue_key, 'approve')}"
    changes_url = (
        f"{api_base_url}/review/confirm?token={make_review_token(issue_key, 'request_changes')}"
    )
    button_style = (
        "display:inline-block;padding:10px 20px;margin-right:10px;border-radius:6px;"
        "text-decoration:none;font:14px sans-serif;color:#fff"
    )
    return (
        f"<p>"
        f"<a href='{approve_url}' style='{button_style};background:#2e7d32'>Approve</a>"
        f"<a href='{changes_url}' style='{button_style};background:#c62828'>Request Changes</a>"
        f"</p>"
    )


def send_admin_review_email(
    html_content: str,
    pdf_path: Optional[str],
    issue_date: str,
    issue_key: str,
    revision_number: int = 1,
) -> bool:
    """Send the admin a preview of a draft issue awaiting approve/request-changes."""
    admin_email = os.environ.get("ADMIN_EMAIL", "")
    if not admin_email:
        print("[Email] ADMIN_EMAIL not set. Skipping admin review email.")
        return False

    revision_note = f" (revision {revision_number})" if revision_number > 1 else ""
    subject = f"[REVIEW NEEDED] THE AI 7 · {issue_date}{revision_note}"
    instructions = (
        f"<p style='font:14px sans-serif;color:#555'>"
        f"This is a draft awaiting your review. Tap a button below, or run the "
        f"<code>review-newsletter</code> GitHub Actions workflow with "
        f"<code>issue_key={issue_key}</code> and <code>decision=approve</code> to send it to "
        f"subscribers, or <code>decision=request_changes</code> with feedback to regenerate it."
        f"</p>"
        f"{_review_action_buttons(issue_key)}"
        f"<hr/>"
    )

    return get_email_transport().send(
        to=admin_email,
        subject=subject,
        html=instructions + html_content,
        pdf_path=pdf_path,
        pdf_filename=f"ai_dispatch_preview_{issue_key}.pdf" if pdf_path else None,
    )


def _unsubscribe_footer(recipient_email: str) -> str:
    api_base_url = os.environ.get("API_BASE_URL", "").strip().rstrip("/")
    if not api_base_url:
        return ""

    from api.security import make_unsubscribe_token

    token = make_unsubscribe_token(recipient_email)
    url = f"{api_base_url}/unsubscribe/confirm?token={token}"
    return (
        f"<p style='font:12px sans-serif;color:#999;margin-top:24px'>"
        f"<a href='{url}' style='color:#999'>Unsubscribe</a>"
        f"</p>"
    )


def send_welcome_email(recipient_email: str) -> bool:
    """Welcome a brand-new subscriber, linking the latest issue if one has ever been sent.

    Subscribing never triggers a resend of a past issue's full content — only a
    temporary, private link to it (via a presigned R2 URL) — so this stays
    consistent with the "you only get issues sent while you're subscribed"
    idempotency the rest of delivery relies on.
    """
    from database.artifact_repository import get_artifacts_for_run
    from database.workflow_repository import get_latest_sent_issue
    from storage.r2_client import generate_presigned_url

    latest = get_latest_sent_issue()
    if latest is None:
        body = (
            "<h2>Welcome to THE AI 7!</h2>"
            "<p>You're subscribed. You'll get a new issue every Sunday, "
            "reviewed by hand before it's sent.</p>"
        )
        return get_email_transport().send(
            to=recipient_email,
            subject="Welcome to THE AI 7!",
            html=body + _unsubscribe_footer(recipient_email),
        )

    artifacts = get_artifacts_for_run(latest.workflow_run_id)
    html_record = artifacts.get("html")
    latest_link = (
        f"<p><a href='{generate_presigned_url(html_record.object_key)}'>"
        f"Read the {latest.issue_date.strftime('%B %d, %Y')} issue &rarr;</a></p>"
        if html_record
        else ""
    )
    body = (
        "<h2>Welcome to THE AI 7!</h2>"
        "<p>You're subscribed. You'll get a new issue every Sunday, "
        "reviewed by hand before it's sent.</p>"
        f"{latest_link}"
        "<p>In the meantime, here's the most recent issue to get you started.</p>"
    )
    return get_email_transport().send(
        to=recipient_email,
        subject="Welcome to THE AI 7! Here's the latest issue",
        html=body + _unsubscribe_footer(recipient_email),
    )


def send_to_subscriber(
    html_content: str,
    pdf_path: Optional[str],
    issue_date: str,
    recipient_email: str,
) -> bool:
    """Send the approved issue to one subscriber."""
    subject = f"⚡ THE AI 7 — Your weekly AI intelligence brief · {issue_date}"
    return get_email_transport().send(
        to=recipient_email,
        subject=subject,
        html=html_content + _unsubscribe_footer(recipient_email),
        pdf_path=pdf_path,
    )
