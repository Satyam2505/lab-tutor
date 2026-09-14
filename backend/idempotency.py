"""Server-side single-fire enforcement.

Disabling a button on click is necessary but not sufficient: a network
retry, a refresh, or a second browser tab can still deliver the same
action twice. Every state-changing or LLM-calling endpoint therefore
claims an idempotency key here first.

The claim is a unique-constraint insert, so two concurrent requests race
at the database and exactly one wins. The loser either waits (the first
is still in flight) or replays the stored response (the first finished) --
it never performs the action a second time, which is what keeps duplicate
rows, duplicate inference calls and duplicate billing from happening.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import IdempotencyRecord

#: How long an `in_flight` claim is honoured before it's treated as
#: abandoned rather than genuinely still running. Found this session
#: (Explore-agent sweep): `release()` is only called from a handful of
#: routes' explicit error branches, not from every route, and none of
#: them use a `finally`. A request that crashes between `claim()` and
#: `complete()`/`release()` -- an unhandled exception, a killed worker,
#: an LLM call that hangs past its own timeout in a way that doesn't
#: raise cleanly -- leaves that exact `(user, scope, key)` claim wedged
#: `in_flight` forever, since the key is deterministic
#: (`derive_key`) for a `submit`-style action: the student could never
#: resubmit that exact data again without a manual DB fix. Real requests
#: finish in low single-digit seconds even under load; anything still
#: `in_flight` past this window is being treated as a crash, not slowness.
STALE_IN_FLIGHT_SECONDS = 300


class DuplicateInFlight(RuntimeError):
    """The same action is already running. The caller should not retry it."""


def _is_stale(record: IdempotencyRecord) -> bool:
    created_at = record.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=dt.timezone.utc)
    age = dt.datetime.now(dt.timezone.utc) - created_at
    return age > dt.timedelta(seconds=STALE_IN_FLIGHT_SECONDS)


@dataclass
class Claim:
    record: IdempotencyRecord
    fresh: bool
    replayed_response: dict[str, Any] | None = None


def derive_key(*parts: Any) -> str:
    """A stable key from the action's identifying parts.

    Used when the client sends no key of its own, so a double-click still
    collapses to one action.
    """
    blob = json.dumps([str(p) for p in parts], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:64]


async def claim(
    db: AsyncSession, *, user_id: str, scope: str, key: str
) -> Claim:
    """Claim the right to perform an action once.

    Returns a fresh claim to the winner. For a duplicate, returns the
    stored response if the original finished, or raises
    `DuplicateInFlight` if it has not.
    """
    existing = (
        await db.scalars(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key == key,
            )
        )
    ).first()

    if existing is not None:
        if existing.status == "done":
            return Claim(record=existing, fresh=False, replayed_response=existing.response)
        if _is_stale(existing):
            # Abandoned, not in progress -- reclaim it rather than
            # wedging this (user, scope, key) forever. See
            # STALE_IN_FLIGHT_SECONDS.
            await db.delete(existing)
            await db.flush()
        else:
            raise DuplicateInFlight(
                f"An identical '{scope}' action is already in progress"
            )

    record = IdempotencyRecord(user_id=user_id, scope=scope, key=key, status="in_flight")
    db.add(record)
    try:
        await db.flush()
    except IntegrityError:
        # Lost the race. Re-read to see what the winner did.
        await db.rollback()
        winner = (
            await db.scalars(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user_id,
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.key == key,
                )
            )
        ).first()
        if winner is not None:
            if winner.status == "done":
                return Claim(record=winner, fresh=False, replayed_response=winner.response)
            if not _is_stale(winner):
                raise DuplicateInFlight(
                    f"An identical '{scope}' action is already in progress"
                ) from None
            # The record we lost to is itself stale -- reclaim it. Rare
            # (two requests racing to reclaim the same abandoned key at
            # the same instant) but handled rather than left to raise.
            await db.delete(winner)
            await db.flush()
            record = IdempotencyRecord(
                user_id=user_id, scope=scope, key=key, status="in_flight"
            )
            db.add(record)
            await db.flush()
        else:
            raise DuplicateInFlight(
                f"An identical '{scope}' action is already in progress"
            ) from None

    return Claim(record=record, fresh=True)


async def complete(
    db: AsyncSession, claim_obj: Claim, response: dict[str, Any] | None = None
) -> None:
    """Mark a claimed action finished and store its response for replay."""
    claim_obj.record.status = "done"
    claim_obj.record.response = response
    await db.flush()


async def release(db: AsyncSession, claim_obj: Claim) -> None:
    """Drop a claim whose action failed, so the user can genuinely retry."""
    if claim_obj.fresh:
        await db.delete(claim_obj.record)
        await db.flush()
