"""Professor-triggered, async, idempotent per-student trajectory summaries.

Qualitative engagement reads, not grades. Visible only to the professor,
never generated mid-session. See `jobs.py` for the batching rules.
"""

from backend.summaries.jobs import run_job, start_job
from backend.summaries.trajectory import (
    Trajectory,
    build_trajectory,
    deterministic_summary,
)

__all__ = [
    "Trajectory",
    "build_trajectory",
    "deterministic_summary",
    "run_job",
    "start_job",
]
