"""One-tap admin review: a link shows a confirmation page, a button POSTs the action.

GET never mutates state (email/messaging clients often prefetch links for
previews, which must not silently trigger an approval).
"""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from api.security import TokenError, verify_review_token
from graph.review import ReviewError, handle_review_decision


router = APIRouter(prefix="/review", tags=["review"])


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<html><head><title>{title}</title></head>"
        f"<body style='font-family:sans-serif;max-width:480px;margin:40px auto'>{body}</body></html>"
    )


@router.get("/confirm")
def confirm(token: str) -> HTMLResponse:
    try:
        payload = verify_review_token(token)
    except TokenError as exc:
        return _page("Link error", f"<p>{exc}</p>")

    decision = payload["decision"]
    issue_key = payload["issue_key"]

    if decision == "approve":
        action = "/review/approve"
        body = (
            f"<h2>Approve issue {issue_key}?</h2>"
            f"<p>This sends it to every active subscriber.</p>"
            f"<form method='post' action='{action}'>"
            f"<input type='hidden' name='token' value='{token}'>"
            f"<button type='submit'>Confirm Approve</button></form>"
        )
    else:
        action = "/review/request-changes"
        body = (
            f"<h2>Request changes on issue {issue_key}</h2>"
            f"<form method='post' action='{action}'>"
            f"<input type='hidden' name='token' value='{token}'>"
            f"<textarea name='feedback' rows='4' style='width:100%' "
            f"placeholder='What should change?' required></textarea><br><br>"
            f"<button type='submit'>Confirm Request Changes</button></form>"
        )

    return _page("Confirm your decision", body)


@router.post("/approve")
def approve(token: str = Form(...)) -> HTMLResponse:
    try:
        payload = verify_review_token(token)
    except TokenError as exc:
        return _page("Link error", f"<p>{exc}</p>")

    try:
        result = handle_review_decision(payload["issue_key"], "approve")
    except ReviewError as exc:
        return _page("Could not approve", f"<p>{exc}</p>")

    return _page(
        "Approved",
        f"<h2>Sent!</h2><p>Delivered to {result['sent']} subscriber(s), "
        f"{result['failed']} failed, {result['skipped']} already sent.</p>",
    )


@router.post("/request-changes")
def request_changes(token: str = Form(...), feedback: str = Form(...)) -> HTMLResponse:
    try:
        payload = verify_review_token(token)
    except TokenError as exc:
        return _page("Link error", f"<p>{exc}</p>")

    try:
        result = handle_review_decision(
            payload["issue_key"], "request_changes", feedback=feedback
        )
    except ReviewError as exc:
        return _page("Could not request changes", f"<p>{exc}</p>")

    return _page(
        "Feedback sent",
        f"<h2>Regenerating draft (revision {result['revision_number']})</h2>"
        f"<p>You'll get a new review email shortly.</p>",
    )
