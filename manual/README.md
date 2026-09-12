# manual/

**Put the current manual PDF here, named `IACHY102.pdf`.**

The source filename supplied for this course is
`IACHY102-2026-27-manual_2_260830_133124.pdf`; either that name or
`IACHY102.pdf` is picked up, but keep the version encoded in the
filename if you have it — see `docs/source_manifest.json`, which pins
ingestion to a specific `version` string precisely so a manual revision
produces new chunk IDs instead of silently overwriting old ones.

This directory is mounted read-only into the backend container at
`/app/manual` (see `infra/docker-compose.yml`), and `LABTUTOR_MANUAL_PDF`
points at it.

It is empty in the repository, which is why:

- every numeric experiment plugin under
  `backend/tier1_compute/experiments/` is a `PendingManualPlugin` that
  raises rather than diagnosing;
- `golden_dataset/category1_worked_examples/` has no data;
- `docs/source_manifest.json` reports `iachy102_manual_2026_27` as
  **blocked** rather than ingested (`backend/sources/manifest.py`);
- retrieval returns no passages, so phrased output carries no citation.

The manual is the source of truth for every formula, tolerance,
experiment name, numbering, screenshot and worked example in this
system — see `docs/current_state_audit.md` §0 and
`backend/sources/tiers.py` for the full source-hierarchy rule. Nothing
here was inferred, guessed, or filled in from a plausible textbook
value.

**A previous build session targeted a different, superseded course
manual (BACHY105).** That manual is declared in the source manifest as
`superseded_by: iachy102_manual_2026_27` specifically so a stray copy
left on a machine is recognised and refused rather than silently
ingested as current — do not drop a `BACHY105.pdf` here expecting it to
be used.

The PDF itself is deliberately not committed: it is course material, and
whether it may be redistributed is the department's call, not this
repository's. Add it locally and it will be picked up on the next
ingestion run — no code change is required.
