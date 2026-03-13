"use client";

import { useCallback, useEffect, type ReactNode } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  maxWidth?: string;
  minHeight?: string;
}

export function Modal({ open, onClose, children, maxWidth = "max-w-md", minHeight }: ModalProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-wizard-backdrop"
      onClick={onClose}
    >
      <div
        className={`flex w-full ${maxWidth} flex-col rounded-lg border border-border bg-background p-6 ${minHeight ?? ""} max-h-[90vh]`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
