"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

interface Toast {
  id: string;
  message: string;
  detail?: string;
  variant: "success" | "error" | "info";
  ts: number;
}

interface ToastContextValue {
  addToast: (message: string, opts?: { detail?: string; variant?: "success" | "error" | "info" }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TOAST_TTL = 6000;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const addToast = useCallback(
    (message: string, opts?: { detail?: string; variant?: "success" | "error" | "info" }) => {
      const id = `toast-${++counterRef.current}`;
      setToasts((prev) => [
        ...prev,
        { id, message, detail: opts?.detail, variant: opts?.variant ?? "info", ts: Date.now() },
      ]);

      // Persist error toasts to the system error feed so they appear in System > Errors
      if (opts?.variant === "error") {
        import("@/lib/api").then(({ reportFrontendError }) =>
          reportFrontendError({
            severity: "warning",
            message,
            source: "web-ui",
            context: opts?.detail ? { detail: opts.detail } : undefined,
          }).catch(() => {
            // Fire-and-forget — don't create error toasts about error logging
          })
        ).catch(() => {});
      }
    },
    [],
  );

  // Expire old toasts
  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = setInterval(() => {
      setToasts((prev) => prev.filter((t) => Date.now() - t.ts < TOAST_TTL));
    }, 1000);
    return () => clearInterval(timer);
  }, [toasts.length]);

  const variantStyles: Record<string, string> = {
    success: "border-green-700 bg-green-950",
    error: "border-red-700 bg-red-950",
    info: "border-zinc-700 bg-zinc-900",
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      {toasts.length > 0 && (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={`text-zinc-100 rounded-lg px-4 py-3 shadow-lg border animate-in slide-in-from-right ${variantStyles[toast.variant] ?? variantStyles.info}`}
              role="status"
            >
              <p className="text-sm font-medium">{toast.message}</p>
              {toast.detail && (
                <p className="text-xs text-zinc-400 mt-1 truncate">{toast.detail}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
