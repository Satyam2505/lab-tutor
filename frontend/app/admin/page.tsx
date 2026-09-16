"use client";

import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Shell } from "@/components/Shell";
import { ApiError, api, newIdempotencyKey, type Classroom } from "@/lib/api";

export default function AdminPage() {
  return <Shell requireRole="admin">{() => <AdminConsole />}</Shell>;
}

function AdminConsole() {
  const [classrooms, setClassrooms] = useState<Classroom[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const data = await api.get<{ classrooms: Classroom[] }>("/api/classrooms");
    setClassrooms(data.classrooms);
  }, []);

  useEffect(() => {
    load().catch((e) => setError(String(e.message ?? e)));
  }, [load]);

  if (classrooms === null) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Admin console</h1>
      <p className="muted">
        Every classroom on the platform, with global authority — no
        membership needed to view or open any of them.
      </p>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <label>
          <span>New classroom name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Section name"
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
          Create classroom
        </ActionButton>
      </div>

      {classrooms.length === 0 ? (
        <p className="muted">No classrooms yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Students</th>
              <th>Active experiment</th>
              <th>Student code</th>
              <th>Faculty code</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {classrooms.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.student_count ?? 0}</td>
                <td>{c.active_experiment_id ?? "—"}</td>
                <td className="mono">{c.student_join_code}</td>
                <td className="mono">{c.faculty_join_code}</td>
                <td>
                  <a className="btn btn-secondary" href={`/faculty/${c.id}`}>
                    Open dashboard
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
