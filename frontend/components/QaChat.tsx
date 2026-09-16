"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ActionButton } from "@/components/ActionButton";
import { ApiError, api, type QaAskResult, type QaHistoryMessage } from "@/lib/api";

interface DisplayMessage {
  author: "student" | "tutor";
  content: string;
  citations?: QaAskResult["citations"];
  status?: string | null;
}

/**
 * The Q&A chat surface shared by students and faculty (brief item 1:
 * "Students and faculty must use the SAME LabTutor system"). Renders
 * citations distinctly from prose so a grounded answer never looks like
 * an unsourced claim, and never renders raw JSON to a student.
 */
export function QaChat({ classroomId }: { classroomId: string }) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      const data = await api.get<{ messages: QaHistoryMessage[] }>(
        `/api/qa/history?classroom_id=${encodeURIComponent(classroomId)}`,
      );
      setMessages(
        data.messages.map((m) => ({ author: m.author, content: m.content })),
      );
    } catch {
      // History is a convenience; a failure here shouldn't block asking.
    } finally {
      setLoaded(true);
    }
  }, [classroomId]);

  useEffect(() => {
    setLoaded(false);
    setMessages([]);
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages]);

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    setError("");
    setMessages((m) => [...m, { author: "student", content: text }]);
    try {
      const result = await api.post<QaAskResult>("/api/qa/ask", {
        classroom_id: classroomId,
        message: text,
      });
      setMessages((m) => [
        ...m,
        {
          author: "tutor",
          content: result.reply,
          citations: result.citations,
          status: result.status,
        },
      ]);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 409 || e.status === 404)) {
        setError(e.message);
        return;
      }
      setMessages((m) => [
        ...m,
        {
          author: "tutor",
          content: e instanceof ApiError ? e.message : "Something went wrong.",
        },
      ]);
    }
  }, [classroomId, draft]);

  return (
    <div className="card">
      <strong>Ask LabTutor</strong>
      <p className="muted">
        Theory, procedure, calculations, troubleshooting — grounded in the
        manual, with citations. This never reveals a final computed answer
        for your own submitted data.
      </p>

      {error && <div className="error">{error}</div>}

      <div className="chat">
        {!loaded && <p className="muted">Loading…</p>}
        {loaded && messages.length === 0 && (
          <p className="muted">No messages yet — ask something below.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg msg-${m.author}`}>
            {m.content}
            {m.citations && m.citations.length > 0 && (
              <div className="muted" style={{ marginTop: 6, fontSize: "0.85em" }}>
                {m.citations.map((c, ci) => (
                  <div key={ci}>{c.text}</div>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <label>
        <span>Your question</span>
        <textarea
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
      </label>
      <ActionButton disabled={!draft.trim()} pendingLabel="Sending…" onAction={send}>
        Ask
      </ActionButton>
    </div>
  );
}
