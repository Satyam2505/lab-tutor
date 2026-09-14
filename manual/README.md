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

## Text transcription

The manual's text is transcribed in `IACHY102_manual.md` in this
directory. It was pasted in as document content, not uploaded as a PDF,
so **no PDF binary has been placed here.** Retrieval reads the PDF path
and does not ingest the markdown transcription, so until the PDF is added:

- `docs/source_manifest.json` reports `iachy102_manual_2026_27` as
  **blocked** rather than ingested (`backend/sources/manifest.py`);
- retrieval returns no manual passages, so phrased output carries no
  manual citation.

`IACHY102_manual.md` is nonetheless the source of truth for every
formula, tolerance, experiment name and worked example a Tier 1 plugin
uses. `docs/final_audit.md` §4 lists which of the 10 assessed experiments
are implemented against it so far (Experiment 1, plus the Experiment 8
ordering check) and which are still `PendingManualPlugin` and why.

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
