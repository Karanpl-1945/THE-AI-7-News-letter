"""Signed, tamper-proof tokens for one-click email links.

Two independent serializers (different salts) so a review token can never be
replayed as an unsubscribe token or vice versa.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


DEFAULT_TOKEN_MAX_AGE_SECONDS = 259_200  # 3 days


class TokenError(ValueError):
    """Raised when a token is missing, tampered with, or expired."""


def _signing_secret() -> str:
    secret = os.environ.get("API_SIGNING_SECRET", "").strip()
    if not secret:
        raise TokenError("API_SIGNING_SECRET is not configured.")
    return secret


def _token_max_age_seconds() -> int:
    return int(os.environ.get("API_TOKEN_MAX_AGE_SECONDS", str(DEFAULT_TOKEN_MAX_AGE_SECONDS)))


def _review_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_signing_secret(), salt="review-action")


def _unsubscribe_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_signing_secret(), salt="unsubscribe-action")


def make_review_token(issue_key: str, decision: str) -> str:
    return _review_serializer().dumps({"issue_key": issue_key, "decision": decision})


def verify_review_token(token: str, max_age: int | None = None) -> Dict[str, Any]:
    effective_max_age = max_age if max_age is not None else _token_max_age_seconds()
    try:
        return _review_serializer().loads(token, max_age=effective_max_age)
    except SignatureExpired as exc:
        raise TokenError("This review link has expired.") from exc
    except BadSignature as exc:
        raise TokenError("This review link is invalid.") from exc


def make_unsubscribe_token(email: str) -> str:
    return _unsubscribe_serializer().dumps({"email": email})


def verify_unsubscribe_token(token: str) -> str:
    try:
        # max_age=None: unsubscribe links must keep working indefinitely.
        payload = _unsubscribe_serializer().loads(token, max_age=None)
    except BadSignature as exc:
        raise TokenError("This unsubscribe link is invalid.") from exc
    return payload["email"]
