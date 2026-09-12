"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Shell } from "@/components/Shell";
import {
  ApiError,
  api,
  newIdempotencyKey,
  type DashboardSubmission,
  type Escalation,
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
    <Shell requireRole="faculty">{() => <Dashboard classroomId={classroomId} />}</Shell>
  );
}

type Tab = "submissions" | "escalations" | "summaries";

function Dashboard({ classroomId }: { classroomId: string }) {
  const [tab, setTab] = useState<Tab>("submissions");
  const [error, setError] = useState("");

  return (
    <>
      <h1>Section dashboard</h1>
      <p className="muted">
        <a href="/faculty">← all sections</a>
      </p>

      {error && <div className="error">{error}</div>}

      <div className="row" style={{ marginBottom: 14 }}>
        {(["submissions", "escalations", "summaries"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            className={`btn ${tab === t ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setTab(t)}
          >
            {t === "escalations" ? "Review queue" : t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "submissions" && (
        <Submissions classroomId={classroomId} onError={setError} />
      )}
      {tab === "escalations" && (
        <Escalations classroomId={classroomId} onError={setError} />
      )}
      {tab === "summaries" && (
        <Summaries classroomId={classroomId} onError={setError} />
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
  const [rows, setRows] = useState<StudentSummary[] | null>(null);
  const [job, setJob] = useState<SummaryJob | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    const d = await api.get<{ summaries: StudentSummary[] }>(
      `/api/dashboard/classrooms/${classroomId}/summaries`,
    );
    setRows(d.summaries);
  }, [classroomId]);

  useEffect(() => {
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
        <ActionButton
          disabled={running}
          pendingLabel="Starting…"
          onAction={async () => {
            try {
              const started = await api.post<SummaryJob>(
                `/api/dashboard/classrooms/${classroomId}/summaries`,
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
