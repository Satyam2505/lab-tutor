# Current state audit — Phase 1 forensics

Date: 2026-09-12. Branch: `feat/pilot-build` (23 commits, clean tree).
Audited against the current source-of-truth manual, **IACHY102**
(`IACHY102-2026-27-manual_2_260830_133124.pdf`).

This document reconciles what the repository actually contains against
what the current phase requires. It is deliberately blunt about what is
stale, because the previous two sessions built against a different
manual and a partly different product.

---

## 0. The finding that governs everything else

**No IACHY102 manual exists in this repository or anywhere on this
machine.** Neither does any of the supplementary material the phase
brief refers to.

Searched: the repository (tracked and untracked), `manual/`,
`~/OneDrive/Desktop`, `~/Downloads`, `~/OneDrive/Documents`. Searched
for `*IACHY*`, `*BACHY*`, `*manual*`, and for every `.pdf`, `.ipynb`,
`.docx`, `.png`, `.jpg` in the tree.

Result: zero matches. `manual/` contains only a `README.md` explaining
that the PDF is deliberately not committed (it is course material, and
redistribution is the department's call — see `.gitignore`, which
ignores `manual/*.pdf`).

The following Phase 1 deliverables are therefore **blocked on a file**,
not on engineering:

| Blocked deliverable | Why |
| --- | --- |
| Exact formulas for Exp 2 and every numeric experiment | Brief §4: "Do NOT invent equations. Extract exact formulas from the manual." |
| Page images / screenshot assets | There are no pages to rasterise. |
| Real page numbers in citations | Fabricating them is explicitly forbidden (brief §13). |
| `expected_answer_facts` in golden cases | Would be invented chemistry presented as ground truth. |
| Per-screenshot coverage report for Exp 7 | Requires knowing which screenshots exist. |
| Confirmed experiment titles and numbering for all 10 | Only the manual establishes these. |

Everything else in the brief is architecture, and architecture does not
need the PDF to be built or tested. That is what this phase delivers —
see §7 and `docs/handoff_phase2.md`.

**The single highest-value action available to the next person is to
drop the PDF into `manual/IACHY102.pdf`.** The ingestion pipeline built
this phase reads it on the next run with no code change.

---

## 1. What already works

Verified by running the suite: **658 passed, 3 skipped**, on Python
3.12.10 against SQLite (`python -m pytest -q`).

| Area | State | Notes |
| --- | --- | --- |
| Auth (`backend/auth/`) | Works | Server-side role resolution from OAuth domain, re-checked per request. Matches the security non-negotiables. |
| Data isolation (`backend/data_access.py`) | Works | Every query scoped to the caller; `tests/test_data_isolation.py` covers cross-student access. |
| Answer gate (`backend/answer_gate/`) | Works, and is good | Structurally prevents the answer entering a Socratic prompt — a `frozen`+`slots` dataclass with no answer field, asserted at startup — plus numeric scrubbing of outbound hints. Preserve as-is. |
| Deterministic triage (`backend/socratic_engine/triage.py`) | Works | Safety-incident / safety-question / distress short-circuits that run before any model call. Precision-biased, well tested. Keep. |
| Shared Tier 1 checkers (`backend/tier1_compute/shared/`) | Works | Four checker types (direct formula, calibration curve, endpoint detection, regression slope) with signature detection. |
| Tiers 2–3, escalation, audit, idempotency, rate limiting | Works | Structurally complete. |
| Deployment (`infra/`) | Works | Compose stack, Caddy, two Dockerfiles, CI. |
| Frontend (`frontend/`) | Minimal but real | Next.js app router, student and faculty views. |

The engineering quality of what exists is high. The previous sessions
refused to fabricate chemistry and said so loudly in code. That
judgement was correct, and this phase preserves it.

## 2. What partially works

| Area | Gap |
| --- | --- |
| `backend/rag/retrieval.py` | A single BM25 index over whole-page text chunks. No metadata, no experiment filtering, no reranking, no page images, no source tiers, no provenance beyond a page integer. Roughly step 3 of the nine-step pipeline brief §6 asks for. |
| `backend/rag/phrasing.py` | Injection-resistant delimiting is correct, but it phrases an already-computed diagnosis. There is no question-answering path at all. |
| Frontend | No chat surface for the Q&A product. Built for submission review, not for a student typing "orca input kaha se banau". |
| Golden dataset | Five populated categories, all testing *diagnosis* (deviations, edge inputs, injection, probing). Category 6 holds ~180 realistic student questions — genuinely reusable raw material — but with no scope levels, no experiment routing labels, and no citation expectations. |

## 3. What is broken or stale relative to IACHY102

Concrete conflicts, not stylistic preferences.

1. **`exp07.py` models the wrong experiment.** It implements ethane
   staggered-vs-eclipsed conformers as Experiment 7. Under IACHY102,
   conformational analysis (ethane staggered/eclipsed, cyclohexane
   chair/boat) is **Experiment 8**, and **Experiment 7** is the
   molecular-orbital workflow (Gabedit / ORCA 5.0.4 / Avogadro, methane
   and O2, optimisation, HOMO/LUMO, orbital contributions). The file's
   own `TODO` anticipated exactly this ("confirm that experiment 7 … is
   in fact the ethane conformer calculation"). It is not.
2. **Every user-visible string says BACHY105.** `Passage.citation()`
   hardcodes `"BACHY105 manual, p. {page}"`, `config.manual_pdf`
   defaults to `manual/BACHY105.pdf`, and several module docstrings plus
   `manual/README.md` name the old course. A citation naming the wrong
   document is worse than no citation.
3. **Experiment titles are placeholders.** Nine of ten read "Experiment
   N (title pending manual transcription)". Under the new brief they
   must at minimum route correctly, which requires an ontology — built
   this phase from the brief's own descriptions, and explicitly marked
   as routing vocabulary rather than manual content.
4. **The product model has moved.** The repo is built as a *grading and
   diagnosis* system (Socratic step verification plus post-submission
   diagnosis). The current brief describes a *retrieval-grounded
   learning assistant* as the primary product. Complementary, not
   contradictory — but the second one barely exists in the code, and it
   is what the Exp 7 demo needs.
5. **No scope model whatsoever.** `triage.py` has an `OFF_SCOPE` intent,
   but it collapses exactly the distinction brief §12 calls
   non-negotiable: "not found in retrieval" and "out of scope" are the
   same outcome today. This is the single largest architectural gap, and
   it is what this phase fixes first.

## 4. What conflicts with the source hierarchy

The brief defines Tier A (official manual) > Tier B (supplied
scripts/notebooks) > Tier C (curated supplementary) > Tier D (model
knowledge). The repository currently has **no concept of a source
tier**: `retrieval.py` returns passages from one document and the
phrasing layer treats them all identically.

There is also a latent Tier D exposure: `backend/rag/qualitative.py`
lets a model read a student's method narrative for Exp 7/8. It is
tightly contained (low-confidence, escalation-biased, never a pass) and
CLAUDE.md documents the exception — but its containment argument was
written for an experiment that, per §3.1, was misidentified. Re-examine
it against the real Exp 7 once the manual is in.

## 5. What can be reused as-is

- The whole answer-gate package. Do not rewrite it.
- `triage.py` — safety short-circuits apply to the Q&A product too, and
  the new scope classifier defers to it rather than duplicating it.
- The four shared Tier 1 checker types and signature detection.
- Auth, data access, audit, idempotency, rate limiting.
- `sanitise_student_text()` from `phrasing.py` for injection isolation.
- Category 6 student questions, as raw phrasing material.
- The `PendingManualPlugin` pattern — raising loudly beats guessing. The
  new retrieval layer takes the same stance.

## 6. What must be rewritten

- `backend/rag/retrieval.py` → superseded by `backend/retrieval/`
  (hybrid, metadata-filtered, reranked, provenance-carrying). The old
  module stays as a shim so the diagnosis path keeps working.
- `exp07.py` / `exp08.py` experiment identity.
- Every `BACHY105` string.
- `golden_dataset/` gains a parallel QA dataset using the brief's
  schema; the existing diagnosis categories stay where they are.

## 7. Current test and demo status

**Tests:** 658 passed, 3 skipped before this phase's work. The suite
needs no services (SQLite, no network, no LLM).

**Demo:** there is no runnable end-to-end demo, for the Q&A product or
for any experiment. `frontend/` renders and the API answers, but no path
exists from "student types a messy Exp 7 question" to "grounded answer
with a citation". Building that path is Phase 1's headline deliverable,
and it is the part most damaged by the missing PDF: the pipeline can be
demonstrated end to end against a fixture corpus, but it cannot yet
quote the real manual.

## 8. What remains for Phase 2

Tracked in `docs/handoff_phase2.md`. In short: everything needing the
PDF (real ingestion, real formulas, real citations, real
`expected_answer_facts`, screenshot coverage), plus the chat frontend
and the multi-turn context layer.
