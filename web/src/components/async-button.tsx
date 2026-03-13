"use client";

import { useEffect, useState, type ReactNode } from "react";

/** Self-updating elapsed time counter. Uses tabular-nums to prevent layout shift. */
export function ElapsedTime({ startTime }: { startTime: string }) {
  const [elapsed, setElapsed] = useState(() =>
    Math.max(0, Math.floor((Date.now() - new Date(startTime).getTime()) / 1000)),
  );

  useEffect(() => {
    const start = new Date(startTime).getTime();
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [startTime]);

  if (elapsed < 1) return null;

  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;

  return (
    <span className="tabular-nums opacity-70">
      {minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`}
    </span>
  );
}

/** Inline spinner matching the existing codebase SVG pattern. */
export function Spinner({ className = "h-3 w-3" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

interface AsyncButtonProps {
  loading: boolean;
  startTime?: string | null;
  loadingText?: string;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
}

/** Drop-in button that shows a spinner + elapsed time counter when loading. */
export function AsyncButton({
  loading,
  startTime,
  loadingText,
  children,
  className = "",
  disabled,
  onClick,
}: AsyncButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={className}
    >
      {loading ? (
        <span className="inline-flex items-center gap-1.5">
          <Spinner />
          {loadingText && <span>{loadingText}</span>}
          {startTime && <ElapsedTime startTime={startTime} />}
        </span>
      ) : (
        children
      )}
    </button>
  );
}
