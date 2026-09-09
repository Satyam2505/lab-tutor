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

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import IdempotencyRecord


class DuplicateInFlight(RuntimeError):
    """The same action is already running. The caller should not retry it."""


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
        if winner is not None and winner.status == "done":
            return Claim(record=winner, fresh=False, replayed_response=winner.response)
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
