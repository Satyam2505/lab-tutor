"use client";

import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Shell } from "@/components/Shell";
import {
  ApiError,
  api,
  newIdempotencyKey,
  type Classroom,
  type Experiment,
} from "@/lib/api";

export default function FacultyPage() {
  return <Shell requireRole="faculty">{() => <Sections />}</Shell>;
}

function Sections() {
  const [classrooms, setClassrooms] = useState<Classroom[] | null>(null);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [mine, exps] = await Promise.all([
      api.get<{ classrooms: Classroom[] }>("/api/classrooms/mine"),
      api.get<{ experiments: Experiment[] }>("/api/classrooms/experiments"),
    ]);
    setClassrooms(mine.classrooms);
    setExperiments(exps.experiments);
  }, []);

  useEffect(() => {
    load().catch((e) => setError(String(e.message ?? e)));
  }, [load]);

  if (classrooms === null) return <p className="muted">Loading…</p>;

  const notReady = experiments.filter((e) => !e.ready);

  return (
    <>
      <h1>Lab sections</h1>
      {error && <div className="error">{error}</div>}

      {notReady.length > 0 && (
        <div className="notice">
          {notReady.length} of {experiments.length} experiments have no
          transcribed formulas yet ({notReady.map((e) => e.id).join(", ")}).
          Submissions against those are sent to the review queue rather than
          diagnosed.
        </div>
      )}

      <div className="card">
        <label>
          <span>New section name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Tuesday B1"
          />
        </label>
        <ActionButton
          disabled={!name.trim()}
          pendingLabel="Creating…"
          onAction={async () => {
            try {
              await api.post("/api/classrooms", {
                name: name.trim(),
                idempotency_key: newIdempotencyKey(),
              });
              setName("");
              setError("");
              await load();
            } catch (e) {
              setError(e instanceof ApiError ? e.message : String(e));
            }
          }}
        >
          Create section
        </ActionButton>
      </div>

      {classrooms.map((classroom) => (
        <SectionCard
          key={classroom.id}
          classroom={classroom}
          experiments={experiments}
          onChanged={load}
          onError={setError}
        />
      ))}
    </>
  );
}

function SectionCard({
  classroom,
  experiments,
  onChanged,
  onError,
}: {
  classroom: Classroom;
  experiments: Experiment[];
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [pendingExperiment, setPendingExperiment] = useState(
    experiments.find((e) => e.ready)?.id ?? "",
  );
  const hasActiveSession = Boolean(classroom.active_session_id);

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong>{classroom.name}</strong>
        <span className="muted">{classroom.student_count ?? 0} students</span>
      </div>

      <p className="muted" style={{ marginTop: 8 }}>
        Student code: <span className="mono">{classroom.student_join_code}</span>
        {" · "}
        Faculty code: <span className="mono">{classroom.faculty_join_code}</span>
        {" · "}
        {classroom.join_open ? "open" : "closed"}
      </p>

      {hasActiveSession ? (
        <>
          <p>
            Class session active: <strong>{classroom.active_experiment_id}</strong>
          </p>
          <ActionButton
            variant="secondary"
            pendingLabel="Ending…"
            confirm="End this class session? Students will no longer be able to ask questions, get hints, or submit for this classroom until a new session starts."
            onAction={async () => {
              try {
                await api.post(
                  `/api/classrooms/${classroom.id}/sessions/${classroom.active_session_id}/end`,
                );
                await onChanged();
              } catch (e) {
                onError(e instanceof ApiError ? e.message : String(e));
              }
            }}
          >
            End class
          </ActionButton>
        </>
      ) : (
        <>
          <label>
            <span>Experiment to start</span>
            <select
              value={pendingExperiment}
              onChange={(e) => setPendingExperiment(e.target.value)}
            >
              <option value="">— choose —</option>
              {experiments.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.id} — {e.title}
                  {e.ready ? "" : " (not configured)"}
                </option>
              ))}
            </select>
          </label>
          <ActionButton
            disabled={!pendingExperiment}
            pendingLabel="Starting…"
            onAction={async () => {
              try {
                await api.post(`/api/classrooms/${classroom.id}/sessions/start`, {
                  experiment_id: pendingExperiment,
                });
                await onChanged();
              } catch (e) {
                onError(e instanceof ApiError ? e.message : String(e));
              }
            }}
          >
            Start class
          </ActionButton>
        </>
      )}

      <div className="row" style={{ marginTop: 10 }}>
        <ActionButton
          variant="secondary"
          pendingLabel="Saving…"
          confirm={
            classroom.join_open
              ? "Close joining for this section? Students who have not joined yet will not be able to."
              : undefined
          }
          onAction={async () => {
            try {
              await api.patch(`/api/classrooms/${classroom.id}/join-open`, {
                join_open: !classroom.join_open,
              });
              await onChanged();
            } catch (e) {
              onError(e instanceof ApiError ? e.message : String(e));
            }
          }}
        >
          {classroom.join_open ? "Close joining" : "Reopen joining"}
        </ActionButton>

        <a className="btn btn-secondary" href={`/faculty/${classroom.id}`}>
          Open dashboard
        </a>
      </div>
    </div>
  );
}
