"""Per-user rate limiting.

Protects the inference backend from a single user hammering an endpoint,
and from ~70 students all arriving at once. Limits come from the
environment (`LABTUTOR_RATELIMIT_*`).

KNOWN LIMITATION: the window is held in this process's memory, keyed
per OS process, not per container. `infra/backend.Dockerfile` runs
`uvicorn --workers 2`, so even the single-container pilot topology
already has two independent worker processes, each with its own
un-shared limiter state -- the effective limit for a given user is
already up to 2x the configured value today, not only under a
hypothetical multi-replica scale-out. Add another replica and it
multiplies again. Moving this to a shared store (e.g. Redis) is the
fix, and is listed in README "Known limitations" rather than being
quietly assumed away -- verify the actual effective rate under load
before the pilot, don't just trust the configured number.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from backend.config import get_settings


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: float = 0.0


class SlidingWindowLimiter:
    """Fixed count per rolling window, keyed by (scope, user)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self, scope: str, user_id: str, *, limit: int, window_seconds: float
    ) -> LimitDecision:
        if limit <= 0:
            return LimitDecision(allowed=True, remaining=0)

        now = time.monotonic()
        cutoff = now - window_seconds
        key = (scope, user_id)

        with self._lock:
            window = self._hits.setdefault(key, deque())
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) >= limit:
                retry_after = max(0.0, window[0] + window_seconds - now)
                return LimitDecision(
                    allowed=False, remaining=0, retry_after_seconds=retry_after
                )

            window.append(now)
            return LimitDecision(allowed=True, remaining=limit - len(window))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter = SlidingWindowLimiter()


def check_socratic_turn(user_id: str) -> LimitDecision:
    settings = get_settings()
    return _limiter.check(
        "socratic",
        user_id,
        limit=settings.ratelimit_socratic_per_minute,
        window_seconds=60.0,
    )


def check_submission(user_id: str) -> LimitDecision:
    settings = get_settings()
    return _limiter.check(
        "submission",
        user_id,
        limit=settings.ratelimit_submit_per_hour,
        window_seconds=3600.0,
    )


def check_qa_turn(user_id: str) -> LimitDecision:
    settings = get_settings()
    return _limiter.check(
        "qa",
        user_id,
        limit=settings.ratelimit_qa_per_minute,
        window_seconds=60.0,
    )


def reset_for_tests() -> None:
    _limiter.reset()
