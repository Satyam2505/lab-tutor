"""Persistent classrooms, high-entropy join codes, active-experiment tagging."""

from backend.classrooms.service import (
    ClassroomError,
    ClassroomView,
    JoinClosed,
    NotEnrolled,
    create_classroom,
    generate_join_code,
    join_classroom,
    require_active_experiment,
    roster_with_users,
    set_active_experiment,
    set_join_open,
    student_count,
)

__all__ = [
    "ClassroomError",
    "ClassroomView",
    "JoinClosed",
    "NotEnrolled",
    "create_classroom",
    "generate_join_code",
    "join_classroom",
    "require_active_experiment",
    "roster_with_users",
    "set_active_experiment",
    "set_join_open",
    "student_count",
]
