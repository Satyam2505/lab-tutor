# manual/

**Updated 2026-09-12.** The manual arrived as **IACHY102** (VIT M.Tech
Engineering Chemistry Lab) — a different course code than `BACHY105`,
which the rest of this repo's docs were originally written against; see
`docs/ARCHITECTURE.md`'s manual-status note and `docs/final_audit.md`
for why that matters and what was taken on faith vs. verified.

Its text is transcribed in `IACHY102_manual.md` in this directory —
pasted in-chat as document content during a Claude Code session, not
uploaded as a PDF file. **No PDF binary has been placed here.** If the
actual PDF becomes available, drop it in as `IACHY102.pdf` and update
`LABTUTOR_MANUAL_PDF` / `infra/docker-compose.yml` accordingly — the
existing `backend/rag/retrieval.py` reads a PDF path directly via
`pypdf` and does not yet know how to ingest the markdown transcription
instead, so retrieval/citation will still return nothing until one of
those two things happens. This is a real, open gap — see
`docs/final_audit.md` §2, row 2.

`IACHY102_manual.md` is nonetheless now the source of truth for every
formula, tolerance, experiment name and worked example a Tier 1 plugin
should use — see `docs/final_audit.md` §4 for which of the 10 assessed
experiments have been implemented against it so far (one, Experiment 1)
and which are still `PendingManualPlugin` and why.
