# Phase 3 handoff

Written mid-session (2026-09-17, branch `master`, HEAD `e17afd3`), first
as a preemptive note before a usage-window cutoff, then updated after
the session actually continued past that point. `docs/handoff_phase2.md`
is now stale in its "manual missing" framing — the manual
(`manual/IACHY102_manual.md`) has been present and ingested for several
sessions; ignore that document's premise, not necessarily every finding
in it (some items may still be open — not re-audited this session).

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
- **Not fully browser-verified**: the new `ChatWorkspace` UI's actual
  chat *send* (a live attempt hit a 500, traced to this session's own
  disposable scratch SQLite file having stale WAL/schema state, not an
  app bug — `test_chat_routes.py` passes cleanly against a correctly-
  built DB, which is the real evidence for that code path); the full
  Socratic/diagnostic/multi-thread flow through the new unified box;
  the faculty `AdminModal`/`FacultyModal` flows; the co-faculty and
  two-faculty-one-classroom scenarios against the new UI. The machine
  this session ran on became severely memory-constrained (SQLite/OAuth-
  cookie test users had to be recreated multiple times; server restarts
  kept getting OOM-killed) partway through this second verification
  pass — that resource exhaustion, not a code issue, is why this list
  stops here.

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

## Suggested next steps, roughly in priority order

1. Browser-verify the new `ChatWorkspace` UI's actual message send
   (Q&A/Socratic/diagnostic all flow through one unified box now — read
   `backend/api/chat_routes.py` to understand how it dispatches) using a
   **freshly created** scratch SQLite DB (delete any old
   `labtutor.sqlite*` files first, including `-wal`/`-shm` siblings, to
   avoid the stale-schema 500 this session hit) or, better, a fresh
   `:memory:`-style temp path per run.
2. Browser-verify faculty flows through `FacultyModal.tsx` (Socratic/
   diagnostic testing, class controls, submissions/escalations,
   summaries) and admin flows through `AdminModal.tsx`, plus the
   "two faculty members, one classroom" and co-faculty scenarios,
   against the *current* UI — not the old per-page components.
3. If real Postgres/Google OAuth/LLM-provider credentials become
   available, perform the goal's item 7 real external checks and
   update the report with genuine evidence instead of "not configured."
   (A local Ollama instance was observed running on this machine and is
   what the LLM client actually fell back to during this session's live
   checks — that is not the same as verifying the real "hosted" backend.)
4. Load-test prep (~70 students / 2 hours) was not done this session —
   read `infra/loadtest.py` (exists, unclear if up to date) before
   writing a new plan from scratch.
5. Re-run the full verification bar (backend suite, tsc, build, alembic
   check, golden QA) after any further change, and keep committing in
   small logical units with real verification each time — that pattern
   held for the whole of this session and should continue.
6. If this machine is still memory-constrained, prefer `next build` +
   `next start` over `next dev` for any live browser check (much lower
   footprint), and check `free -h` before spawning uvicorn/next
   processes — several restart attempts this session were killed by
   the OS for memory pressure, unrelated to the code itself.
