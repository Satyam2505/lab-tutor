"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type Me } from "@/lib/api";

/**
 * Loads the signed-in identity and renders the page for it.
 *
 * The role shown here is presentation only. Every role-gated endpoint
 * re-checks the caller's role server-side on that request, so hiding a
 * button is a convenience, never the access control.
 */
export function Shell({
  requireRole,
  children,
}: {
  requireRole?: Me["role"] | Me["role"][];
  children: (me: Me) => React.ReactNode;
}) {
  const allowedRoles = requireRole
    ? Array.isArray(requireRole)
      ? requireRole
      : [requireRole]
    : null;
  const [me, setMe] = useState<Me | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "anonymous">("loading");

  useEffect(() => {
    let cancelled = false;
    api
      .get<Me>("/api/auth/me")
      .then((identity) => {
        if (cancelled) return;
        setMe(identity);
        setState("ready");
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          setState("anonymous");
        } else {
          setState("anonymous");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "loading") {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  if (state === "anonymous" || !me) {
    return (
      <main>
        <h1>LabTutor</h1>
        <p className="muted">VIT Applied Chemistry Lab assistant</p>
        <div className="card">
          <p>Sign in with your institutional Google account to continue.</p>
          <p className="muted">
            Access is limited to registered student and staff domains. Your
            role is determined from your email address by the server.
          </p>
          <a className="btn btn-primary" href="/api/auth/login">
            Sign in with Google
          </a>
        </div>
      </main>
    );
  }

  if (allowedRoles && !allowedRoles.includes(me.role)) {
    return (
      <main>
        <h1>Not available</h1>
        <p className="muted">
          This page is for {allowedRoles.join(" or ")}. You are signed in as{" "}
          {me.email} ({me.role}).
        </p>
        <a className="btn btn-secondary" href="/">
          Go back
        </a>
      </main>
    );
  }

  if (!me.profile_complete) {
    return (
      <main>
        <h1>Finish setting up your account</h1>
        <ProfileCompletionForm me={me} onDone={setMe} />
      </main>
    );
  }

  return (
    <>
      <header className="bar">
        <strong>LabTutor</strong>
        <span className="muted">
          {me.email} · {me.role}
        </span>
      </header>
      <main>{children(me)}</main>
    </>
  );
}

function ProfileCompletionForm({
  me,
  onDone,
}: {
  me: Me;
  onDone: (me: Me) => void;
}) {
  const [name, setName] = useState(me.name ?? "");
  const [regNo, setRegNo] = useState(me.reg_no ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  // Optional for students, never asked of faculty/admin -- it's stored
  // if given, but never blocks onboarding.
  const showRegNo = me.role === "student";

  return (
    <div className="card">
      {error && <div className="error">{error}</div>}
      <p className="muted">
        Signed in as {me.email}. What should we call you?
      </p>
      <label>
        <span>Full name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {showRegNo && (
        <label>
          <span>Registration number (optional)</span>
          <input value={regNo} onChange={(e) => setRegNo(e.target.value)} className="mono" />
        </label>
      )}
      <button
        className="btn btn-primary"
        disabled={saving || !name.trim()}
        onClick={async () => {
          setSaving(true);
          setError("");
          try {
            const updated = await api.post<Me>("/api/auth/complete-profile", {
              name: name.trim(),
              reg_no: showRegNo ? regNo.trim() || null : null,
            });
            onDone(updated);
          } catch (e) {
            setError(e instanceof ApiError ? e.message : String(e));
          } finally {
            setSaving(false);
          }
        }}
      >
        {saving ? "Saving…" : "Continue"}
      </button>
    </div>
  );
}
