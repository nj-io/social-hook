"use client";

import type { ReactNode } from "react";

interface NoteProps {
  children: ReactNode;
  /** Visual variant. Default: "warning" (amber/yellow). */
  variant?: "warning" | "info" | "success" | "error";
  /** Optional className override */
  className?: string;
}

const VARIANTS = {
  warning:
    "bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-400",
  info: "bg-blue-50 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400",
  success:
    "bg-green-50 text-green-800 dark:bg-green-900/20 dark:text-green-400",
  error: "bg-red-50 text-red-800 dark:bg-red-900/20 dark:text-red-400",
};

/**
 * Inline note/callout for settings panels and wizards.
 *
 * Usage:
 *   <Note>Some warning text</Note>
 *   <Note variant="info">Informational note</Note>
 *   <Note variant="error">Something went wrong</Note>
 */
export function Note({ children, variant = "warning", className }: NoteProps) {
  return (
    <div
      className={`rounded-md p-3 text-sm ${VARIANTS[variant]} ${className ?? ""}`}
    >
      {children}
    </div>
  );
}
