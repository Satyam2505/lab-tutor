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
  requireRole?: Me["role"];
  children: (me: Me) => React.ReactNode;
}) {
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
        <p className="muted">BACHY105 — Applied Chemistry Lab</p>
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

  if (requireRole && me.role !== requireRole) {
    return (
      <main>
        <h1>Not available</h1>
        <p className="muted">
          This page is for {requireRole === "faculty" ? "staff" : "students"}.
          You are signed in as {me.email}.
        </p>
        <a className="btn btn-secondary" href="/">
          Go back
        </a>
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
