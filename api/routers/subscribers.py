"""Public subscribe, token-restricted unsubscribe."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr

from api.security import TokenError, verify_unsubscribe_token
from database.subscriber_repository import add_subscriber, remove_subscriber


router = APIRouter(tags=["subscribers"])


class SubscribeRequest(BaseModel):
    email: EmailStr


class SubscribeResponse(BaseModel):
    email: str
    status: str


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<html><head><title>{title}</title></head>"
        f"<body style='font-family:sans-serif;max-width:480px;margin:40px auto'>{body}</body></html>"
    )


@router.post("/subscribe", response_model=SubscribeResponse)
def subscribe(request: SubscribeRequest) -> SubscribeResponse:
    record = add_subscriber(request.email)
    return SubscribeResponse(email=record.email, status=record.status)


@router.get("/unsubscribe/confirm")
def unsubscribe_confirm(token: str) -> HTMLResponse:
    try:
        email = verify_unsubscribe_token(token)
    except TokenError as exc:
        return _page("Link error", f"<p>{exc}</p>")

    body = (
        f"<h2>Unsubscribe {email}?</h2>"
        f"<form method='post' action='/unsubscribe'>"
        f"<input type='hidden' name='token' value='{token}'>"
        f"<button type='submit'>Confirm Unsubscribe</button></form>"
    )
    return _page("Confirm unsubscribe", body)


@router.post("/unsubscribe")
def unsubscribe(token: str = Form(...)) -> HTMLResponse:
    try:
        email = verify_unsubscribe_token(token)
    except TokenError as exc:
        return _page("Link error", f"<p>{exc}</p>")

    remove_subscriber(email)
    return _page("Unsubscribed", f"<p>{email} has been unsubscribed.</p>")
