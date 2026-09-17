"""Async, idempotent per-student trajectory summaries, keyed on class session.

Qualitative engagement reads, not grades. Visible only to faculty/admin,
never generated mid-session. Auto-triggered on class-session end
(`enqueue_for_session`), with a manual regeneration path
(`start_job_for_session` + `run_job`) for backfill/refresh. See `jobs.py`
for the batching rules.
"""

from backend.summaries.jobs import (
    enqueue_for_session,
    run_job,
    start_job_for_session,
    track_background_task,
)
from backend.summaries.trajectory import (
    Trajectory,
    build_trajectory,
    deterministic_summary,
)

__all__ = [
    "Trajectory",
    "build_trajectory",
    "deterministic_summary",
    "enqueue_for_session",
    "run_job",
    "start_job_for_session",
    "track_background_task",
]
