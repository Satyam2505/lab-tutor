"""Google OAuth 2.0 authorisation-code flow.

The security-relevant parts:

* The email is taken from Google's token response, never from anything
  the browser sent. A client cannot claim a domain.
* `email_verified` must be true. An unverified Google account could
  otherwise assert an address it does not own.
* The domain check runs here, at callback time, before any session
  exists. A rejected domain creates no user row and no session, and the
  attempt is written to the audit log.
* `state` is a signed, single-use value checked on return, so a callback
  cannot be replayed or forged from another site.

Re-checking the role on every later request is handled in
`dependencies.py`; passing this flow is not, on its own, sufficient
authorisation for anything.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer

from backend.config import Settings, get_settings
from backend.models import Role

log = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

STATE_MAX_AGE_SECONDS = 600


class OAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    """A verified identity. Constructing one implies Google vouched for it."""

    subject: str
    email: str
    name: str
    email_verified: bool


def _state_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="labtutor-oauth-state")


def redirect_uri(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return f"{settings.public_url.rstrip('/')}/api/auth/callback"


def build_authorize_url(settings: Settings | None = None) -> tuple[str, str]:
    """Return (url, state). The caller stores `state` in a cookie."""
    settings = settings or get_settings()
    if not settings.google_client_id:
        raise OAuthError("GOOGLE_CLIENT_ID is not configured")

    nonce = secrets.token_urlsafe(24)
    state = _state_serializer(settings).dumps({"n": nonce})
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(settings),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}", state


def verify_state(state: str, expected: str, settings: Settings | None = None) -> bool:
    """Signed and unexpired, and equal to the value issued to this browser."""
    settings = settings or get_settings()
    if not state or not expected or not secrets.compare_digest(state, expected):
        return False
    try:
        _state_serializer(settings).loads(state, max_age=STATE_MAX_AGE_SECONDS)
    except BadSignature:
        return False
    return True


async def exchange_code(code: str, settings: Settings | None = None) -> GoogleIdentity:
    """Swap an authorisation code for a verified identity."""
    settings = settings or get_settings()
    if not (settings.google_client_id and settings.google_client_secret):
        raise OAuthError("Google OAuth client credentials are not configured")

    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri(settings),
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(GOOGLE_TOKEN_URL, data=data)
            token_resp.raise_for_status()
            access_token = token_resp.json().get("access_token")
            if not access_token:
                raise OAuthError("Google token response contained no access token")

            info_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            info_resp.raise_for_status()
            info = info_resp.json()
    except httpx.HTTPError as exc:
        raise OAuthError(f"Google OAuth exchange failed: {exc}") from exc

    email = (info.get("email") or "").strip().lower()
    subject = info.get("sub") or ""
    if not email or not subject:
        raise OAuthError("Google userinfo response was missing email or subject")

    return GoogleIdentity(
        subject=subject,
        email=email,
        name=info.get("name") or email.split("@")[0],
        email_verified=bool(info.get("email_verified")),
    )


def role_or_reject(identity: GoogleIdentity, settings: Settings | None = None) -> Role:
    """Final admission decision for a verified identity."""
    from backend.auth.roles import DomainNotPermitted, role_for_email

    if not identity.email_verified:
        raise DomainNotPermitted(identity.email)
    return role_for_email(identity.email, settings)
