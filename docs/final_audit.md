# Final audit — LabTutor vs the Phase 2 build/audit/hardening request

Date: 2026-09-12. Scope note up front, because it governs every verdict
below: **the Phase 2 request describes a different, much larger product
than what exists in this repository**, and this audit says so rather
than inventing evidence to close the gap. See "Architecture mismatch"
before reading the checklist.

## 0. Architecture mismatch (read this first)

The Phase 2 request assumes an already-built system with: a vector
database, an embeddings/chunking/reranking pipeline, image-aware
(multimodal) page retrieval, a three-level scope classifier, an adjacent-
knowledge layer, a 70-concurrent-user load-test harness, an automated
LLM-based evaluation suite hitting a real model, and 550–750 golden QA
cases across 10 experiments. It refers to a prior "Antigravity" build,
`docs/current_state_audit.md`, and `docs/handoff_phase2.md`.

None of that exists in this repository, and none of those files exist.
What exists (`git log`, all first-party commits) is **LabTutor**: a
Socratic/Diagnostic chemistry-lab tutor built around a *deterministic*
Tier 1 compute layer (`backend/tier1_compute/`) with a thin,
non-vector, TF-IDF-style text retrieval module (`backend/rag/
retrieval.py`) whose only job is to hand a citation to an LLM
*phrasing* layer — never to decide correctness. This is a coherent,
well-tested, much smaller system than the one the request describes.

The request also names a manual (`IACHY102-2026-27-manual_2_260830_
133124.pdf`) that turned out to be for a *different course* than the one
CLAUDE.md and every doc in this repo were written against — the repo
says **BACHY105** (a B.Tech applied-chemistry lab); the manual's own
title page says **IACHY102**, "FOR FIRST/SECOND SEMESTER M.TECH." Since
these may be different VIT course offerings entirely, and nothing in
the manual text says this LabTutor deployment is for the M.Tech course,
that identification was taken on the user's instruction in this
session, not independently verified. If it's wrong, everything below
that treats IACHY102 as authoritative needs re-checking against the
right manual.

Given this, the audit below is honest about **what this repository
actually is** against the request's checklist, not a fabricated status
report pretending the assumed architecture is present.

## 1. What was audited

- Full git history (`git log --oneline`, all 17 commits) and working
  tree (`git status` — clean before this session's changes).
- Every doc: `README.md`, `CLAUDE.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`,
  `docs/golden_dataset_plan.md`. `docs/current_state_audit.md` and
  `docs/handoff_phase2.md`, named by the request, do not exist.
- `backend/` in full: `tier1_compute/` (shared checkers + all 10
  experiment plugins + registry), `rag/` (retrieval, phrasing,
  templates, qualitative), `socratic_engine/`, `answer_gate/`,
  `tier2_exceptions/`, `tier3_escalation/`, `auth/`, `classrooms/`,
  `api/`, `dashboard_api/`, `summaries/`, `extraction/`, `models.py`,
  `pipeline.py`, `db.py`, `config.py`, `data_access.py`, `idempotency.py`,
  `ratelimit.py`, `audit.py`.
- `frontend/` (Next.js app: student, faculty, faculty/[classroomId] pages).
- `golden_dataset/` (6 categories + generator) and `backend/tests/`
  (18 test files, 663 test cases before this session's edits).
- `infra/` (Docker Compose, Caddyfile, `loadtest.py`).
- The three files the user added to the working tree this session
  (`BTech_Lab_V5_09072025.docx`, `ML_lab_manual_08.07.25.docx`,
  `script_stu.ipynb`) — noted as Tier B (course-supplied scripts/
  notebooks per the request's source hierarchy) but **not opened or
  transcribed in this pass**; they are `.docx`/`.ipynb`, not text tools
  read directly, and reading them was out of scope for this turn.
- The manual content, pasted in-chat as the IACHY102 PDF's extracted
  text (51 pages), now transcribed to `manual/IACHY102_manual.md`.
- Ran the full backend test suite after every code change
  (`python3 -m pytest backend/tests`): 663 passed, 1 skipped (a
  pre-existing, unrelated skip), 0 failed, at the end of this session.

## 2. Per-request-section verdict

| # | Request section | Verdict | Notes |
|---|---|---|---|
| 1 | Tier 1 diagnosis never delegated to an LLM | **PASS** | Structurally enforced: `tier1_compute` has no LLM import anywhere (`backend/rag/qualitative.py` is the one documented, contained exception, and even it never resolves a verdict — see below). Confirmed by reading, not just by the doc's claim. |
| 2 | Full audit of ingestion/chunking/embeddings/vector DB/reranking/metadata filtering/scope classifier | **NOT IMPLEMENTED** | There is no embeddings pipeline, no vector DB, no reranker, no metadata filter, no scope classifier of any kind. `retrieval.py` is ~170 lines: extract PDF text with `pypdf`, chunk on blank lines, TF-IDF cosine-ish scoring, top-k. This is a legitimate, working, *much smaller* thing — it is not the system §2 assumes exists to be audited for correctness. |
| 3 | Do not preserve bad architecture (reject retrieval-only scope detection, giant prompts, hallucinated citations, etc.) | **N/A / mostly moot** | The listed anti-patterns mostly presuppose the RAG system in §2. What *is* present and worth checking: `backend/rag/phrasing.py` isolates student text with delimiters and never lets a model's reply override a pre-computed verdict (`answer_gate/gate.py` enforces this — see row 22). No evidence of giant whole-manual prompts (only top-k passages, capped, are ever concatenated into a prompt — see `qualitative.py`'s 1200-char cap). |
| 4 / 4A | All 10 experiments implemented/routable/searchable/cited/scope-aware/tested | **PARTIAL — see per-experiment table below** | 1 of 10 experiments (Exp 1) has a real Tier 1 plugin with a manual-verified worked-example regression test, added this session. The other 9 are honestly `PendingManualPlugin` (raise rather than guess), now with reasons that state *why* (formula-shape known, no worked example vs. genuinely more analysis needed) instead of the stale "manual not present." None of the 10 have RAG-style "routing," a scope classifier, or citation validation in the sense §6/§18 describe, because that layer does not exist (see row 2). |
| 5 | Source hierarchy (Tier A/B/C/D) enforced | **NOT IMPLEMENTED** | No tiering exists. Retrieval has exactly one source (the manual index) and no adjacent-knowledge or general-model-knowledge layer to rank against it. |
| 6 | Three-level scope classification (IN_SCOPE/ADJACENT/OUT_OF_SCOPE × supported/insufficient/human-review) | **NOT IMPLEMENTED** | No scope classifier exists at all — not a bad one, none. Retrieval returning zero passages is not used as an out-of-scope signal anywhere in this codebase (there is no such branch to check), so the specific bug pattern §6 warns against doesn't currently exist either, for the same reason: the whole mechanism is absent. |
| 7 | Adjacent knowledge layer (`knowledge/adjacent/`, policy doc) | **NOT IMPLEMENTED** | Directory does not exist. Not created this session — building a real, curated adjacent-knowledge dataset with correct scope/confidence/citation metadata per topic is substantive content work, not a mechanical fix, and doing it quickly risks exactly the "plausible-sounding invented content" CLAUDE.md forbids. |
| 8–9 | Experiment 7 flagship demo, image-aware page retrieval, 150–200+ golden cases | **NOT IMPLEMENTED** | Experiment 7 in the *real* manual (p.39–42) is a Gabedit→ORCA→Avogadro orbital-contribution workflow (CH4, O2), not the ethane-conformer check the pre-existing code had registered under that id. That mismatch is fixed this session (see §3 below) but the experiment itself has zero Tier 1 checker, zero golden cases, and no image/page retrieval of any kind — there is no image handling anywhere in the codebase to begin with (`retrieval.py` extracts text only). |
| 10–13 | Experiment 8/2/3, remaining six, full golden distribution (~550–750 cases) | **NOT IMPLEMENTED at the volume requested** | Golden dataset currently has 6 categories per `docs/golden_dataset_plan.md`, populated for categories 2–6 with synthetic/structural cases (not manual-numbers-dependent) plus one new Category 1 case (Exp 1). Total case count is nowhere near 550–750, and the 9 experiments without a Tier 1 plugin cannot get calculation-grounded golden cases yet without inventing numbers. |
| 14–19 | Golden test schema, automated evaluator, RAG/retrieval evaluation, citation validation, image-aware RAG tests | **NOT IMPLEMENTED** | No evaluator producing `reports/latest_evaluation.json` exists; building a real one requires the scope classifier and retrieval system from rows 2/6/7, none of which exist yet. |
| 20 | 70/50/25/10-user load test | **NOT EXECUTED** | `infra/loadtest.py` exists (pre-dates this session) and is a real, runnable Locust-style script per `docs/ARCHITECTURE.md`, but no load test was run in this session — no backend server was started against a live Postgres, and running one was out of scope for an audit-and-fix pass with no confirmed deployment target. Marking this NOT EXECUTED rather than claiming a result, per the request's own §32/§34 rule. |
| 21 | Bounded LLM concurrency, caching, timeouts, retries, rate limiting, circuit breaker | **PARTIAL** | `backend/ratelimit.py` and `backend/idempotency.py` exist and are tested (`test_single_fire_and_summaries.py`). `backend/llm/client.py` was not re-audited line-by-line this session for retry/backoff/circuit-breaker behavior specifically — flagging as unverified rather than PASS. |
| 22 | Answer gate / safety | **PASS** | `backend/answer_gate/gate.py` + `test_answer_gate.py` exist and were exercised by the full suite this session (663 passed). Both diagnostic and Socratic output are routed through it per `git log` (`c141d6a Route diagnostic output through the answer gate too`). |
| 23 | Prompt injection resistance | **PARTIAL** | `golden_dataset/category4_prompt_injection/` and `backend/tests/test_phrasing_injection.py` exist and pass. Coverage is against the existing (small) RAG/phrasing surface, not against a scope-policy/source-hierarchy layer that doesn't exist yet. |
| 24 | Data isolation / server-side authz | **PASS (re-verified)** | `backend/tests/test_data_isolation.py` exists and passes; this session ran it after editing it (one `exp07`→`exp08` fix, unrelated to the isolation logic itself) and it still passes. |
| 25–26 | Frontend demo quality, demo runbook | **NOT VERIFIED / NOT IMPLEMENTED** | Frontend was not started or exercised in a browser this session (no UI changes were made, so this was not re-verified). `docs/demo_runbook.md` does not exist. |
| 27–28 | Observability, error handling | **PARTIAL** | `backend/audit.py` exists; not re-audited line-by-line against the request's specific field list (request ID, retrieval latency, etc.) this session. |
| 29–33 | Per-experiment table, quality gates, final regression, deliverables checklist | **See §3 below and the acceptance-gate summary at the end.** | |

## 3. Concrete fixes made this session

1. **`manual/IACHY102_manual.md`** — the manual's text (pasted in-chat)
   transcribed into the repo as the new source of truth, with page
   numbers preserved for citation, every formula transcribed verbatim,
   and every worked numeric example the manual actually prints
   (Experiment 1 only — see the summary table inside that file).
   The PDF binary itself was not deposited (only pasted as chat content),
   so `manual/README.md`'s instruction to drop `BACHY105.pdf` there is
   now doubly stale — updated separately (see below).

2. **Experiment 7/8 identity, corrected.** The pre-existing code (before
   the manual arrived) guessed Experiment 7 = ethane conformers,
   Experiment 8 = cyclohexane conformers, as two separate ordering
   checks. The real manual has **one** experiment (8) covering **both**
   ethane and cyclohexane conformer energies, and Experiment 7 is an
   unrelated DFT/orbital-contribution workflow with no ordering to
   check at all (a single run has one HOMO and one LUMO, not two
   conformers to compare).
   - `exp08.py` rewritten: now a `QualitativeOrderingPlugin` with both
     ethane and cyclohexane orderings and 4 Socratic steps (was 2).
   - `exp07.py` rewritten: now honestly `PendingManualPlugin`, with a
     reason explaining the real problem shape (needs a fifth,
     not-yet-built "computation sanity" checker type — job completion +
     HOMO<LUMO + energy decreased after optimization — not an ordering
     check) instead of silently keeping the wrong ethane logic live.
   - `backend/rag/qualitative.py`'s `ALLOWED_EXPERIMENTS` narrowed from
     `{exp07, exp08}` to `{exp08}`, since Exp 7 no longer uses this
     mechanism.
   - `docs/ARCHITECTURE.md` §2.1 amended (§2.1.1) recording the
     correction, in the pattern the document's own header requires.
   - 8 test files updated to stop asserting the wrong mapping
     (`test_pipeline_and_tiers.py`, `test_phrasing_injection.py`,
     `test_single_fire_and_summaries.py`, `test_data_isolation.py`,
     `test_student_questions.py`) — full suite re-run green after each
     change.

3. **Experiment 1 (Zn–Cu EMF thermodynamics) fully implemented**, the
   one experiment the manual gives a complete worked numeric example
   for (p.13–15): Nernst-equation `Ecell` as an intermediate Socratic
   step, `ΔG = -nFEcell` as the final checker. Both formulas verified
   against the manual's own numbers (`backend/tests/test_exp01_emf.py`,
   `golden_dataset/category1_worked_examples/exp01.json`). ΔH/ΔS were
   **not** implemented: the manual's method pools ΔG at two different
   temperatures from two different runs before differencing, a shape
   none of the four shared checker types cover — flagged rather than
   forced into the wrong one.

4. **Experiments 2–6, 9, 10**: reason strings corrected from the stale
   "BACHY105 manual not present in the repository" (now false — the
   manual is present) to an accurate, experiment-specific statement of
   what's actually missing (a worked numeric example to verify a
   tolerance against — the formula itself is known and cited to a page
   range in every case). Not implemented as real checkers this session:
   each needs a deliberate tolerance-policy decision (the manual gives
   no experiment-specific numeric acceptance band, only the course-wide
   marks-vs-error-percentage rubric on p.8, which is not the same thing
   as a Tier 1 self-consistency tolerance and must not be conflated with
   one), which is a judgment call worth making individually per
   experiment rather than rushing six at once.

5. Full test suite run after every change; 663 passed, 1 pre-existing
   skip, 0 failed, at the end of the session.

Not fixed / not attempted this session, and why: everything in §2's
NOT IMPLEMENTED rows. Each is either (a) a substantial subsystem this
repo never had (vector DB, scope classifier, adjacent-knowledge corpus,
image-aware retrieval, load-test execution, an LLM-eval harness costing
real API calls) that cannot be built and *validated* honestly inside one
session without producing exactly the fabricated-evidence problem this
audit exists to prevent, or (b) six more Tier 1 experiments that each
deserve the same individual, unhurried treatment Experiment 1 got rather
than a batch of six rushed tolerance guesses.

## 4. Per-experiment status (the table the request's §29 asks for)

Routing/retrieval/citation/scope columns are marked N/A throughout
because that whole layer does not exist in this codebase (see §2 row 2)
— not because it was tested and scored zero.

| # | Title | Tier 1 checker | Worked example | Golden cases | Routing/Retrieval/Citation/Scope |
|---|---|---|---|---|---|
| 1 | Zn-Cu EMF thermodynamics | **Implemented** (Ecell + ΔG) | Yes, p.13, verified | 1 (Category 1) | N/A — no RAG/scope layer exists |
| 2 | Ester hydrolysis kinetics | Pending (regression_slope shape known) | No | 0 | N/A |
| 3 | Ni2+ colorimetry | Pending (calibration_curve shape known) | No | 0 | N/A |
| 4 | Fe potentiometry | Pending (endpoint_detection shape known) | No | 0 | N/A |
| 5 | ZnO prep/characterization | Pending (Scherrer eq. known, no sample data) | No | 0 | N/A |
| 6 | Sulfate conductometry | Pending (endpoint_detection shape known) | No | 0 | N/A |
| 7 | Orbital contributions (Gabedit/ORCA/Avogadro) | **Pending — needs new checker type** | No | 0 | N/A |
| 8 | Ethane + cyclohexane conformers | **Implemented** (QualitativeOrderingPlugin, corrected this session) | N/A (ordering-only check by design) | pre-existing category 2/5 cases (generic, not manual-numeric) | N/A |
| 9 | Fe2+ colorimetry | Pending (calibration_curve shape known) | No | 0 | N/A |
| 10 | Cu2O nanoparticle colour | Pending (calibration_curve shape known) | No | 0 | N/A |

## 5. Final acceptance gate (request §33, honestly filled in)

Nearly everything in the request's checklist is unchecked, and it should
read that way rather than be marked done on the strength of adjacent
work. The items this session can actually check:

- [x] Tier 1 math never delegated to an LLM (structural, re-verified)
- [x] Server-side authz / data isolation (re-verified, tests pass)
- [x] Answer gate covers both modes (re-verified, tests pass)
- [x] Experiment 1 implemented, routable-in-the-sense-this-codebase-has
      (registered, used by the pipeline), source-grounded (manual page
      cited in `manual_reference`), baseline-tested (golden + unit)
- [x] Experiment 8 identity corrected and both conformer pairs covered
- [ ] Everything else in the request's §33 checklist — **unchecked**,
      because the underlying subsystem (RAG/scope/adjacent-knowledge/
      image retrieval/load test/evaluator) does not exist yet, not
      because it exists and scored poorly.

**The honest one-line summary:** this repository is a working,
well-tested, ~10%-of-the-way point toward the product the Phase 2
request describes, on a course whose manual only just arrived — one
experiment now has a real, manual-verified deterministic checker, the
biggest latent correctness bug (Experiment 7/8 identity) is fixed, and
every other gap is named specifically enough that the next session can
pick any one item in §2 and build it for real, rather than being told
"mostly done" and discovering otherwise later.
