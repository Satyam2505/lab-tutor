# Phase 2 handoff

Written at the end of the Phase 1 session (2026-09-12, branch
`feat/pilot-build`). Read `docs/current_state_audit.md` first — this
document is the action list that audit's findings turn into; it does
not re-derive the reasoning already recorded there.

Item numbers below are referenced directly from code comments
(`grep -rn handoff_phase2 --include=*.py .`), so if you renumber
anything here, update those comments too.

## Before anything else: the manual

Almost every item below is either blocked by, or dramatically easier
after, one file: `manual/IACHY102-2026-27-manual_2_260830_133124.pdf`
(or `manual/IACHY102.pdf`). Neither exists in this repository or
anywhere this session could find on the machine it ran on. Drop it in
and:

- `docs/source_manifest.json`'s `iachy102_manual_2026_27` entry flips
  from blocked to ingestible with zero code changes (set `present: true`
  and confirm `version` matches what you have).
- `backend/retrieval/ingest.py` will chunk it, page by page, with full
  provenance.
- `scripts/demo_exp7.py` and the golden QA dataset
  (`golden_dataset/qa/`) will start showing real
  `IN_SCOPE_SUPPORTED` answers instead of
  `IN_SCOPE_RETRIEVAL_INSUFFICIENT` — re-run both to see exactly which
  questions the manual actually resolves, which is a better coverage
  signal than anything hand-written.

## Item 1 — Move exp07/exp08's diagnosis-tier identity to match reality

**What's wrong.** `backend/tier1_compute/experiments/exp07.py` runs the
ethane staggered/eclipsed ordering check under the `exp07` id.
Per the brief and `backend/scope/ontology.py` (built this phase from the
same brief), **experiment 7 is the molecular-orbital workflow**
(Gabedit/ORCA/Avogadro, methane, HOMO/LUMO) and **experiment 8 covers
both ethane and cyclohexane conformers**. `exp08.py` already has the
right id for cyclohexane; ethane's ordering pairs need to move there
too, and `exp07.py` needs to become something else (see below).

**Why it wasn't done this phase.** The swap touches real behaviour in
four test files with DB fixtures, not just a docstring:

| File | What references the wrong identity |
| --- | --- |
| `backend/tests/test_pipeline_and_tiers.py` | `get_plugin("exp07")` checks with `ethane_staggered`/`ethane_eclipsed` energies; an assertion that `qualitative == ["exp07", "exp08"]` |
| `backend/tests/test_phrasing_injection.py` | `ALLOWED_EXPERIMENTS == {"exp07", "exp08"}`; `qualitative_note(experiment_id="exp07", ...)` calls expecting success |
| `backend/tests/test_data_isolation.py` | A classroom fixture with `experiment_id="exp07"` and ethane energies |
| `backend/tests/test_single_fire_and_summaries.py` | ~10 references to `experiment_id="exp07"` with ethane energies, across submission/summary/trajectory fixtures |

**The exact fix:**

1. In `exp08.py`, add ethane's `ORDERINGS` pairs
   (`("ethane_staggered", "ethane_eclipsed")`) alongside the existing
   cyclohexane pairs, and merge the `STEPS` from `exp07.py`'s geometry
   setup / energies steps into `exp08.py`'s (both experiments ask for
   the same two-step shape: build geometries, report energies). One
   `QualitativeOrderingPlugin` registration, one title
   ("Conformational analysis: ethane and cyclohexane").
2. Replace `exp07.py`'s registration with a `PendingManualPlugin` (same
   pattern as `exp01.py`/`exp04.py`/etc.), titled from
   `backend.scope.ontology.get_topic("exp07").title`, pending manual
   transcription of whatever Tier 1 *can* deterministically check for
   the orbital workflow (if anything — it may turn out to be entirely
   procedural/qualitative once you can read the manual's actual
   assessment criteria; don't assume it needs `QualitativeOrderingPlugin`
   just because exp08 does).
3. In `backend/rag/qualitative.py`, change `ALLOWED_EXPERIMENTS` to
   `frozenset({"exp08"})` and update its docstring — the CLAUDE.md
   exception was written for "experiments 7 and 8" under the old
   identity; under the corrected one, both orderings live in one
   experiment, so the exception now covers *one* registered plugin, not
   two. This is a tightening, not a loosening, but say so explicitly
   wherever CLAUDE.md's amended paragraph is referenced, since its own
   prose still says "Experiments 7 and 8."
4. Update the four test files above: change `experiment_id="exp07"` to
   `"exp08"` everywhere the fixture is exercising the ethane ordering
   check, change the `ALLOWED_EXPERIMENTS` assertion, and change the
   `qualitative_note(experiment_id="exp07", ...)` calls in
   `test_phrasing_injection.py` to `"exp08"` (or add a new assertion that
   `"exp07"` now correctly *raises* `ValueError` from
   `qualitative_note`, if you want to keep coverage on the restriction
   itself).
5. Run the full suite. Expect roughly a dozen assertions to need the
   `exp07`→`exp08` string swap and nothing else — the underlying
   ordering-check logic does not change.
6. Update `backend/scope/ontology.py`'s module docstring, which
   currently explains this exact conflict at length — once fixed, that
   explanation becomes historical noise and should shrink to a one-line
   note plus a pointer to the git history.

**Do not do this under time pressure without running the full suite
between each file.** The four files are independent test modules; there
is no reason to batch the edits blind.

## Item 2 — Populate the remaining six experiments' ontology

`backend/scope/ontology.py` deliberately leaves `exp01`, `exp04`,
`exp05`, `exp06`, `exp09`, `exp10` with `status=UNKNOWN_PENDING_MANUAL`
and no routing vocabulary, because nothing available this phase
established what they cover. Once the manual is in hand:

1. For each, add a `strong_terms`/`weak_terms`/`software` set the same
   way `exp02`/`exp03`/`exp07`/`exp08` are populated, sourced from the
   manual's actual section headers and terminology — not guessed.
2. Change `status=TopicStatus.KNOWN_FROM_BRIEF` to a new
   `KNOWN_FROM_MANUAL` value (add it to `TopicStatus`) so provenance
   stays honest — these six were never in the brief's topic lists, so
   reusing that status name would misattribute the source.
3. Re-run `golden_dataset/qa/generate_qa.py` — `build_priority_cases`
   already works for any topic with populated vocabulary; move these six
   from `build_unknown_experiment_cases` to the priority path (with a
   smaller `target`, per the brief's P1 baseline) once vocabulary exists.
4. This should take under an hour per experiment once you can read the
   relevant manual section.

## Item 3 — Wire up real page images

`backend/retrieval/images.py` is a complete, tested interface with no
implementation behind it in this environment (no `PyMuPDF`/`fitz`
installed; see `backend/requirements.txt`'s commented-out `pymupdf`
line). Once the manual PDF exists:

1. `pip install pymupdf==1.25.1` (or update the pin if a newer stable
   release exists by then) and uncomment it in `requirements.txt`.
2. Call `ingest_document(entry, image_output_dir=<some static-served
   directory>)` instead of the default `None` — every `Chunk` will then
   carry a real `PageImageRef` with `available=True` and an `asset_path`.
3. Decide where rendered images are actually served from (a static
   directory the FastAPI app mounts, or an object store) and wire
   `PageImageRef.asset_path` into whatever URL scheme the frontend needs.
4. `backend/retrieval/rerank.py`'s visual-query boost already uses
   `chunk.visual_available` — no reranking logic needs to change, only
   the fact that `visual_available` starts being `True` for real.
5. Extend `golden_dataset/qa/coverage_report.py` (see its own docstring)
   to report page/section coverage the way the brief's section 10
   actually asks, once `Chunk.page`/`Chunk.section` carry real manual
   data instead of only the adjacent-knowledge directory's synthetic
   page numbers.

## Item 4 — A real embedding provider for the "semantic" retrieval layer

`backend/retrieval/index.py`'s `_TfidfCosine` is a local, dependency-free
stand-in for the "semantic" half of hybrid retrieval — see its docstring
for why that was the right call for Phase 1 (no API key, no network hop,
consistent with the existing `backend/rag/retrieval.py`'s own reasoning
for the same corpus). If evaluation against the real manual shows
paraphrased questions still under-perform:

1. Add an `EmbeddingBackend` protocol next to `backend/llm/client.py`'s
   `LLMBackend` (same swappable-backend pattern), backed by whatever
   provider the hosted LLM backend's account already has embeddings
   access to.
2. Swap `_TfidfCosine` for a class implementing the same `.score(index,
   query_terms)` shape, or change `HybridIndex` to accept a `semantic`
   parameter defaulting to `_TfidfCosine()` — no other module imports
   `_TfidfCosine` directly, so this is contained to `index.py`.
3. Re-run `backend/tests/test_retrieval_index.py` and the golden QA
   replay (`test_golden_qa_dataset.py`) — both are written against the
   `HybridIndex` public interface, not its internals, so they should
   need no changes.

## Item 5 — The chat frontend

This phase built the backend pipeline end to end
(`backend/retrieval/pipeline.py::answer_question`) and proved it with a
CLI script (`scripts/demo_exp7.py`), but did not build the student-facing
chat UI the brief's demo section describes (multi-turn conversation,
screenshot display, visible scope/citation labelling). `frontend/` today
is built for the submission-review product (`app/student/page.tsx`,
`app/faculty/`), not a chat surface. To add one:

1. A new FastAPI route, e.g. `backend/api/qa_routes.py`, exposing
   `answer_question` behind the existing auth dependencies
   (`backend/auth/dependencies.py`) — follow the pattern in
   `backend/api/socratic_routes.py` for session/classroom resolution,
   but note the Q&A product doesn't need submission data at all, so it
   likely needs a lighter dependency than the diagnostic routes.
2. A new `frontend/app/student/ask/` (or similar) page: a message list,
   an input box, and — this is the part worth getting right — visible
   rendering of `AnswerResult.supplementary` (a clearly different visual
   treatment from a manual-grounded answer) and `AnswerResult.citations`
   (page/section, and once Item 3 lands, the actual page image).
3. Session/experiment context (`active_experiment` in
   `answer_question`) should come from the same "active experiment for
   this classroom" resolution `backend/classrooms/service.py` already
   provides for Socratic mode — don't build a second mechanism for it.

## Smaller items

- **CLAUDE.md, README.md, ARCHITECTURE.md still say BACHY105 in prose.**
  This phase deliberately left these three alone (see the commit that
  did the BACHY105→IACHY102 rename) because they are governance/
  reference documents the repository owner should revise on purpose, not
  documents a session should silently rewrite. The code, config, env
  template, and manual-mount instructions were renamed; these three
  weren't. Worth a deliberate pass once the manual situation is settled
  for good.
- **`golden_dataset/qa/coverage_report.py` reports `ni2+`/`ni(ii)` as
  uncovered for exp03** even though "ni2" (without the punctuation) is
  well covered — a word-boundary regex artifact in `_term_hit`, not a
  real gap. Low priority; fix by normalising punctuation before the
  `\b...\b` match if it starts bothering you.
- **`backend/rag/retrieval.py` (the old BM25-only module) is still used
  by the diagnosis pipeline** (`backend/rag/phrasing.py`,
  `backend/rag/qualitative.py`). It was deliberately left alone this
  phase — see `backend/retrieval/__init__.py`'s docstring for why
  duplicating its simpler, single-document design into the new
  multi-tier `backend/retrieval/` package would have been the wrong
  direction. If the diagnosis pipeline ever needs multi-tier citations
  too, that's the point to reconsider, not before.
- **The adjacent-knowledge corpus (`knowledge/adjacent/`) is five files
  covering the four priority experiments.** The brief's own examples
  extend further (general kinetics beyond what's written, more DFT
  background, etc.) — treat the current set as a working proof of the
  mechanism, not as complete. Adding a file is genuinely just adding a
  file: `expNN_topic.md` in that directory, ingested automatically on
  the next run with correct attribution (see
  `backend/retrieval/ingest.py::_filename_experiment_hint`).
- **No rate limiting or auth is wired to the Q&A pipeline yet**, because
  there is no route for it yet (Item 5). Whatever route gets built must
  go through the existing `backend/ratelimit.py` and
  `backend/auth/dependencies.py` the same way every other endpoint does
  — this is a "don't forget," not a design question.
