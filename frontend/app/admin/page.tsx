"use client";

import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Shell } from "@/components/Shell";
import { ApiError, api, newIdempotencyKey, type AdminUser, type Classroom } from "@/lib/api";

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

      <UserRoleManager />
    </>
  );
}

function UserRoleManager() {
  const [query, setQuery] = useState("");
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState("");

  const search = useCallback(async (q: string) => {
    const data = await api.get<{ users: AdminUser[] }>(
      `/api/admin/users?q=${encodeURIComponent(q)}`,
    );
    setUsers(data.users);
  }, []);

  useEffect(() => {
    search("").catch((e) => setError(String(e.message ?? e)));
  }, [search]);

  return (
    <>
      <h2>Users — change anyone's role</h2>
      <div className="card">
        {error && <div className="error">{error}</div>}
        <label>
          <span>Search by name or email</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") search(query).catch((err) => setError(String(err)));
            }}
            placeholder="name or email"
          />
        </label>
        <ActionButton
          pendingLabel="Searching…"
          onAction={async () => {
            setError("");
            await search(query);
          }}
        >
          Search
        </ActionButton>
      </div>

      {users && (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <UserRoleRow
                key={u.id}
                user={u}
                onChanged={() => search(query).catch((err) => setError(String(err)))}
                onError={setError}
              />
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function UserRoleRow({
  user,
  onChanged,
  onError,
}: {
  user: AdminUser;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [role, setRole] = useState(user.role);

  return (
    <tr>
      <td>{user.name}</td>
      <td className="mono">{user.email}</td>
      <td>
        <select value={role} onChange={(e) => setRole(e.target.value as AdminUser["role"])}>
          <option value="student">student</option>
          <option value="faculty">faculty</option>
          <option value="admin">admin</option>
        </select>
      </td>
      <td>
        <div className="row" style={{ gap: 8 }}>
          <ActionButton
            disabled={role === user.role}
            pendingLabel="Updating…"
            onAction={async () => {
              try {
                await api.patch(`/api/admin/users/${user.id}/role`, { role });
                onChanged();
              } catch (e) {
                onError(e instanceof ApiError ? e.message : String(e));
              }
            }}
          >
            Update role
          </ActionButton>
          {user.role_override !== null && (
            <ActionButton
              variant="secondary"
              pendingLabel="Clearing…"
              onAction={async () => {
                try {
                  await api.del(`/api/admin/users/${user.id}/role-override`);
                  onChanged();
                } catch (e) {
                  onError(e instanceof ApiError ? e.message : String(e));
                }
              }}
            >
              Clear override
            </ActionButton>
          )}
        </div>
      </td>
    </tr>
  );
}
