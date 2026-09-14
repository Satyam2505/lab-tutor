# manual/

**Updated 2026-09-12.** The manual arrived as **IACHY102** (VIT M.Tech
Engineering Chemistry Lab) — a different course code than `BACHY105`,
which the rest of this repo's docs were originally written against; see
`docs/ARCHITECTURE.md`'s manual-status note and `docs/final_audit.md`
for why that matters and what was taken on faith vs. verified.

Its text is transcribed in `IACHY102_manual.md` in this directory —
pasted in-chat as document content during a Claude Code session, not
uploaded as a PDF file. **No PDF binary has been placed here.**

**Update (2026-09-14): retrieval is fixed.** `backend/rag/retrieval.py`
now dispatches on file extension — a `.md` path (this file) is chunked
by its `## Experiment N ... (p.X-Y)` headings via `_chunk_markdown`
rather than pushed through `pypdf`. `LABTUTOR_MANUAL_PDF` defaults here
already. If a real PDF ever becomes available, dropping it in as
`IACHY102.pdf` and repointing the setting still works too (the old PDF
path through `pypdf` is untouched) — it's no longer required, just an
option. See `docs/final_audit.md` §7 for what was verified live (19
passages indexed; correct top-ranked section for both an Exp7 Hinglish
query and an Exp2 kinetics query).

`IACHY102_manual.md` is the source of truth for every formula,
tolerance, experiment name and worked example a Tier 1 plugin should
use — see `docs/final_audit.md` §4 for which of the 10 assessed
experiments have real plugins so far (1, 2, 3, 7, 8) and which are still
`PendingManualPlugin` and why (4, 5, 6, 9, 10).
