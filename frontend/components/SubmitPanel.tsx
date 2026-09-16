"use client";

import { useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { ApiError, api, newIdempotencyKey, type SubmissionResult } from "@/lib/api";

/**
 * The finished-record submission/diagnostic panel. Shared by the student
 * flow (no `experimentId` -- server resolves it from the classroom's
 * active class session) and faculty/admin diagnostic testing
 * (`experimentId` set explicitly -- see `POST /api/submissions`'s
 * `experiment_id` override for non-student callers in
 * `backend/api/diagnostic_routes.py`).
 */
export function SubmitPanel({
  classroomId,
  experimentId,
  title = "Submit a finished record",
  onSubmitted,
}: {
  classroomId: string;
  experimentId?: string;
  title?: string;
  /** Called after a submission is recorded (pass/fail/escalated/invalid
   * all count -- the row exists either way), so a sibling history view can
   * refresh instead of going stale until the next full page load. */
  onSubmitted?: () => void;
}) {
  const [data, setData] = useState("");
  const [reported, setReported] = useState("");
  const [remarks, setRemarks] = useState("");
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [error, setError] = useState("");

  return (
    <>
      <h2>{title}</h2>
      <div className="card">
        {error && <div className="error">{error}</div>}

        <label>
          <span>Readings (JSON)</span>
          <textarea
            rows={5}
            className="mono"
            value={data}
            onChange={(e) => setData(e.target.value)}
            placeholder='{"standard_normality": 0.1, "standard_volume": 25.0, "titre_volume": 20.0}'
          />
        </label>
        <label>
          <span>Reported result</span>
          <input value={reported} onChange={(e) => setReported(e.target.value)} />
        </label>
        <label>
          <span>Remarks (anything unusual about the run)</span>
          <textarea
            rows={2}
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
          />
        </label>

        <ActionButton
          disabled={!data.trim()}
          pendingLabel="Checking…"
          onAction={async () => {
            setError("");
            setResult(null);
            let parsed: Record<string, unknown>;
            try {
              parsed = JSON.parse(data);
            } catch {
              setError("Readings are not valid JSON.");
              return;
            }
            try {
              const r = await api.post<SubmissionResult>("/api/submissions", {
                classroom_id: classroomId,
                data: parsed,
                reported_value: reported.trim() || null,
                remarks,
                ...(experimentId ? { experiment_id: experimentId } : {}),
                idempotency_key: newIdempotencyKey(),
              });
              setResult(r);
              onSubmitted?.();
            } catch (e) {
              setError(e instanceof ApiError ? e.message : String(e));
            }
          }}
        >
          Submit for checking
        </ActionButton>

        {result && (
          <div style={{ marginTop: 16 }}>
            <span className={`pill pill-${result.status}`}>{result.status}</span>
            {result.low_confidence && (
              <span className="pill pill-escalated" style={{ marginLeft: 6 }}>
                low confidence
              </span>
            )}
            <p style={{ marginTop: 10 }}>{result.explanation}</p>
            {result.citation && <p className="muted">{result.citation}</p>}
          </div>
        )}
      </div>
    </>
  );
}
