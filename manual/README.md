# manual/

**Put the BACHY105 manual PDF here, named `BACHY105.pdf`.**

This directory is mounted read-only into the backend container at
`/app/manual` (see `infra/docker-compose.yml`), and `LABTUTOR_MANUAL_PDF`
points at it.

It is empty in the repository, which is why:

- every numeric experiment plugin under
  `backend/tier1_compute/experiments/` is a `PendingManualPlugin` that
  raises rather than diagnosing;
- `golden_dataset/category1_worked_examples/` has no data;
- retrieval returns no passages, so phrased output carries no citation.

The manual is the source of truth for every formula, tolerance,
experiment name and worked example in this system. Nothing here was
inferred, guessed, or filled in from a plausible textbook value — see
`README.md` → "What the manual unblocks".

The PDF itself is deliberately not committed: it is course material, and
whether it may be redistributed is the department's call, not this
repository's. Add it locally and it will be picked up on the next backend
start.
