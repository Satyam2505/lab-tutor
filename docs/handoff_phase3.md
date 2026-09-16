# Phase 3 handoff

Written mid-session (2026-09-17, branch `master`, HEAD `ccf0bc6`) because
the session's usage window is ending. `docs/handoff_phase2.md` is now
stale in its "manual missing" framing — the manual
(`manual/IACHY102_manual.md`) has been present and ingested for several
sessions; ignore that document's premise, not necessarily every finding
in it (some items may still be open — not re-audited this session).

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

## Verified this session (real evidence)

- Full backend suite: 1590 collected / 1589 passed / 1 skipped / 0
  failed as of the last run before this handoff.
- `npx tsc --noEmit` and `npm run build` (frontend): both clean.
- `alembic upgrade head` + `alembic check` against a fresh SQLite DB:
  applies cleanly, zero drift.
- **Live browser session** (Playwright, against the real Next.js dev
  server + real FastAPI backend on SQLite, session cookies minted
  directly via `backend.auth.session.issue()` since no real Google
  OAuth credentials are configured in this environment — see below):
  onboarding form → join by student code → active-experiment banner →
  Q&A with a real grounded, cited answer and a working follow-up turn
  → Socratic step verification against the real exp01 Tier 1 checker
  (correct rejection of wrong field names with a clear message, correct
  pass-and-advance, a real adaptive hint) → diagnostic submission
  (correctly flagged `invalid` with a clear reason) → submission history
  (after the fix, updates live without reload).
- **Not yet browser-verified this session**: the faculty dashboard's own
  tabs (Socratic/diagnostic testing, roster promote/demote, coverage,
  summaries) end-to-end in a real browser — only their backend routes
  and `tsc`/`next build` were checked; the co-faculty "two faculty on
  one classroom without replacing each other" scenario from the goal;
  the admin console's live browser flow.

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

1. Browser-verify the faculty dashboard tabs live (the goal's item 1
   faculty flow, and the "two faculty members, one classroom" check)
   — this session ran out of window before reaching it.
2. If real Postgres/Google OAuth/LLM-provider credentials become
   available, perform the goal's item 7 real external checks and
   update the report with genuine evidence instead of "not configured."
3. Load-test prep (goal item 8, ~70 students / 2 hours) was not done
   this session — read `infra/loadtest.py` (exists, unclear if
   up to date) before writing a new plan from scratch.
4. Re-run the full verification bar (backend suite, tsc, build, alembic
   check, golden QA) after any further change, and keep committing in
   small logical units with real verification each time — that pattern
   held for the whole of this session and should continue.
