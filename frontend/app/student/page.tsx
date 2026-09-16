"use client";

import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { QaChat } from "@/components/QaChat";
import { Shell } from "@/components/Shell";
import { SocraticPanel } from "@/components/SocraticPanel";
import { SubmitPanel } from "@/components/SubmitPanel";
import { ApiError, api, newIdempotencyKey, type Classroom } from "@/lib/api";

export default function StudentPage() {
  return <Shell requireRole="student">{() => <StudentLab />}</Shell>;
}

function StudentLab() {
  const [classrooms, setClassrooms] = useState<Classroom[] | null>(null);
  const [selected, setSelected] = useState<Classroom | null>(null);
  const [error, setError] = useState("");
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const loadClassrooms = useCallback(async () => {
    const data = await api.get<{ classrooms: Classroom[] }>(
      "/api/classrooms/enrolled",
    );
    setClassrooms(data.classrooms);
    setSelected((current) =>
      current ? data.classrooms.find((c) => c.id === current.id) ?? null : data.classrooms[0] ?? null,
    );
  }, []);

  useEffect(() => {
    loadClassrooms().catch((e) => setError(String(e.message ?? e)));
  }, [loadClassrooms]);

  if (classrooms === null) {
    return error ? <div className="error">{error}</div> : <p className="muted">Loading…</p>;
  }

  return (
    <>
      <h1>My lab</h1>
      {error && <div className="error">{error}</div>}

      <JoinClassroom
        onJoined={async () => {
          setError("");
          await loadClassrooms();
        }}
        onError={setError}
      />

      {classrooms.length === 0 ? (
        <p className="muted">
          You are not in a section yet. Enter the join code your demonstrator
          gave you.
        </p>
      ) : (
        <>
          <h2>Section</h2>
          <div className="card">
            <label>
              <span>Your sections</span>
              <select
                value={selected?.id ?? ""}
                onChange={(e) =>
                  setSelected(
                    classrooms.find((c) => c.id === e.target.value) ?? null,
                  )
                }
              >
                {classrooms.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.co_faculty ? " (co-faculty)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <p className="muted" style={{ marginBottom: 0 }}>
              {selected?.active_experiment_id
                ? `Active experiment: ${selected.active_experiment_id}. Your work is tagged with this automatically.`
                : "Your demonstrator has not set this week's experiment yet."}
            </p>
            {selected?.co_faculty && (
              <p style={{ marginTop: 10, marginBottom: 0 }}>
                <span className="pill" style={{ marginRight: 8 }}>
                  promoted co-faculty for this section
                </span>
                <a className="btn btn-secondary" href={`/faculty/${selected.id}`}>
                  Open faculty dashboard
                </a>
              </p>
            )}
          </div>

          {selected?.active_experiment_id && (
            <>
              <QaChat classroomId={selected.id} />
              <SocraticPanel classroomId={selected.id} />
              <SubmitPanel
                classroomId={selected.id}
                onSubmitted={() => setHistoryRefreshKey((k) => k + 1)}
              />
              <HistoryPanel refreshKey={historyRefreshKey} />
            </>
          )}
        </>
      )}
    </>
  );
}

interface SubmissionHistoryRow {
  id: string;
  experiment_id: string;
  created_at: string;
  status: string;
  explanation: string;
}

function HistoryPanel({ refreshKey }: { refreshKey: number }) {
  const [rows, setRows] = useState<SubmissionHistoryRow[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<{ submissions: SubmissionHistoryRow[] }>("/api/submissions/mine")
      .then((d) => setRows(d.submissions))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [refreshKey]);

  return (
    <>
      <h2>My submission history</h2>
      <div className="card">
        {error && <div className="error">{error}</div>}
        {rows === null ? (
          <p className="muted">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="muted">No submissions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Experiment</th>
                <th>Status</th>
                <th>Submitted</th>
                <th>Explanation</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.experiment_id}</td>
                  <td>
                    <span className={`pill pill-${r.status}`}>{r.status}</span>
                  </td>
                  <td>{new Date(r.created_at).toLocaleString()}</td>
                  <td>{r.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function JoinClassroom({
  onJoined,
  onError,
}: {
  onJoined: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [code, setCode] = useState("");

  return (
    <div className="card">
      <label>
        <span>Join code</span>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="ABCDE-FGHIJ-KLMNO-PQRST"
          className="mono"
        />
      </label>
      <ActionButton
        disabled={!code.trim()}
        pendingLabel="Joining…"
        onAction={async () => {
          try {
            // A fresh key per press: this is one action instance, so a
            // retry of *this* press collapses, but a later deliberate
            // press is a new action.
            await api.post("/api/classrooms/join", {
              join_code: code.trim(),
              idempotency_key: newIdempotencyKey(),
            });
            setCode("");
            await onJoined();
          } catch (e) {
            onError(e instanceof ApiError ? e.message : String(e));
          }
        }}
      >
        Join section
      </ActionButton>
    </div>
  );
}
