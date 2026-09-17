# Phase 3 handoff

Written mid-session (2026-09-17, branch `master`, HEAD `ab84b7f`), first
as a preemptive note before an anticipated usage-window cutoff, then
updated twice more as the session continued past that point through a
full data-isolation/co-faculty/faculty-flow verification pass and a
deployment-readiness audit. `docs/handoff_phase2.md` is now stale in its
"manual missing" framing — the manual (`manual/IACHY102_manual.md`) has
been present and ingested for several sessions; ignore that document's
premise, not necessarily every finding in it (some items may still be
open — not re-audited this session).

## Second update — the single most important finding of this session

**The new unified `ChatWorkspace` UI has no genuine step-by-step Socratic
guided mode.** `backend/api/chat_routes.py::send_message` imported
`handle_attempt`/`SocraticSession`/`SocraticAttempt`/`present_step`/
`steps_for`/`tutor_reply` but never called any of them (confirmed via
`pyflakes` and a live curl test: sending partial step-1 data through the
chat produced an immediate "invalid, missing X" diagnostic response, the
same as a final-submission rejection, not a step-1 hint). Every numeric-
bearing chat message is instead scored as a ONE-SHOT FINAL diagnostic via
the same Tier 1-3 pipeline `/api/submissions` uses. There is no hint
ladder, no "step N of M" progression, and no answer-gate-protected
reveal in the live chat surface. The real step-by-step engine and its
API (`backend/api/socratic_routes.py`, still fully tested and correct in
isolation) is simply not wired into the new frontend at all.

This was **not fixed** this session — implementing genuine per-message
step-state tracking inside a shared chat box is a product/UX design
decision (how does a student "declare" they're on step 2 vs. submitting
a final record, in a single free-text box?), not a bounded bug fix, and
the goal explicitly said not to redesign without a concrete requirement.
The dead imports were removed and the file's docstring now states this
gap explicitly so nobody mistakes "the code imports Socratic stuff" for
"Socratic mode works here." **This is the top-priority item for whoever
continues**, since it means the guided-mode pedagogical feature the
whole Tier 1 architecture was built around is not actually reachable by
a real student using the live product today.

A second, smaller but safety-relevant bug found the same way: `Escalation`
was also imported-but-unused in `chat_routes.py` — a diagnosis correctly
computed as needing human review (`status=escalated` /
`action=await_review`) never created an `Escalation` row, so it silently
never reached the faculty review queue. This one WAS fixed and
live-verified (exp08's always-escalates conformer-ordering check,
before/after the fix).

## Third update — full data-isolation / co-faculty / faculty-flow pass

All done via direct API calls (curl) against a live backend on a fresh
scratch DB, plus a live browser walkthrough of the faculty side of the
new `ChatWorkspace` UI. All passed:

- Outsider student on an unrelated classroom's roster: 403. Outsider
  faculty (real role, but not a member of that classroom): 404 — the
  intentional 403-role/404-membership split, confirmed still correct.
- Student code presented by faculty, and vice versa: both rejected with
  a clear "this is a X join code" message; no cross-type access created.
- Two faculty (`prof1`, `prof2`) on the same classroom: both appear as
  peers on the faculty roster, both independently query the student
  roster and dashboard submissions — neither replaces the other.
- Student-to-student isolation: student2's `/api/submissions/mine` is
  empty after student1 submits; each only ever sees their own rows.
- Stale-tab rejection after class end: Q&A, diagnostic submission, and
  Socratic session-start all correctly return 409 for a student whose
  tab never reloaded.
- Auto-queued summaries: generated correctly on session end, visible to
  faculty, 403 for students, with `flagged: true` + a real reason for a
  student who has no activity to summarise (an honest empty-transcript
  flag, not a fabricated summary).
- Co-faculty promotion: before promotion, a student gets 403 on the
  faculty roster route; after `POST /promote`, 200, with the platform
  role still reported as `"student"` on `/api/auth/me`. **Re-verified
  with a freshly-issued session token (simulating re-login/refresh)**:
  access persists — it's a DB-backed membership row, not session state.
  Demotion (`POST /demote`) immediately drops access back to 403, again
  confirmed with a fresh token.
- Faculty/admin-test exclusion from student analytics: `prof2`'s own
  diagnostic test submission is tagged `actor_type: "faculty_test"` on
  the dashboard submissions list, distinguishable from `student1`'s real
  `"student"`-tagged rows, both visible together to faculty as intended.
- Live browser: faculty login shows the `FACULTY` badge; "Faculty Tools"
  / "🎓 Classroom Management" opens a modal with **roster** (shows both
  faculty as "Platform Faculty" peers, "Promote to Co-Faculty" per
  student), **session** (class controls: active-session status, "End
  Class Session"), **settings** (join-open toggle, join codes), and
  **summaries** (correct empty state when no summaries exist yet for
  the current, still-active session) tabs. There is no separate
  "Socratic testing" / "diagnostic testing" tab in the new UI — faculty
  test the pipelines by using the same chat box themselves (which is
  consistent with the unified design, and does produce correctly-tagged
  `FACULTY_TEST` activity, per the item above).

**Update**: after this doc was first written (commit `5938e31`), a
different agent session (`848eb3b`) rewrote the student/faculty/admin
frontend into a single shared "ChatGPT-style" `ChatWorkspace` component
(`frontend/components/ChatWorkspace.tsx`) with multi-thread chat, plus a
new backend `backend/api/chat_routes.py` and a `thread_id`/`metadata_json`
migration on `chat_messages`. This session then continued, verified that
rewrite (backend suite, tsc, build, Alembic all still green against it),
found and fixed one real live bug it introduced
(`GET /api/classrooms/experiments` still `require_faculty_or_admin`-gated
even though the new shared `ChatWorkspace` calls it for students too —
fixed in `e17afd3`), and re-verified the fix live in a browser. The
"suggested next steps" section below is updated accordingly.

## What this session did (all pushed, commits `86310e9`..`ccf0bc6`)

1. Admin can change any user's platform role anywhere (`PATCH`/`DELETE
   /api/admin/users/{id}/role[-override]`), audit-logged, self-change
   blocked.
2. Faculty can promote a student to classroom-scoped co-faculty
   (`POST /api/classrooms/{id}/promote` / `/demote`) — does not touch
   platform role, contained to one classroom, verified via
   `backend/tests/test_role_management.py`.
3. Unrecognised email domains default to STUDENT instead of rejecting
   sign-in (`backend/auth/roles.py::role_for_email`).
4. Every user completes name + (students only) reg_no via a blocking
   onboarding form (`POST /api/auth/complete-profile`, gated in
   `frontend/components/Shell.tsx`).
5. Deterministic (non-LLM) per-experiment topic-coverage score for
   faculty (`backend/summaries/coverage.py`,
   `GET /api/dashboard/classrooms/{id}/coverage`).
6. A full live browser smoke test (Playwright, real running app) found
   and fixed two real bugs:
   - `POST /api/socratic/session/{id}/attempt`'s validation-failure
     early returns were missing `total_steps`/`complete`/`prompt`,
     rendering "Step NaN of" in the UI on an invalid submission. Fixed
     in `backend/api/socratic_routes.py`.
   - Submitting a diagnostic record didn't refresh "My submission
     history" until a full reload. Fixed with a new `onSubmitted`
     callback on `SubmitPanel`.
   Plus four "stuck on Loading forever after a fetch error" bugs across
   faculty/admin/student pages and the faculty dashboard's sub-tabs, a
   broken co-faculty back-link, and a co-faculty dashboard-access gate
   that was still checking platform role instead of classroom-scoped
   capability (the single most important bug this phase found).
7. `GET /api/classrooms/experiments` now returns each experiment's
   testing priority (P0+/P0/P1, from the pre-existing
   `backend/scope/ontology.py::PRIORITY` map) and lists priority-first;
   the frontend pickers star exp02/03/07/08 while still listing (and
   allowing) all 10 — this was a direct, mid-session correction from the
   user: "priority is exp2,3,7,8... it should show every exp, just that
   those 4 are the best ones." Read that framing as the intended product
   behavior for any further experiment-picker UI work.
8. Golden QA dataset regenerated against the live manual/pipeline,
   623/623 verified.

## IMPORTANT: the frontend described in items 1-8 above is now superseded

Everything in the "what this session did" list above that describes
`frontend/app/student/page.tsx`, `frontend/app/admin/page.tsx`,
`frontend/app/faculty/page.tsx` as separate per-role pages with distinct
`SubmitPanel`/`SocraticPanel`/`QaChat`/`Roster`/`Coverage` components is
**historically accurate for what this session built, but those pages
were then replaced** by commit `848eb3b`'s unified `ChatWorkspace`. The
*backend* routes and behavior described above are still current and
still the ones `ChatWorkspace` calls; only the frontend presentation
layer changed. Read `frontend/components/ChatWorkspace.tsx`,
`frontend/components/AdminModal.tsx`, `frontend/components/FacultyModal.tsx`,
and `backend/api/chat_routes.py` for the current frontend/chat reality,
not the older per-page components this session originally wrote (still
present in git history but no longer referenced by `student`/`admin`/
`faculty` pages, which now all render `<ChatWorkspace me={me} />`).

## Verified this session (real evidence)

- Full backend suite: 1590 collected / 1589 passed / 1 skipped / 0
  failed, as of the last run against `e17afd3` (i.e. including the
  other agent's `ChatWorkspace`/`chat_routes.py` rewrite and this
  session's fix on top of it).
- `npx tsc --noEmit` and `npm run build` (frontend): both clean against
  `e17afd3`.
- `alembic upgrade head` + `alembic check` against a fresh SQLite DB:
  all three migrations (baseline, role_override/reg_no, chat
  threads/metadata) apply cleanly in order, zero drift.
- **Live browser session against the NEW unified `ChatWorkspace` UI**
  (Playwright, real Next.js production server + real FastAPI backend on
  SQLite, session cookies minted directly via
  `backend.auth.session.issue()` since no real Google OAuth credentials
  are configured in this environment — see below): sign-in page (no
  raw JSON, clean copy) → student session → the new sidebar (classroom
  selector, experiment selector, chat threads) rendered correctly →
  **found and fixed a real bug**: the experiment selector was empty and
  the browser console showed a `403 "Staff or admin only"` on
  `GET /api/classrooms/experiments`, because that route was still
  faculty/admin-gated from before `ChatWorkspace` started calling it for
  every role. Fixed (`current_user` instead of `require_faculty_or_
  admin`), re-verified live: the dropdown now populates, priority-sorted,
  ⭐-marked on exp02/03/07/08, and the real experiment title renders in
  the chat header.
- Earlier in the session, against the *old* per-page frontend (before
  `848eb3b` landed): onboarding form → join by student code →
  active-experiment banner → Q&A with a real grounded, cited answer and
  a working follow-up turn → Socratic step verification against the
  real exp01 Tier 1 checker (correct rejection of wrong field names with
  a clear message, correct pass-and-advance, a real adaptive hint,
  and a live-confirmed fix for a "Step NaN of" bug) → diagnostic
  submission (correctly flagged `invalid` with a clear reason) →
  submission history (after a fix, updates live without reload). These
  specific pages no longer exist, but the *backend* routes they
  exercised are unchanged and still passing, and the same behaviors
  should still be reachable through `ChatWorkspace`'s unified message
  box (not yet individually re-confirmed there — see next steps).
- **Update — chat send re-verified live, successfully**: after rebuilding
  the frontend with `BACKEND_INTERNAL_URL` actually baked in (a plain
  `npm run build` without that env var silently produces a build with no
  API rewrite at all — costly to rediscover, see the environment note
  below) and starting both servers against a genuinely fresh scratch
  SQLite DB (the earlier 500 really was just stale WAL/schema state in
  a reused scratch file, confirmed by the DB producing the *old*
  `chat_messages` schema even though `models.py` was current), a real
  Q&A message ("What is the principle and formula...") produced a
  grounded answer with a manual citation in a new chat thread, and a
  real diagnostic-style message ("Here are my readings: ecell=1.1,
  reported_value=-212.3") produced a genuine deterministic `PASS (Tier
  1)` result with a manual citation — confirming the unified chat
  correctly dispatches both Q&A and diagnostic paths, and that Tier 1
  correctness is still computed deterministically, not by the LLM.
  Multi-thread chat (new thread per topic, old thread still listed) also
  confirmed working live.
- **Still not browser-verified**: the full Socratic flow through the
  unified box (only Q&A and one-shot diagnostic were exercised); the
  faculty `AdminModal`/`FacultyModal` flows; the co-faculty and
  two-faculty-one-classroom scenarios against the new UI. This session's
  time/cost ran out before reaching them — see next steps.

## Known-safe environment facts for whoever continues

- No `.env` file exists in this checkout — no real Postgres, no real
  Google OAuth client id/secret, no real LLM provider credentials are
  configured. Any further "real external check" claim needs those
  filled in first; document explicitly if you still can't get them.
- A local Ollama instance was observed running on this machine
  (`ps aux | grep ollama`) and the backend's LLM client automatically
  fell back to it when the configured "hosted" backend had no
  credentials (see `backend/llm/client.py`'s fallback log line). The
  Q&A answers verified live in the browser this session came from that
  fallback, not the real production ("hosted") backend — don't
  represent that as hosted-backend verification.
- The browser-verification scratch environment (throwaway, not part of
  the repo) lived at `/tmp/claude-1000/browser_verify/` — a scratch
  SQLite DB, an env-var script, and a `make_users.py` helper that mints
  session cookies directly via the same mechanism
  `backend/tests/conftest.py::make_user` uses. Recreate if useful;
  nothing there needs to be preserved.
- `.playwright-mcp/` appeared as an untracked directory (browser-test
  screenshots/snapshots) — not committed, safe to delete.

## Deployment-readiness audit findings (this session)

Reviewed: config/secrets, CORS, cookies, auth, logging, DB startup,
migrations, health checks, background jobs, Docker/Caddy production
wiring. Findings:

- **Fixed**: a real background-task GC risk — the manual "regenerate
  summaries" route created its `asyncio.create_task(run_job(...))`
  without keeping a strong reference, unlike the automatic end-of-class
  path, which already had the correct protection. A task with no
  reference can be silently garbage-collected mid-batch. Extracted the
  existing protection into `track_background_task()` in
  `backend/summaries/jobs.py` and used it at both call sites.
- **Fixed (docs only)**: `backend/ratelimit.py`'s docstring and
  README's "Known limitations" both claimed the in-process rate limiter
  is "exact" with one backend container. It isn't, right now, in the
  documented pilot topology: `infra/backend.Dockerfile` runs
  `uvicorn --workers 2`, so a single container already has two
  independent worker processes with un-shared limiter state — the
  effective per-user limit is already up to 2x the configured value
  before any replica scale-out. Not fixing the underlying limitation
  (needs Redis, explicitly out of scope for this pass); just correcting
  the documentation so the actual risk is understood.
- **Investigated, confirmed NOT a bug**: no `CORSMiddleware` exists
  anywhere in the backend. Confirmed this is correct, not missing —
  both `frontend/next.config.js`'s dev rewrite and `infra/Caddyfile`'s
  production routing keep the browser same-origin to `/api/*` always;
  no cross-origin request is ever made.
- **Investigated, confirmed NOT a bug**: the production session-secret
  guard (refusing to start with the `"dev-insecure-secret"` default
  when `LABTUTOR_ENV=production`) is already present in
  `backend/main.py`'s `lifespan()`.
- **Investigated, confirmed NOT a bug**: `infra/frontend.Dockerfile`'s
  `next build` step runs with no `BACKEND_INTERNAL_URL` available,
  which looked like the exact rewrite-baking bug this session hit
  locally — but in the real `docker-compose` + Caddy production stack,
  Caddy's `handle /api/* { reverse_proxy backend:8000 }` intercepts
  those requests before they ever reach the Next.js server, so Next's
  own rewrite mechanism is unused/irrelevant there. Confirmed via
  `infra/Caddyfile` and a grep showing no server-side code reads
  `BACKEND_INTERNAL_URL` outside `next.config.js`. Not a production risk.
- **Not fully audited**: Postgres-specific behavior (only SQLite has
  been exercised, this session and prior ones — see "Real external
  checks" below), and whatever else differs under real concurrent
  multi-worker traffic that a single-process pytest run can't surface.

## Real external checks (goal item 7) — why they were not performed

No `.env` file exists in this checkout, so none of the following have
real credentials configured: `POSTGRES_*`, `GOOGLE_CLIENT_ID`/
`GOOGLE_CLIENT_SECRET`, any real LLM provider (`LABTUTOR_LLM_*`). This
session (and the ones before it) verified everything against SQLite and
against whatever the LLM client falls back to when unconfigured — this
session observed a local Ollama instance already running on the host
and confirmed live chat answers came from that fallback, not a real
"hosted" backend. `infra/loadtest.py --dry-run` was run and confirmed
functional (harness works, no network calls), but a real run against a
real LLM provider was not performed for the same credential reason.
**None of Postgres, Google OAuth, a real LLM provider, or real
multi-worker/multi-replica concurrency have been verified by any
session so far** — only SQLite + local-fallback-LLM + single-process
test-harness evidence exists anywhere in this repo's history.

## Suggested next steps, roughly in priority order

1. **Decide what to do about the missing Socratic step-by-step mode in
   the new `ChatWorkspace` UI** (see the "second update" section above)
   — this is the top-priority open item. Either wire real per-message
   step-state tracking into `chat_routes.py`, or explicitly decide the
   one-shot-diagnostic-only behavior is the intended product simplification
   and update the architecture docs (CLAUDE.md, README) to match reality
   instead of describing a guided mode that isn't reachable.
2. Browser-verify the admin `AdminModal.tsx` flow (role search/change,
   role-override clearing) against the current UI — not yet done live
   this session (verified only via the backend test suite + curl).
3. If real Postgres/Google OAuth/LLM-provider credentials become
   available, perform the goal's item 7 real external checks for real
   and update this report with genuine evidence instead of "not
   configured."
4. Get real load-test numbers using `infra/loadtest.py` against the
   actual configured LLM provider once credentials exist, and verify
   the DB pool sizing (`pool_size=20, max_overflow=10` per worker × 2
   workers = up to 60 base / 90 max connections against Postgres's
   default `max_connections=100`) holds under real concurrent load —
   both are currently reasoned-about, not load-tested.
5. Re-run the full verification bar (backend suite, tsc, build, alembic
   check, golden QA) after any further change, and keep committing in
   small logical units with real verification each time.
6. Environment gotchas hit this session, for whoever continues:
   - `next build` without `BACKEND_INTERNAL_URL` set silently produces a
     build with *no* `/api/*` rewrite at all (the rewrite is baked in at
     build time, not evaluated per-request) — always
     `BACKEND_INTERNAL_URL=http://127.0.0.1:<port> npm run build` before
     `next start` for any local live check, and don't run a plain
     `npm run build` afterward (it'll silently strip the rewrite again).
   - Prefer `next build` + `next start` over `next dev` for live
     checks — much lower memory footprint.
   - Delete `*.sqlite`, `*.sqlite-wal` and `*.sqlite-shm` together
     (not just the base file) when resetting a scratch dev DB — a
     leftover WAL file can resurrect old rows/schema into a "fresh"
     file and reproduce confusing stale-schema errors.
   - This machine ran very low on free memory during this session
     (repeated OOM-kills on server restarts, `free -h` showed under
     600Mi free with ~19Gi/22Gi swap used); check `free -h` before
     spawning uvicorn/next processes.

## Recommended load-test plan (~70 students, ~2 hours)

Not executed this session (no LLM-provider credentials configured).
When credentials exist, run in this order:

1. **`infra/loadtest.py` against the real configured LLM backend**
   (`python infra/loadtest.py --students 70 --turns 6`, no `--dry-run`)
   — this is the one piece of infrastructure already built for exactly
   this. It measures inference latency/error-rate only (no DB, no web
   tier), gated by the script's own p95/error-rate thresholds. Confirm
   the "hosted" backend (not the Ollama fallback) is what actually
   answers, or the numbers mean nothing.
2. **Real concurrent multi-student HTTP load** against the full stack
   (Caddy + backend + Postgres), not just the inference layer — e.g.
   Locust/k6 driving ~70 simulated students each doing join → Q&A →
   Socratic/diagnostic → occasional dashboard poll, sustained ~2 hours.
   Watch: `pool_size=20, max_overflow=10` per worker × `--workers 2` =
   up to 60 base / 90 max Postgres connections against Postgres's
   default `max_connections=100` — close enough to want a real number,
   not just the arithmetic above.
3. **In-process rate limiter's real effective ceiling** under that same
   load — confirm it's actually ~2x the configured `LABTUTOR_RATELIMIT_*`
   values (per the `--workers 2` finding above), not the configured
   value itself, and decide whether that's acceptable for the pilot or
   needs a shared store before go-live.
4. **Background summary-job throughput** at pilot scale: ending a class
   session for ~70 students queues one job per student, batched by
   `LABTUTOR_SUMMARY_WORKERS` (default 4) `asyncio.Semaphore`-limited
   concurrency, each needing an LLM call (or falling back to a
   deterministic template) plus a sanity-check LLM call. Confirm this
   completes in a reasonable time and doesn't itself contend with
   live student traffic for the same LLM backend's concurrency budget.
5. **Request timeouts and retry behavior**: confirm what happens to a
   student's in-flight Q&A/diagnostic request if the LLM backend is
   slow or times out mid-pilot — check `backend/llm/client.py`'s
   timeout/retry/fallback configuration under sustained load, not just
   the single-request fallback-on-unavailable path already exercised
   by this session's tests.
6. **Memory/CPU** of the actual containers under sustained 70-student
   load for 2 hours, not just this session's ad-hoc host (which was
   memory-constrained for unrelated reasons — other processes on a
   shared dev machine, not the app itself).

Do not introduce Redis/Kubernetes/etc. before these numbers say the
current single-container-plus-Postgres topology actually can't hold
~70 students for 2 hours — the goal explicitly asked not to add
infrastructure without a concrete measured requirement, and none of
the above has been measured yet.
