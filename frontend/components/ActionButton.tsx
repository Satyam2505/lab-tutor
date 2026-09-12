"use client";

import { useCallback, useRef, useState } from "react";

/**
 * A button that fires exactly once per press.
 *
 * It disables itself synchronously on click and stays disabled until the
 * action settles. The `inFlight` ref matters as much as the state: a
 * second click in the same tick would otherwise slip through before React
 * re-rendered with the disabled attribute set.
 *
 * This is the client half of the single-fire rule. The server half — an
 * idempotency key on every state-changing endpoint — is what actually
 * guarantees it, because nothing here survives a network retry or a
 * second tab.
 */
export function ActionButton({
  onAction,
  children,
  pendingLabel = "Working…",
  variant = "primary",
  disabled = false,
  confirm,
}: {
  onAction: () => Promise<void>;
  children: React.ReactNode;
  pendingLabel?: string;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  confirm?: string;
}) {
  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);

  const handleClick = useCallback(async () => {
    if (inFlight.current) return;
    if (confirm && !window.confirm(confirm)) return;

    inFlight.current = true;
    setPending(true);
    try {
      await onAction();
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }, [onAction, confirm]);

  return (
    <button
      type="button"
      className={`btn btn-${variant}`}
      onClick={handleClick}
      disabled={pending || disabled}
      aria-busy={pending}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
