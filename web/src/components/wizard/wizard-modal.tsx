"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Modal } from "@/components/ui/modal";
import { WizardContainer } from "./wizard-container";

interface WizardModalProps {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
  prefilledProject?: { repoPath: string; projectId: string } | null;
}

export function WizardModal({ open, onClose, onComplete, prefilledProject }: WizardModalProps) {
  const [confirmClose, setConfirmClose] = useState(false);
  const hasProgressRef = useRef(false);

  // Track if wizard has progress to show confirmation on close
  useEffect(() => {
    if (!open) {
      hasProgressRef.current = false;
      setConfirmClose(false);
    }
  }, [open]);

  const handleClose = useCallback(() => {
    // Check localStorage for wizard progress
    try {
      const stored = localStorage.getItem("social-hook-wizard");
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.data?.strategyId || parsed.currentStep > 0) {
          setConfirmClose(true);
          return;
        }
      }
    } catch {
      // Ignore
    }
    onClose();
  }, [onClose]);

  const handleConfirmDiscard = useCallback(() => {
    localStorage.removeItem("social-hook-wizard");
    setConfirmClose(false);
    onClose();
  }, [onClose]);

  if (!open) return null;

  if (confirmClose) {
    return (
      <Modal open={true} onClose={() => setConfirmClose(false)} maxWidth="max-w-sm">
        <h3 className="text-lg font-semibold">Discard setup progress?</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Your wizard progress will be lost. You can always start again later.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={() => setConfirmClose(false)}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Keep editing
          </button>
          <button
            onClick={handleConfirmDiscard}
            className="rounded-md bg-destructive px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-destructive/80"
          >
            Discard
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal open={true} onClose={handleClose} maxWidth="max-w-2xl" minHeight="min-h-[600px]">
      <WizardContainer onComplete={onComplete} onClose={handleClose} prefilledProject={prefilledProject} />
    </Modal>
  );
}
