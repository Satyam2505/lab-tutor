"""Google OAuth, server-side role determination, and per-request gating.

Roles come from an admin allowlist checked first, then environment-
configured email domains, and are re-derived on every role-gated request
-- never trusted from a cookie or from login time. See `dependencies.py`.
"""

from backend.auth.dependencies import (
    Principal,
    current_user,
    faculty_or_admin_scope,
    faculty_scope,
    require_admin,
    require_faculty,
    require_faculty_or_admin,
    require_student,
    require_student_or_staff,
    student_scope,
)
from backend.auth.roles import DomainNotPermitted, domain_of, is_permitted, role_for_email

__all__ = [
    "DomainNotPermitted",
    "Principal",
    "current_user",
    "domain_of",
    "faculty_or_admin_scope",
    "faculty_scope",
    "is_permitted",
    "require_admin",
    "require_faculty",
    "require_faculty_or_admin",
    "require_student",
    "require_student_or_staff",
    "role_for_email",
    "student_scope",
]
