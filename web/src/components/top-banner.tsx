"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

interface TopBannerProps {
  visible: boolean;
  onDismiss: () => void;
  children: ReactNode;
  onDismissForever?: () => void;
  dismissForeverLabel?: string;
}

/**
 * Fixed top-center notification banner with slide-in/fade-out animation.
 *
 * Visibility is controlled by the parent. The banner provides an X button
 * (calls onDismiss) and an optional "don't show again" link (calls onDismissForever).
 * Dark-themed to match existing toast styling.
 */
export function TopBanner({
  visible,
  onDismiss,
  children,
  onDismissForever,
  dismissForeverLabel = "Don\u2019t show again",
}: TopBannerProps) {
  const [mounted, setMounted] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  // Mount when visible becomes true; unmount after fade-out completes
  useEffect(() => {
    if (visible) {
      setMounted(true);
      setDismissing(false);
    }
  }, [visible]);

  const handleDismiss = useCallback((callback: () => void) => {
    setDismissing(true);
    setTimeout(() => {
      setMounted(false);
      setDismissing(false);
      callback();
    }, 200);
  }, []);

  if (!mounted) return null;

  return (
    <div className="fixed top-4 left-1/2 z-50 -translate-x-1/2">
      <div
        className={`rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 shadow-lg transition-opacity duration-200 ${
          dismissing ? "opacity-0" : "animate-in slide-in-from-top opacity-100"
        }`}
      >
        <div className="flex items-center gap-3">
          <div className="text-sm text-zinc-100">{children}</div>
          {onDismissForever && (
            <button
              onClick={() => handleDismiss(onDismissForever)}
              className="shrink-0 text-xs text-zinc-500 transition-colors hover:text-zinc-200"
            >
              {dismissForeverLabel}
            </button>
          )}
          <button
            onClick={() => handleDismiss(onDismiss)}
            className="shrink-0 text-zinc-400 transition-colors hover:text-zinc-100"
            aria-label="Dismiss"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
