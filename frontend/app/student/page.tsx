"use client";

import { useCallback, useEffect, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { Shell } from "@/components/Shell";
import {
  ApiError,
  api,
  newIdempotencyKey,
  type AttemptResult,
  type Classroom,
  type SocraticState,
  type SubmissionResult,
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

export default function StudentPage() {
  return <Shell requireRole="student">{() => <StudentLab />}</Shell>;
}

function StudentLab() {
  const [classrooms, setClassrooms] = useState<Classroom[] | null>(null);
  const [selected, setSelected] = useState<Classroom | null>(null);
  const [error, setError] = useState("");

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

  if (classrooms === null) return <p className="muted">Loading…</p>;

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
                  </option>
                ))}
              </select>
            </label>
            <p className="muted" style={{ marginBottom: 0 }}>
              {selected?.active_experiment_id
                ? `Active experiment: ${selected.active_experiment_id}. Your work is tagged with this automatically.`
                : "Your demonstrator has not set this week's experiment yet."}
            </p>
          </div>

          {selected?.active_experiment_id && (
            <>
              <SocraticPanel classroom={selected} />
              <SubmitPanel classroom={selected} />
            </>
          )}
        </>
      )}
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

function SocraticPanel({ classroom }: { classroom: Classroom }) {
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
        classroom_id: classroom.id,
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
  }, [classroom.id]);

  useEffect(() => {
    setState(null);
    setMessages([]);
    setReveal("");
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

function SubmitPanel({ classroom }: { classroom: Classroom }) {
  const [data, setData] = useState("");
  const [reported, setReported] = useState("");
  const [remarks, setRemarks] = useState("");
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [error, setError] = useState("");

  return (
    <>
      <h2>Submit a finished record</h2>
      <div className="card">
        {error && <div className="error">{error}</div>}

        <label>
          <span>Your readings (JSON)</span>
          <textarea
            rows={5}
            className="mono"
            value={data}
            onChange={(e) => setData(e.target.value)}
            placeholder='{"standard_normality": 0.1, "standard_volume": 25.0, "titre_volume": 20.0}'
          />
        </label>
        <label>
          <span>Your reported result</span>
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
              setError("Your readings are not valid JSON.");
              return;
            }
            try {
              const r = await api.post<SubmissionResult>("/api/submissions", {
                classroom_id: classroom.id,
                data: parsed,
                reported_value: reported.trim() || null,
                remarks,
                idempotency_key: newIdempotencyKey(),
              });
              setResult(r);
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
