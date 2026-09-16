/**
 * API client.
 *
 * Everything is same-origin `/api/*`: in the container stack Caddy routes
 * those to the backend, and in development a Next rewrite does. Cookies
 * are sent with every request because the session is an HttpOnly cookie
 * the JavaScript here cannot read — which is the point.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; the status text will do.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body ?? {}) }),
};

/**
 * A stable key for one action *instance*.
 *
 * Disabling a button on click is not enough on its own: a network retry,
 * a refresh mid-flight, or a second tab can still deliver the same action
 * twice. The server rejects or replays a duplicate key, so the worst case
 * of a double-fire is a repeated response rather than a duplicate row or
 * a second billed inference call.
 */
export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// --- shared response shapes ------------------------------------------------

export interface Me {
  id: string;
  email: string;
  name: string;
  role: "student" | "faculty" | "admin";
}

export interface Classroom {
  id: string;
  name: string;
  join_open?: boolean;
  /** Present only when the caller is faculty/admin (own section, or an
   * admin-listed one) -- a student's /enrolled view omits both codes. */
  student_join_code?: string;
  faculty_join_code?: string;
  active_experiment_id: string | null;
  active_session_id: string | null;
  student_count?: number;
}

export interface ActiveSessionInfo {
  active: boolean;
  session_id?: string;
  experiment_id?: string;
  started_at?: string;
}

export interface ClassSessionInfo {
  id: string;
  experiment_id: string;
  status: "active" | "ended";
  started_at: string;
  ended_at: string | null;
}

export interface Experiment {
  id: string;
  title: string;
  kind: string;
  ready: boolean;
  manual_reference: string;
}

export type TutorIntent =
  | "lab_question"
  | "safety_incident"
  | "safety_question"
  | "distress"
  | "off_scope";

export interface SocraticState {
  session_id: string;
  experiment_id: string;
  current_step: number;
  total_steps: number;
  prompt: string;
  complete: boolean;
  actor_type?: string;
}

export interface AttemptResult {
  passed: boolean;
  current_step: number;
  total_steps: number;
  message: string;
  hint_level: number;
  complete: boolean;
  prompt: string;
}

export interface SubmissionResult {
  submission_id: string;
  experiment_id: string;
  status: string;
  tier: number;
  action: string;
  explanation: string;
  citation: string;
  low_confidence: boolean;
}

// --- Q&A chat ---------------------------------------------------------------

export interface QaCitation {
  text: string;
  page: number;
  tier: string;
}

export interface QaAskResult {
  reply: string;
  status: string | null;
  citations: QaCitation[];
  answer_source: string;
  experiment_id: string | null;
  intent: TutorIntent;
}

export interface QaHistoryMessage {
  author: "student" | "tutor";
  content: string;
  experiment_id: string | null;
  created_at: string;
}

// --- faculty/admin dashboard -------------------------------------------------

export interface DashboardSubmission {
  submission_id: string;
  student_email: string;
  experiment_id: string;
  created_at: string;
  status: string;
  tier: number | null;
  signature: string | null;
  expected_value: number | null;
  reported_value: number | null;
  explanation: string;
  low_confidence: boolean;
}

export interface Escalation {
  id: string;
  student_email: string;
  reason: string;
  resolved: boolean;
  created_at: string;
  expected_value: number | null;
  reported_value: number | null;
}

export interface SummaryJob {
  job_id: string;
  status: string;
  total: number;
  completed: number;
  skipped: number;
  error: string | null;
}

export interface StudentSummary {
  student_id: string;
  student_email: string;
  experiment_id: string;
  text: string;
  flagged: boolean;
  flag_reason: string | null;
  generated_at: string;
}
