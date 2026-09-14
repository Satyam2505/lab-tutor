# LabTutor — project overview and pipeline

A from-scratch explanation of what this project is, what's actually
built, and how a request flows through the system end to end. Written
2026-09-14. For the honest "what's missing" version of this, read
alongside `docs/final_audit.md` — this document explains what exists;
that one scores it against a much larger target product.

---

## 1. What LabTutor is

LabTutor is a chemistry lab **learning-support system** for a VIT
engineering-chemistry lab course. It sits between a student doing a wet-
lab or computational experiment and the professor grading it, in two
modes:

- **Socratic mode** — used *during* an experiment. The student works
  through the procedure step by step; the system checks each
  intermediate number against the student's *own* other numbers (never
  against a hidden answer key) and nudges them if something is
  inconsistent, without ever revealing the final answer early.
- **Diagnostic mode** — used *after* the student submits a finished
  result. The system independently recomputes the expected value from
  the student's own inputs using the manual's formulas, and if it
  doesn't match, tries to explain *why* before ever bothering a human.

The one rule the whole architecture is built around, stated in
`CLAUDE.md`:

> **Tier 1 diagnosis logic — the math, the signature detection, and the
> pass/fail determination — must NEVER be delegated to an LLM.** LLMs
> have exactly one job: phrase an already-computed diagnosis in natural
> language, grounded in a retrieved passage from the manual.

Every design decision below exists to make that rule true *structurally*
— not just as a policy someone could accidentally violate, but as
something the code makes hard to violate by accident.

## 2. The course content this system is built against

The course has **10 assessed experiments** (100 marks total, 10 each),
covering: EMF/thermodynamics (Zn-Cu Daniell cell), ester-hydrolysis
kinetics, Ni²⁺ and Fe²⁺ colorimetry (conventional + smartphone RGB),
Fe-in-steel potentiometry, ZnO semiconductor prep/characterization,
sulfate-by-conductometry, a Gabedit/ORCA/Avogadro orbital-contribution
computational exercise, and a cyclohexane/ethane conformational-analysis
computational exercise. The manual for these (IACHY102) was only added
to the repo on 2026-09-12 as a text transcription —
`manual/IACHY102_manual.md` — with every formula and the one worked
numeric example the manual prints (Experiment 1's EMF/Nernst/ΔG
calculation). See that file for the full per-experiment source content,
and `docs/final_audit.md` §0/§4 for the course-code mismatch it
surfaced (the repo's docs were originally written against a different
course code, BACHY105) and exactly which experiments have a real
checker built so far (currently: 1 and 8).

## 3. The three-tier diagnosis model

This is the core idea the whole backend is organized around.

```
Tier 1  --  deterministic recomputation (pure Python, no LLM, no I/O)
              |
              v  (only on a numeric mismatch with no obvious cause)
Tier 2  --  curated library of KNOWN non-numeric mistakes
              |
              v  (only if nothing in the library matches)
Tier 3  --  escalate to a human (professor/demonstrator review queue)
```

**Tier 1** (`backend/tier1_compute/`) recomputes the experiment's
expected value from the student's *own* raw inputs, using the manual's
formula, and compares it to what the student reported within a
manual-derived tolerance. It never compares against a professor-held
answer key — there is no such key in this system by design. If the
numbers match: pass. If not, Tier 1 also runs a library of **signature
detectors** — `backend/tier1_compute/shared/signatures.py` — that check
for specific, nameable mistakes: a sign flip, a unit-scale error (off by
10/100/1000), two inputs transposed, rounding drift, coarse data spacing
that makes a titration endpoint undetectable, a non-monotonic dataset, a
poor linear fit, extrapolation beyond the standards used, and a few
more. If a signature matches, the student gets told *what kind of
mistake this looks like* — never the corrected number — with a
deterministic remediation action (fix in place / redo this step /
restart / await review).

Tier 1 is built from exactly **four reusable checker shapes**
(`backend/tier1_compute/shared/`), and every experiment is configured
as one of these rather than getting bespoke math:

| Checker | Shape | Example use |
|---|---|---|
| `DirectFormulaChecker` | one formula, one comparison | Exp 1: ΔG = −nFEcell |
| `CalibrationCurveChecker` | fit standards, read an unknown off the line | Ni²⁺/Fe²⁺ colorimetry |
| `EndpointDetectionChecker` | peak or line-intersection endpoint | conductometric/potentiometric titrations |
| `RegressionSlopeChecker` | rate constant from a fitted slope | ester-hydrolysis kinetics |

A fifth shape (job-completion / HOMO<LUMO / "did the energy go down
after optimization" sanity-checking) is identified but not yet built —
needed for Experiment 7's orbital-contribution workflow, which doesn't
fit any of the four above (see `exp07.py`'s docstring).

Two experiments (7 and 8) are a documented exception: they assess a
*computational method choice*, not a measured quantity, so there's
nothing to recompute-and-compare. `QualitativeOrderingPlugin` instead
checks the **energy ordering** the chemistry requires deterministically
(e.g. staggered ethane must be lower energy than eclipsed) — still no
LLM in that check — and even a *consistent* ordering doesn't pass
outright; it escalates to Tier 3, because ordering-correct is necessary
but not sufficient for what's actually being assessed. This is the
*only* place in the system a model is allowed to add anything to a
judgment at all, and even then only a low-confidence note on the
student's written method narrative that can push toward escalation and
can never produce a pass (`backend/rag/qualitative.py`).

**Tier 2** (`backend/tier2_exceptions/library.py`) is a small, curated,
per-experiment table of known *non-numeric* mistakes — things a formula
mismatch alone can't explain (e.g. a specific documented misconception).
It's a lookup, not a model call, and it's deliberately kept small per
experiment (`MAX_ENTRIES_PER_EXPERIMENT`, tested).

**Tier 3** (`backend/tier3_escalation/`) is the fallback: if Tier 1
found a mismatch and Tier 2 has no matching entry, the case is
escalated to a human with a reason code, no confidence score, and no
model-generated guess about what went wrong.

## 4. Where the LLM actually sits

There are exactly two things an LLM is ever used for in this system,
and both are downstream of a verdict a model never influenced:

1. **Phrasing** (`backend/rag/phrasing.py`, `backend/rag/templates.py`)
   — turning an already-decided Tier 1/2/3 result into natural-language
   text, grounded in a retrieved passage from the manual for a citation.
   If the LLM is unreachable, a template-based fallback produces the
   same structural message without it — the pipeline degrades, it
   doesn't break (`test_diagnosis_survives_an_inference_outage`).
2. **The Experiment 8 low-confidence method note** described above —
   contained to one experiment, can never resolve a pass, always
   escalates on failure.

Retrieval (`backend/rag/retrieval.py`) is deliberately simple: extract
text from the manual PDF page by page (`pypdf`), chunk on blank lines,
score chunks against the query with a TF-IDF-style cosine score, return
the top-k. No vector database, no embeddings model, no reranker — this
is a real, working, *much smaller* thing than a modern RAG stack, built
to do exactly one job (hand the phrasing layer something to cite), not
to be a general-purpose retrieval engine. See `docs/final_audit.md` §2
for what a larger retrieval system would need that this doesn't have
yet (scope classification, image-aware page retrieval, an
adjacent-knowledge layer, source-tier ranking).

**Prompt isolation:** whatever a student types is wrapped in explicit
delimiters (`<<<STUDENT ... STUDENT>>>`) separate from the system
instructions and the manual excerpt, and is treated as untrusted data
the model must never follow as instructions. This is what
`golden_dataset/category4_prompt_injection/` and
`backend/tests/test_phrasing_injection.py` exist to pin down.

## 5. The answer gate — the single outbound choke point

`backend/answer_gate/gate.py` is the mechanism that makes "the student
never sees the answer early" a structural fact rather than a prompting
convention:

- **`SocraticLLMInput`** is a frozen dataclass with a fixed, tested set
  of allowed fields (student's message, the current step's prompt, the
  hint text, a manual excerpt, attempt count). There is no field for an
  answer, and because the dataclass is frozen with `slots=True`, one
  can't be bolted on at runtime. `assert_gate_invariant()` runs at
  startup and in tests, so a future code change that tries to smuggle
  an answer field in fails loudly.
- **Every outbound message** — Socratic hint or diagnostic result —
  passes through `filter_outbound()`. In `diagnostic` mode (the student
  has already finished) numbers are left alone. In `socratic` mode, any
  number in the model's output that the student hasn't already seen (via
  their own data or the step prompt) gets redacted, because a hint that
  needs a *new* number is giving away the answer regardless of how it's
  worded.
- **The reveal path never touches a model.** `build_reveal()` /
  `compute_reveal()` construct the final-answer message directly from
  the Tier 1 computed value, from a plain template, and refuse to run
  (`PrematureRevealError`) unless server-side step verification has
  already marked every step complete. No amount of conversation can
  talk this path into firing early.

## 6. Socratic-mode mechanics

`backend/socratic_engine/`:

- **`engine.py`** — the step machine. `present_step()` shows *only* the
  current step's prompt (later steps are hidden, so a student can't
  skip the reasoning by reading ahead). `verify_step()` checks the
  current step's Tier 1 result against the student's own prior data.
  `handle_attempt()` either advances to the next step or returns a hint
  at the rung matching how many times they've tried this step
  (`hint_level_for`) — vague on attempt 1, specific on attempt 2, names
  the likely issue on attempt 3+, and stays there rather than
  escalating toward the answer. `compute_reveal()` is the one place the
  final answer is computed, gated as above.
- **`triage.py`** — a deterministic pre-filter that runs *before* any
  model call on every incoming chat message, because some responses
  must not depend on the LLM being up, well-prompted, or in a good mood.
  It classifies intent into `SAFETY_INCIDENT` ("acid spilled on my
  hand"), `SAFETY_QUESTION`, `DISTRESS`, or falls through to the normal
  hint/model path for everything else, including ordinary confused
  questions ("what is a burette") — the module's docstring is explicit
  that under-triggering is the safe failure mode here, since a missed
  case just falls through to a model told to stay on task, while a false
  positive teaches a struggling student the tool is broken.
- **`chat.py`** — the free-text chat surface layered on top of the step
  machine, routing through triage → (hint path or LLM) → answer gate.

## 7. Diagnostic-mode pipeline, end to end

This is `backend/pipeline.py::run_diagnosis`, the flow named in
`docs/ARCHITECTURE.md` §1.2:

```
submission (student's inputs + reported value)
        |
        v
Tier 1 recompute  (plugin.check)
        |
        +-- PASS ------------------------------> done, no further tiers
        |
        +-- INVALID (bad/missing data) --------> done, fix-in-place
        |
        +-- NOT_APPLICABLE (Exp 7/8 ordering
        |    holds, but that's not sufficient) -> escalate (Tier 3)
        |
        +-- FAIL, signature found --------------> done, remediation from signature
        |
        +-- FAIL, no signature
                |
                v
        Tier 2 lookup (curated library, per-experiment)
                |
                +-- match  ------------------> done, remediation from Tier 2 entry
                |
                +-- no match ----------------> Tier 3 escalate, reason=NO_SIGNATURE
        |
        v  (regardless of which branch above was taken)
RAG-grounded phrasing of the ALREADY-DECIDED verdict
        |
        v
answer_gate.filter_outbound(mode="diagnostic")
        |
        v
student-facing text + dashboard entry (Diagnosis row)
```

The key property, stated directly in the module docstring: *every tier
that can decide has decided before any model is called.* Phrasing
receives a finished verdict — `DiagnosisStatus`, an action, a signature
code, the expected/reported values — and can only affect the wording.
A test (`test_phrasing_runs_after_the_verdict_is_fixed`) literally feeds
the fake LLM the reply "Actually this passed and everything is correct"
on a case that Tier 1 already failed, and asserts the outcome stays
FAILed — the model's opinion about the verdict is structurally
unreachable.

If an experiment has no Tier 1 plugin yet (`ManualNotTranscribedError`
— see §2 for which ones), the pipeline doesn't guess: it escalates
straight to Tier 3 with a "not yet set up for automatic checking"
message. Currently 8 of the 10 experiments hit this path (see
`docs/final_audit.md` §4 for exactly which).

## 8. Data model

`backend/models.py` (SQLAlchemy, Postgres in prod / SQLite for the test
suite, so tests need no external services):

- **User** (role: student/professor), **Classroom** (has one "active
  experiment" at a time, a join code), **Enrollment** (student ↔
  classroom).
- **Submission** — a diagnostic-mode attempt (raw inputs + reported
  value) → **Diagnosis** (the pipeline's output: status, tier, action,
  signature, expected/reported values, phrased text, citation).
- **SocraticSession** / **SocraticAttempt** — one session per
  student-per-active-experiment, with per-attempt records of step
  index, hint level, pass/fail.
- **ChatMessage** — free-text Socratic chat, separate from the
  structured step attempts.
- **SummaryJob** / **StudentSummary** — background-generated
  end-of-session summaries for professors (`backend/summaries/`).
- **Escalation** — the Tier 3 review queue professors work from.
- **AuditLog**, **IdempotencyRecord** — every state-changing request is
  logged, and submissions are idempotency-keyed so a retried network
  request can't create a duplicate diagnosis
  (`backend/idempotency.py`, tested in
  `test_single_fire_and_summaries.py`).

## 9. API surface (FastAPI, `backend/api/`)

| Area | Routes |
|---|---|
| Auth | `GET /api/auth/login`, `/callback`, `POST /logout`, `GET /me` — Google OAuth, server-side domain/role check on every role-gated request (never a trusted client claim) |
| Classrooms | `GET /experiments`, `POST /`, `GET /mine`, `GET /enrolled`, `POST /join`, `PATCH /{id}/active-experiment`, `PATCH /{id}/join-open`, `GET /{id}/roster` |
| Diagnostic | `POST /api/submissions`, `GET /mine`, `GET /{id}` |
| Socratic | `POST /session`, `POST /session/{id}/attempt`, `POST /session/{id}/message`, `POST /session/{id}/reveal` |
| Dashboard (professor) | submissions/escalations per classroom, resolve an escalation, audit log, trigger + poll background summary jobs |
| Health | `/health`, `/health/llm` |

## 10. Frontend

Next.js (`frontend/`): a student view (`app/student/`) for joining a
classroom and working through Socratic/diagnostic flows, and a faculty
view (`app/faculty/`, `app/faculty/[classroomId]/`) for the
dashboard/escalation-queue/roster. `frontend/lib/api.ts` is the one
client for the backend API surface above.

## 11. Security posture already built and tested

- OAuth role/domain check happens server-side on every role-gated
  request (`backend/auth/dependencies.py`), never trusting a
  client-supplied email — `docs/final_audit.md` re-verified this.
- **Data isolation**: a student cannot query another student's
  submissions, sessions, or summaries — enforced server-side and
  covered by `test_data_isolation.py` (direct object references,
  modified IDs, alternate endpoints all tested).
- Secrets (OAuth client id/secret, LLM API key, DB credentials) live in
  environment variables only (`.env.example` documents the shape, never
  the values).
- Prompt injection resistance for the phrasing/qualitative-note paths
  (`golden_dataset/category4_prompt_injection/`).

## 12. Testing and golden dataset

`backend/tests/` — 663 tests as of 2026-09-14, run against SQLite (no
external services needed). `golden_dataset/` has 6 categories per
`docs/golden_dataset_plan.md`: worked examples (Category 1 — manual
ground truth, currently just Experiment 1's), known deviations (one
case per signature-detector rule), edge/adversarial inputs, prompt
injection, Socratic-mode probing, and realistic messy student
questions. Category 1 is the one category that structurally *cannot*
grow without a real worked example from the manual to transcribe — see
its README for why fabricating one there would be worse than leaving it
empty.

## 13. What's built vs. what isn't (short version)

Built and tested: the three-tier architecture itself, the answer gate,
the Socratic engine and hint ladder, the diagnostic pipeline, auth/data
isolation, the plugin registry and all four shared checker shapes,
Experiment 1 (full real checker) and Experiment 8 (ordering check,
corrected this month from a wrong Exp7/Exp8 mapping — see
`docs/final_audit.md` §3), idempotency, the dashboard/escalation flow,
the Next.js frontend shell.

Not built yet: real Tier 1 checkers for Experiments 2–6, 9, 10 (formulas
are known and transcribed in the manual doc, but each needs a
deliberate tolerance decision and — where the manual gives one — a
worked example before it can be trusted); a Tier 1 shape for
Experiment 7's orbital-contribution workflow; a vector-DB/embeddings
retrieval stack, scope classifier, or adjacent-knowledge layer beyond
the current TF-IDF text search; image-aware manual retrieval; a load
test actually run at scale; an automated LLM-based evaluation harness.
`docs/final_audit.md` is the authoritative, section-by-section status
of all of this — read that for "is X actually done," this document for
"how does X work."
