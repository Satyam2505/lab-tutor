"use client";

import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import {
  ApiError,
  api,
  type AttemptResult,
  type SocraticState,
  type TutorIntent,
} from "@/lib/api";

interface Message {
  author: "student" | "tutor";
  content: string;
  /** Set on tutor turns that were triaged, so safety replies stand out. */
  intent?: TutorIntent;
}

/** Safety replies must not look like one more hint in the stream. */
function isUrgent(intent?: TutorIntent) {
  return intent === "safety_incident" || intent === "safety_question";
}

/**
 * The guided (Socratic) step-by-step panel. Shared by the student flow
 * (no `experimentId` -- server resolves it from the classroom's active
 * class session) and faculty/admin testing (`experimentId` set
 * explicitly, matching `POST /api/socratic/session`'s `experiment_id`
 * override for non-student callers -- see `backend/api/socratic_routes.py`).
 */
export function SocraticPanel({
  classroomId,
  experimentId,
}: {
  classroomId: string;
  experimentId?: string;
}) {
  const [state, setState] = useState<SocraticState | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [stepValue, setStepValue] = useState("");
  const [stepData, setStepData] = useState("");
  const [reveal, setReveal] = useState("");
  const [error, setError] = useState("");
  const [unavailable, setUnavailable] = useState("");

  const start = useCallback(async () => {
    try {
      const s = await api.post<SocraticState>("/api/socratic/session", {
        classroom_id: classroomId,
        ...(experimentId ? { experiment_id: experimentId } : {}),
      });
      setState(s);
      setUnavailable("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setUnavailable(e.message);
      } else {
        setError(e instanceof ApiError ? e.message : String(e));
      }
    }
  }, [classroomId, experimentId]);

  useEffect(() => {
    setState(null);
    setMessages([]);
    setReveal("");
    setError("");
    setUnavailable("");
    start();
  }, [start]);

  if (unavailable) {
    return (
      <>
        <h2>Guided mode</h2>
        <div className="notice">{unavailable}</div>
      </>
    );
  }

  if (!state) return <p className="muted">Loading guided mode…</p>;

  return (
    <>
      <h2>Guided mode</h2>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <strong>
            Step {Math.min(state.current_step + 1, state.total_steps)} of{" "}
            {state.total_steps}
          </strong>
          {state.complete && <span className="pill pill-pass">All steps verified</span>}
        </div>
        <div className="progress" style={{ margin: "10px 0 14px" }}>
          <div
            style={{
              width: `${(state.current_step / Math.max(state.total_steps, 1)) * 100}%`,
            }}
          />
        </div>

        {!state.complete && <p>{state.prompt}</p>}

        {error && <div className="error">{error}</div>}

        {!state.complete && (
          <>
            <label>
              <span>Your readings for this step (JSON, e.g. {"{"}&quot;titre_volume&quot;: 24.7{"}"})</span>
              <textarea
                rows={3}
                className="mono"
                value={stepData}
                onChange={(e) => setStepData(e.target.value)}
                placeholder='{"titre_volume": 24.7}'
              />
            </label>
            <label>
              <span>Your value for this step</span>
              <input
                value={stepValue}
                onChange={(e) => setStepValue(e.target.value)}
                placeholder="e.g. 24.7"
              />
            </label>
            <ActionButton
              disabled={!stepValue.trim()}
              pendingLabel="Checking…"
              onAction={async () => {
                setError("");
                let parsed: Record<string, unknown> = {};
                if (stepData.trim()) {
                  try {
                    parsed = JSON.parse(stepData);
                  } catch {
                    setError("Your readings are not valid JSON.");
                    return;
                  }
                }
                try {
                  const result = await api.post<AttemptResult>(
                    `/api/socratic/session/${state.session_id}/attempt`,
                    { data: parsed, value: stepValue.trim() },
                  );
                  setMessages((m) => [
                    ...m,
                    { author: "tutor", content: result.message },
                  ]);
                  setState({
                    ...state,
                    current_step: result.current_step,
                    total_steps: result.total_steps,
                    prompt: result.prompt,
                    complete: result.complete,
                  });
                  if (result.passed) setStepValue("");
                } catch (e) {
                  setError(e instanceof ApiError ? e.message : String(e));
                }
              }}
            >
              Check this step
            </ActionButton>
          </>
        )}

        {state.complete && (
          <>
            <p className="muted">
              Every step has been verified against your own data, so the
              computed result is available now.
            </p>
            <ActionButton
              pendingLabel="Fetching…"
              onAction={async () => {
                try {
                  const r = await api.post<{ reveal: string }>(
                    `/api/socratic/session/${state.session_id}/reveal`,
                  );
                  setReveal(r.reveal);
                } catch (e) {
                  setError(e instanceof ApiError ? e.message : String(e));
                }
              }}
            >
              Show the computed result
            </ActionButton>
            {reveal && <p style={{ marginTop: 12 }}>{reveal}</p>}
          </>
        )}
      </div>

      <div className="card">
        <strong>Ask about this step</strong>
        <p className="muted">
          The tutor can nudge you, but it does not have the final answer to
          give — it is never sent to it.
        </p>
        <div className="chat">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`msg msg-${m.author}${isUrgent(m.intent) ? " msg-urgent" : ""}`}
            >
              {isUrgent(m.intent) && <strong>Stop and get your demonstrator. </strong>}
              {m.content}
            </div>
          ))}
        </div>
        <label>
          <span>Your message</span>
          <textarea
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </label>
        <ActionButton
          disabled={!draft.trim()}
          pendingLabel="Sending…"
          onAction={async () => {
            const text = draft.trim();
            setDraft("");
            setMessages((m) => [...m, { author: "student", content: text }]);
            try {
              const r = await api.post<{ reply: string; intent: TutorIntent }>(
                `/api/socratic/session/${state.session_id}/message`,
                { message: text },
              );
              setMessages((m) => [
                ...m,
                { author: "tutor", content: r.reply, intent: r.intent },
              ]);
            } catch (e) {
              setMessages((m) => [
                ...m,
                {
                  author: "tutor",
                  content:
                    e instanceof ApiError ? e.message : "Something went wrong.",
                },
              ]);
            }
          }}
        >
          Send
        </ActionButton>
      </div>
    </>
  );
}
