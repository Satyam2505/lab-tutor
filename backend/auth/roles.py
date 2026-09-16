"""Server-side role determination from a verified email domain.

Both domain lists come from the environment (`LABTUTOR_STUDENT_DOMAINS`,
`LABTUTOR_FACULTY_DOMAINS`) so a correction or an additional domain never
requires a code change. Nothing here hardcodes a domain.

The email passed in must be one Google has verified in the OAuth token
exchange. A client-supplied email is not acceptable input to these
functions -- see `oauth.py`.
"""

from __future__ import annotations

from backend.config import Settings, get_settings
from backend.models import Role


class DomainNotPermitted(PermissionError):
    """The verified email is outside every configured domain."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Email domain not permitted for this deployment: {email}")


def domain_of(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower()


def role_for_email(email: str, settings: Settings | None = None) -> Role:
    """Map a verified email to a role. Never refuses a well-formed email.

    Admin is checked FIRST, against a platform-wide allowlist -- admin is
    not a domain-derived role and does not require joining a classroom. If
    the email isn't an admin, faculty is checked next: if a deployment
    ever configures overlapping lists, the more privileged reading must
    not be reachable by accident, so the overlap is resolved explicitly
    here rather than by list order.

    Any email that matches neither the faculty nor the student domain
    defaults to STUDENT -- the two domains are no longer a signup gate,
    only a role hint. `DomainNotPermitted` is now raised only for a
    malformed/empty email (no "@"); classroom join codes are the real
    access control for doing anything once signed in.
    """
    settings = settings or get_settings()
    normalised = (email or "").strip().lower()
    if normalised and normalised in settings.admin_emails:
        return Role.ADMIN

    domain = domain_of(email)
    if not domain:
        raise DomainNotPermitted(email or "(empty)")

    if domain in settings.faculty_domains:
        return Role.FACULTY
    return Role.STUDENT


def is_permitted(email: str, settings: Settings | None = None) -> bool:
    try:
        role_for_email(email, settings)
    except DomainNotPermitted:
        return False
    return True
