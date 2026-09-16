"use client";

import { Shell } from "@/components/Shell";

export default function HomePage() {
  return (
    <Shell>
      {(me) => (
        <>
          <h1>LabTutor</h1>
          <p className="muted">VIT Applied Chemistry Lab assistant</p>

          {me.role === "student" && (
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Your lab</h2>
              <p>
                Ask questions, work through the current experiment step by
                step, or submit a finished record for checking.
              </p>
              <div className="row">
                <a className="btn btn-primary" href="/student">
                  Open my lab
                </a>
              </div>
            </div>
          )}
          {me.role === "faculty" && (
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Your sections</h2>
              <p>
                Create and manage lab sections, start/end class sessions,
                and review submissions.
              </p>
              <div className="row">
                <a className="btn btn-primary" href="/faculty">
                  Open dashboard
                </a>
              </div>
            </div>
          )}
          {me.role === "admin" && (
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Administration</h2>
              <p>Create and manage every classroom across the platform.</p>
              <div className="row">
                <a className="btn btn-primary" href="/admin">
                  Open admin console
                </a>
              </div>
            </div>
          )}
        </>
      )}
    </Shell>
  );
}
