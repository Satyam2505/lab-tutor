"""Signed session cookies.

The cookie carries an identifier and the email, and nothing that grants
authority. In particular it does **not** carry the role: the role is
re-derived from the verified email on every request that needs it, so a
tampered or stale cookie cannot promote a student to faculty. See
`dependencies.py`.
"""

from __future__ import annotations

from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from backend.config import Settings, get_settings

COOKIE_NAME = "labtutor_session"
OAUTH_STATE_COOKIE = "labtutor_oauth_state"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="labtutor-session")


def issue(user_id: str, email: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return _serializer(settings).dumps({"uid": user_id, "email": email})


def read(token: str | None, settings: Settings | None = None) -> dict[str, Any] | None:
    if not token:
        return None
    settings = settings or get_settings()
    try:
        data = _serializer(settings).loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or "uid" not in data:
        return None
    return data


def cookie_kwargs(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "max_age": SESSION_MAX_AGE_SECONDS,
        "path": "/",
    }
