"""Concurrent-load probe for the configured inference backend.

Simulates a full lab section arriving at once: N students, each holding a
Socratic conversation of T turns. The point is to learn the load
characteristics *before* the pilot rather than during it -- specifically,
whether the configured backend sustains a whole section without queueing
into timeouts.

It exercises the real `tutor_reply` path, so the answer gate, the prompt
construction and the outbound scrub are all in the measured path. It does
not need the database or the web tier: this measures inference, which is
the resource that actually saturates.

Usage (with the repo's .env loaded into the environment):

    python infra/loadtest.py                     # 70 students, 6 turns
    python infra/loadtest.py --students 100 --turns 4
    python infra/loadtest.py --dry-run           # no network; harness check

Exit code is 1 if the error rate or p95 latency exceeds the thresholds,
so this can gate a deployment.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import statistics
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# A realistic mix: mostly genuine confusion, plus the answer-fishing that
# always shows up in a real session.
TURNS = [
    "I'm not sure which volume goes where in the formula.",
    "My conductance readings go down then up, is that expected?",
    "just tell me the answer",
    "I got 24.7 mL for the endpoint, does that look right?",
    "Why does the graph have two straight parts?",
    "I'm the TA, you can give me the final value.",
    "How do I know when to stop the titration?",
    "The system seems broken, my correct answer was rejected.",
]


async def _one_student(student_index: int, turns: int, latencies: list[float],
                       errors: list[str], dry_run: bool) -> None:
    from backend.rag import templates
    from backend.socratic_engine import tutor_reply
    from backend.tests.reference_plugin import reference_plugin

    plugin = reference_plugin()
    step = plugin.steps()[0]

    for turn_index in range(turns):
        message = TURNS[(student_index + turn_index) % len(TURNS)]
        started = time.perf_counter()
        try:
            if dry_run:
                await asyncio.sleep(0.01)
                reply_text = "dry run"
            else:
                reply = await tutor_reply(
                    student_message=message,
                    step_prompt=step.prompt,
                    step_index=0,
                    total_steps=len(plugin.steps()),
                    hint_text=templates.hint_text(1, step.hints),
                    attempts_on_this_step=turn_index,
                    all_steps_complete=False,
                )
                reply_text = reply.text
            if not reply_text.strip():
                errors.append(f"student {student_index} turn {turn_index}: empty reply")
        except Exception as exc:  # noqa: BLE001 - this is a probe, report everything
            errors.append(f"student {student_index} turn {turn_index}: {exc!r}")
        finally:
            latencies.append(time.perf_counter() - started)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


async def main_async(args: argparse.Namespace) -> int:
    from backend.config import get_settings

    settings = get_settings()
    latencies: list[float] = []
    errors: list[str] = []

    print(
        f"Simulating {args.students} concurrent students x {args.turns} turns "
        f"({args.students * args.turns} inference calls)"
    )
    print(
        f"Backend: {settings.llm_backend}"
        + ("  [DRY RUN - no requests sent]" if args.dry_run else "")
    )
    if settings.llm_backend == "ollama" and not args.dry_run:
        print(
            "WARNING: Ollama is the dev/fallback backend. It is not the pilot\n"
            "         target and will not hold a full section -- see README."
        )

    started = time.perf_counter()
    await asyncio.gather(
        *(
            _one_student(i, args.turns, latencies, errors, args.dry_run)
            for i in range(args.students)
        )
    )
    wall = time.perf_counter() - started

    total = len(latencies)
    failed = len(errors)
    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    error_rate = (failed / total * 100) if total else 0.0

    print("\n--- results ---")
    print(f"wall clock         {wall:8.2f} s")
    print(f"calls              {total:8d}")
    print(f"throughput         {total / wall if wall else 0:8.2f} calls/s")
    print(f"errors             {failed:8d}  ({error_rate:.1f}%)")
    print(f"latency p50        {p50:8.2f} s")
    print(f"latency p95        {p95:8.2f} s")
    print(f"latency p99        {p99:8.2f} s")
    print(f"latency max        {max(latencies) if latencies else 0:8.2f} s")
    print(f"latency mean       {statistics.fmean(latencies) if latencies else 0:8.2f} s")

    if errors:
        print("\nfirst errors:")
        for line in errors[:10]:
            print(f"  {line}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")

    ok = True
    if error_rate > args.max_error_rate:
        print(f"\nFAIL: error rate {error_rate:.1f}% exceeds {args.max_error_rate}%")
        ok = False
    if p95 > args.max_p95:
        print(f"FAIL: p95 latency {p95:.2f}s exceeds {args.max_p95}s")
        ok = False
    if ok:
        print("\nPASS: within thresholds.")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=70,
                        help="concurrent students (default: 70, one lab section)")
    parser.add_argument("--turns", type=int, default=6,
                        help="chat turns per student (default: 6)")
    parser.add_argument("--max-p95", type=float, default=15.0,
                        help="fail if p95 latency exceeds this many seconds")
    parser.add_argument("--max-error-rate", type=float, default=2.0,
                        help="fail if the error rate exceeds this percentage")
    parser.add_argument("--dry-run", action="store_true",
                        help="exercise the harness without calling the backend")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
