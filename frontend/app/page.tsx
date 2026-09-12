"use client";

import { Shell } from "@/components/Shell";

export default function HomePage() {
  return (
    <Shell>
      {(me) => (
        <>
          <h1>LabTutor</h1>
          <p className="muted">BACHY105 — Applied Chemistry Lab</p>

          {me.role === "student" ? (
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Your lab</h2>
              <p>
                Work through the current experiment step by step, or submit a
                finished record for checking.
              </p>
              <div className="row">
                <a className="btn btn-primary" href="/student">
                  Open my lab
                </a>
              </div>
            </div>
          ) : (
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Your sections</h2>
              <p>
                Create and manage lab sections, set the week&rsquo;s active
                experiment, and review submissions.
              </p>
              <div className="row">
                <a className="btn btn-primary" href="/faculty">
                  Open dashboard
                </a>
              </div>
            </div>
          )}
        </>
      )}
    </Shell>
  );
}
