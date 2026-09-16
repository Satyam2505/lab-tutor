"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { QaChat } from "@/components/QaChat";
import { Shell } from "@/components/Shell";
import { SocraticPanel } from "@/components/SocraticPanel";
import { SubmitPanel } from "@/components/SubmitPanel";
import {
  ApiError,
  api,
  newIdempotencyKey,
  type ClassSessionInfo,
  type DashboardSubmission,
  type Escalation,
  type Experiment,
  type RosterFaculty,
  type RosterStudent,
  type StudentCoverage,
  type StudentSummary,
  type SummaryJob,
} from "@/lib/api";

export default function ClassroomDashboardPage({
  params,
}: {
  params: Promise<{ classroomId: string }>;
}) {
  const { classroomId } = use(params);
  return (
    <Shell requireRole={["faculty", "admin"]}>
      {() => <Dashboard classroomId={classroomId} />}
    </Shell>
  );
}

type Tab =
  | "ask"
  | "socratic"
  | "diagnostic"
  | "submissions"
  | "escalations"
  | "summaries"
  | "roster"
  | "coverage";

const TAB_LABEL: Record<Tab, string> = {
  ask: "Ask",
  socratic: "Socratic testing",
  diagnostic: "Diagnostic testing",
  submissions: "Submissions",
  escalations: "Review queue",
  summaries: "Summaries",
  roster: "Roster",
  coverage: "Coverage",
};

function Dashboard({ classroomId }: { classroomId: string }) {
  const [tab, setTab] = useState<Tab>("ask");
  const [error, setError] = useState("");

  return (
    <>
      <h1>Section dashboard</h1>
      <p className="muted">
        <a href="/faculty">← all sections</a>
      </p>

      {error && <div className="error">{error}</div>}

      <div className="row" style={{ marginBottom: 14, flexWrap: "wrap" }}>
        {(
          [
            "ask",
            "socratic",
            "diagnostic",
            "submissions",
            "escalations",
            "summaries",
            "roster",
            "coverage",
          ] as Tab[]
        ).map((t) => (
          <button
            key={t}
            type="button"
            className={`btn ${tab === t ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setTab(t)}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {tab === "ask" && <QaChat classroomId={classroomId} />}
      {tab === "socratic" && <ExperimentTest classroomId={classroomId} mode="socratic" />}
      {tab === "diagnostic" && <ExperimentTest classroomId={classroomId} mode="diagnostic" />}
      {tab === "submissions" && (
        <Submissions classroomId={classroomId} onError={setError} />
      )}
      {tab === "escalations" && (
        <Escalations classroomId={classroomId} onError={setError} />
      )}
      {tab === "summaries" && (
        <Summaries classroomId={classroomId} onError={setError} />
      )}
      {tab === "roster" && <Roster classroomId={classroomId} onError={setError} />}
      {tab === "coverage" && <Coverage classroomId={classroomId} onError={setError} />}
    </>
  );
}

/**
 * Faculty/admin exercise the exact same Socratic/diagnostic engines a
 * student would, against an explicitly chosen experiment rather than
 * the classroom's active session (see `backend/api/socratic_routes.py`
 * and `diagnostic_routes.py`'s `experiment_id` override for non-student
 * callers). Every session/submission this produces is stamped
 * `FACULTY_TEST`/`ADMIN_TEST` server-side and is structurally excluded
 * from student analytics and summaries -- see `backend/models.py`'s
 * `ActorType` and `backend/summaries/jobs.py`.
 */
function ExperimentTest({
  classroomId,
  mode,
}: {
  classroomId: string;
  mode: "socratic" | "diagnostic";
}) {
  const [experiments, setExperiments] = useState<Experiment[] | null>(null);
  const [experimentId, setExperimentId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<{ experiments: Experiment[] }>("/api/classrooms/experiments")
      .then((d) => {
        setExperiments(d.experiments);
        setExperimentId((current) => current || d.experiments.find((e) => e.ready)?.id || "");
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  return (
    <>
      <p className="muted">
        Faculty/admin testing runs the same engine a student would see, on
        a chosen experiment -- never counted as student activity or fed
        into any summary.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <label>
          <span>Experiment to test</span>
          <select value={experimentId} onChange={(e) => setExperimentId(e.target.value)}>
            <option value="">— choose —</option>
            {(experiments ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.id} — {e.title}
                {e.ready ? "" : " (not configured)"}
              </option>
            ))}
          </select>
        </label>
      </div>

      {experimentId && mode === "socratic" && (
        <SocraticPanel classroomId={classroomId} experimentId={experimentId} />
      )}
      {experimentId && mode === "diagnostic" && (
        <SubmitPanel
          classroomId={classroomId}
          experimentId={experimentId}
          title="Test a diagnostic submission"
        />
      )}
    </>
  );
}

function Submissions({
  classroomId,
  onError,
}: {
  classroomId: string;
  onError: (m: string) => void;
}) {
  const [rows, setRows] = useState<DashboardSubmission[] | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    const query = filter ? `?status=${encodeURIComponent(filter)}` : "";
    api
      .get<{ submissions: DashboardSubmission[] }>(
        `/api/dashboard/classrooms/${classroomId}/submissions${query}`,
      )
      .then((d) => setRows(d.submissions))
      .catch((e) => onError(e instanceof ApiError ? e.message : String(e)));
  }, [classroomId, filter, onError]);

  if (rows === null) return <p className="muted">Loading…</p>;

  return (
    <>
      <label style={{ maxWidth: 260 }}>
        <span>Filter by status</span>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All</option>
          <option value="pass">Pass</option>
          <option value="fail">Fail</option>
          <option value="escalated">Escalated</option>
          <option value="invalid">Invalid</option>
        </select>
      </label>

      {rows.length === 0 ? (
        <p className="muted">No submissions yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Student</th>
              <th>Status</th>
              <th>Tier</th>
              <th>Signature</th>
              <th>Expected</th>
              <th>Reported</th>
              <th>Explanation</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.submission_id}>
                <td>{r.student_email}</td>
                <td>
                  <span className={`pill pill-${r.status}`}>{r.status}</span>
                </td>
                <td>{r.tier ?? "—"}</td>
                <td className="mono">{r.signature ?? "—"}</td>
                <td>{r.expected_value ?? "—"}</td>
                <td>{r.reported_value ?? "—"}</td>
                <td>{r.explanation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Escalations({
  classroomId,
  onError,
}: {
  classroomId: string;
  onError: (m: string) => void;
}) {
  const [rows, setRows] = useState<Escalation[] | null>(null);
  const [unresolvedOnly, setUnresolvedOnly] = useState(true);

  const load = useCallback(async () => {
    const d = await api.get<{ escalations: Escalation[] }>(
      `/api/dashboard/classrooms/${classroomId}/escalations?unresolved_only=${unresolvedOnly}`,
    );
    setRows(d.escalations);
  }, [classroomId, unresolvedOnly]);

  useEffect(() => {
    load().catch((e) => onError(e instanceof ApiError ? e.message : String(e)));
  }, [load, onError]);

  if (rows === null) return <p className="muted">Loading…</p>;

  return (
    <>
      <p className="muted">
        Cases where neither the deterministic checks nor the curated mistake
        library produced a diagnosis. Every one needs a human; the queue is in
        arrival order, with no severity ranking.
      </p>

      <label className="row" style={{ gap: 8 }}>
        <input
          type="checkbox"
          style={{ width: "auto" }}
          checked={unresolvedOnly}
          onChange={(e) => setUnresolvedOnly(e.target.checked)}
        />
        <span style={{ margin: 0 }}>Unresolved only</span>
      </label>

      {rows.length === 0 ? (
        <p className="muted">Nothing in the queue.</p>
      ) : (
        rows.map((r) => (
          <div className="card" key={r.id}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>{r.student_email}</strong>
              <span className="muted">
                {new Date(r.created_at).toLocaleString()}
              </span>
            </div>
            <p style={{ marginTop: 8 }}>{r.reason}</p>
            <p className="muted">
              Recomputed {r.expected_value ?? "—"} · reported{" "}
              {r.reported_value ?? "—"}
            </p>
            {!r.resolved && (
              <ActionButton
                variant="secondary"
                pendingLabel="Saving…"
                onAction={async () => {
                  try {
                    await api.post(`/api/dashboard/escalations/${r.id}/resolve`, {
                      note: "",
                    });
                    await load();
                  } catch (e) {
                    onError(e instanceof ApiError ? e.message : String(e));
                  }
                }}
              >
                Mark reviewed
              </ActionButton>
            )}
          </div>
        ))
      )}
    </>
  );
}

function Summaries({
  classroomId,
  onError,
}: {
  classroomId: string;
  onError: (m: string) => void;
}) {
  const [sessions, setSessions] = useState<ClassSessionInfo[] | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [rows, setRows] = useState<StudentSummary[] | null>(null);
  const [job, setJob] = useState<SummaryJob | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api
      .get<{ sessions: ClassSessionInfo[] }>(
        `/api/dashboard/classrooms/${classroomId}/sessions`,
      )
      .then((d) => {
        setSessions(d.sessions);
        setSessionId((current) => current || d.sessions[0]?.id || "");
      })
      .catch((e) => onError(e instanceof ApiError ? e.message : String(e)));
  }, [classroomId, onError]);

  const load = useCallback(async () => {
    if (!sessionId) {
      setRows([]);
      return;
    }
    const d = await api.get<{ summaries: StudentSummary[] }>(
      `/api/dashboard/classrooms/${classroomId}/sessions/${sessionId}/summaries`,
    );
    setRows(d.summaries);
  }, [classroomId, sessionId]);

  useEffect(() => {
    setRows(null);
    load().catch((e) => onError(e instanceof ApiError ? e.message : String(e)));
  }, [load, onError]);

  // Poll while a job is running. At ~70 students this takes long enough
  // that a blocking request would time out, hence the job + progress.
  useEffect(() => {
    if (!job || job.status === "done") {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const next = await api.get<SummaryJob>(
          `/api/dashboard/summaries/jobs/${job.job_id}`,
        );
        setJob(next);
        if (next.status === "done") await load();
      } catch {
        // Transient; the next tick retries.
      }
    }, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [job, load]);

  const running = job !== null && job.status !== "done";

  return (
    <>
      <p className="muted">
        A short read on how each student moved through the experiment — how
        much scaffolding they needed, whether they recovered on their own.
        This is not a grade, and students never see it.
      </p>

      <div className="card">
        <label style={{ maxWidth: 360 }}>
          <span>Class session</span>
          <select value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
            {(sessions ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.experiment_id} — {new Date(s.started_at).toLocaleString()}
                {s.status === "active" ? " (active)" : ""}
              </option>
            ))}
          </select>
        </label>

        <ActionButton
          disabled={running || !sessionId}
          pendingLabel="Starting…"
          onAction={async () => {
            try {
              const started = await api.post<SummaryJob>(
                `/api/dashboard/classrooms/${classroomId}/sessions/${sessionId}/summaries`,
                { refresh_student_ids: [], idempotency_key: newIdempotencyKey() },
              );
              setJob({ ...started, completed: 0, skipped: 0, error: null });
            } catch (e) {
              onError(e instanceof ApiError ? e.message : String(e));
            }
          }}
        >
          Generate summaries
        </ActionButton>

        {job && (
          <div style={{ marginTop: 12 }}>
            <div className="progress">
              <div
                style={{
                  width: `${
                    job.total ? ((job.completed + job.skipped) / job.total) * 100 : 0
                  }%`,
                }}
              />
            </div>
            <p className="muted" style={{ marginTop: 6, marginBottom: 0 }}>
              {job.status} — {job.completed} generated, {job.skipped} already
              done, of {job.total}.
              {job.skipped > 0 &&
                " Students already summarised are skipped, so re-running costs nothing."}
            </p>
          </div>
        )}
      </div>

      {rows === null ? (
        <p className="muted">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="muted">No summaries generated yet.</p>
      ) : (
        rows.map((s) => (
          <div className="card" key={s.student_id}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong>{s.student_email}</strong>
              {s.flagged && (
                <span className="pill pill-escalated">needs manual review</span>
              )}
            </div>
            {s.flagged && s.flag_reason && (
              <p className="muted" style={{ marginTop: 6 }}>
                Flagged: {s.flag_reason}
              </p>
            )}
            <p style={{ whiteSpace: "pre-line", marginTop: 8, marginBottom: 0 }}>
              {s.text}
            </p>
          </div>
        ))
      )}
    </>
  );
}

function Roster({
  classroomId,
  onError,
}: {
  classroomId: string;
  onError: (m: string) => void;
}) {
  const [students, setStudents] = useState<RosterStudent[] | null>(null);
  const [faculty, setFaculty] = useState<RosterFaculty[] | null>(null);

  const load = useCallback(async () => {
    const [s, f] = await Promise.all([
      api.get<{ students: RosterStudent[] }>(`/api/classrooms/${classroomId}/roster`),
      api.get<{ faculty: RosterFaculty[] }>(`/api/classrooms/${classroomId}/faculty`),
    ]);
    setStudents(s.students);
    setFaculty(f.faculty);
  }, [classroomId]);

  useEffect(() => {
    load().catch((e) => onError(e instanceof ApiError ? e.message : String(e)));
  }, [load, onError]);

  if (students === null || faculty === null) return <p className="muted">Loading…</p>;

  return (
    <>
      <p className="muted">
        Promoting a student makes them full faculty for this classroom only
        — their platform account stays a student everywhere else.
      </p>

      <h2>Faculty</h2>
      <div className="card">
        {faculty.length === 0 ? (
          <p className="muted">No faculty yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Joined</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {faculty.map((f) => (
                <tr key={f.id}>
                  <td>{f.name}</td>
                  <td className="mono">{f.email}</td>
                  <td>{new Date(f.joined_at).toLocaleString()}</td>
                  <td>
                    {f.promoted ? (
                      <>
                        <span className="pill" style={{ marginRight: 8 }}>
                          promoted co-faculty
                        </span>
                        <ActionButton
                          variant="secondary"
                          pendingLabel="Demoting…"
                          onAction={async () => {
                            try {
                              await api.post(`/api/classrooms/${classroomId}/demote`, {
                                user_id: f.id,
                              });
                              await load();
                            } catch (e) {
                              onError(e instanceof ApiError ? e.message : String(e));
                            }
                          }}
                        >
                          Demote to student
                        </ActionButton>
                      </>
                    ) : (
                      <span className="muted">platform faculty</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>Students</h2>
      <div className="card">
        {students.length === 0 ? (
          <p className="muted">No students yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Joined</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td className="mono">{s.email}</td>
                  <td>{new Date(s.joined_at).toLocaleString()}</td>
                  <td>
                    <ActionButton
                      variant="secondary"
                      pendingLabel="Promoting…"
                      onAction={async () => {
                        try {
                          await api.post(`/api/classrooms/${classroomId}/promote`, {
                            student_user_id: s.id,
                          });
                          await load();
                        } catch (e) {
                          onError(e instanceof ApiError ? e.message : String(e));
                        }
                      }}
                    >
                      Promote to co-faculty
                    </ActionButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function Coverage({
  classroomId,
  onError,
}: {
  classroomId: string;
  onError: (m: string) => void;
}) {
  const [rows, setRows] = useState<StudentCoverage[] | null>(null);

  useEffect(() => {
    api
      .get<{ students: StudentCoverage[] }>(`/api/dashboard/classrooms/${classroomId}/coverage`)
      .then((d) => setRows(d.students))
      .catch((e) => onError(e instanceof ApiError ? e.message : String(e)));
  }, [classroomId, onError]);

  if (rows === null) return <p className="muted">Loading…</p>;

  const experiments = Array.from(
    new Set(rows.flatMap((r) => r.topics.map((t) => t.experiment_id))),
  ).sort();

  return (
    <>
      <p className="muted">
        A rough, deterministic engagement indicator per experiment — not a
        grade. Computed from stored attempt/submission/diagnosis counts
        only; no model ever produces or adjusts this number.
      </p>
      {rows.length === 0 ? (
        <p className="muted">No students yet.</p>
      ) : experiments.length === 0 ? (
        <p className="muted">No recorded activity yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Student</th>
              {experiments.map((e) => (
                <th key={e}>{e}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.student_id}>
                <td>{r.student_name || r.student_email}</td>
                {experiments.map((e) => {
                  const t = r.topics.find((topic) => topic.experiment_id === e);
                  return (
                    <td key={e}>
                      {t ? (
                        <span
                          className={`pill ${
                            t.coverage_score >= 70
                              ? "pill-pass"
                              : t.coverage_score >= 40
                                ? ""
                                : "pill-fail"
                          }`}
                        >
                          {t.coverage_score}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
