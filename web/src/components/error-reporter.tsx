"use client";

import { useEffect } from "react";
import { reportFrontendError } from "@/lib/api";

/**
 * Captures uncaught frontend errors and reports them to the backend.
 * Mount once in the root layout.
 */
export function ErrorReporter() {
  useEffect(() => {
    function handleError(event: ErrorEvent) {
      try {
        reportFrontendError({
          severity: "error",
          message: event.message || "Uncaught error",
          source: "frontend",
          context: {
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno,
          },
        });
      } catch {
        // Silent — never recurse
      }
    }

    function handleRejection(event: PromiseRejectionEvent) {
      try {
        const reason = event.reason;
        const message =
          reason instanceof Error ? reason.message : String(reason ?? "Unhandled promise rejection");
        reportFrontendError({
          severity: "error",
          message,
          source: "frontend",
          context: {
            type: "unhandledrejection",
            stack: reason instanceof Error ? reason.stack : undefined,
          },
        });
      } catch {
        // Silent — never recurse
      }
    }

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);
    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  }, []);

  return null;
}
