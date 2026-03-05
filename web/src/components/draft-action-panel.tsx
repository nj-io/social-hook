"use client";

import { useState } from "react";
import { sendCallback, sendMessage } from "@/lib/api";
import type { Draft } from "@/lib/types";

interface DraftActionPanelProps {
  draft: Draft;
  onUpdate: () => void;
}

type Submenu = "schedule" | "edit" | "reject" | null;
type TextPrompt = "edit_text" | "edit_angle" | "reject_note" | "schedule_custom" | null;

export function DraftActionPanel({ draft, onUpdate }: DraftActionPanelProps) {
  const [actionPending, setActionPending] = useState("");
  const [submenu, setSubmenu] = useState<Submenu>(null);
  const [textPrompt, setTextPrompt] = useState<TextPrompt>(null);
  const [textInput, setTextInput] = useState("");

  async function handleAction(action: string) {
    setActionPending(action);
    try {
      await sendCallback(action, draft.id);
      onUpdate();
    } catch {
      onUpdate();
    } finally {
      setActionPending("");
      setSubmenu(null);
    }
  }

  async function handleTextSubmit() {
    if (!textPrompt || !textInput.trim()) return;

    setActionPending(textPrompt);
    try {
      // First trigger the callback to set up pending state on the server
      await sendCallback(textPrompt, draft.id);
      // Then send the text as a message
      await sendMessage(textInput.trim());
      onUpdate();
    } catch {
      onUpdate();
    } finally {
      setActionPending("");
      setTextPrompt(null);
      setTextInput("");
      setSubmenu(null);
    }
  }

  function openTextPrompt(prompt: TextPrompt) {
    setTextPrompt(prompt);
    // Pre-fill edit text with current content
    setTextInput(prompt === "edit_text" ? draft.content : "");
    setSubmenu(null);
  }

  function cancelTextPrompt() {
    setTextPrompt(null);
    setTextInput("");
  }

  const isDisabled = !!actionPending;

  // Text prompt overlay
  if (textPrompt) {
    const labels: Record<string, { title: string; placeholder: string }> = {
      edit_text: { title: "Edit Content", placeholder: "Enter new content..." },
      edit_angle: { title: "Change Angle", placeholder: "Enter new angle..." },
      reject_note: { title: "Reject with Note", placeholder: "Enter rejection reason..." },
      schedule_custom: { title: "Custom Schedule", placeholder: "e.g., 2pm, tomorrow 9am, 2026-02-15T14:00:00" },
    };
    const label = labels[textPrompt] ?? { title: "Input", placeholder: "Enter text..." };

    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{label.title}</span>
          <button
            onClick={cancelTextPrompt}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
        </div>
        <textarea
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          placeholder={label.placeholder}
          rows={textPrompt === "edit_text" ? 4 : 2}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          autoFocus
        />
        <div className="flex gap-2">
          <button
            onClick={handleTextSubmit}
            disabled={!textInput.trim() || isDisabled}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            {actionPending ? "..." : "Submit"}
          </button>
          <button
            onClick={cancelTextPrompt}
            className="rounded-md border border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  // Status-gated action buttons
  const status = draft.status;

  if (status === "draft") {
    return (
      <div className="space-y-3">
        {/* Primary actions row */}
        <div className="flex flex-wrap gap-2">
          <ActionButton
            label="Quick Approve"
            action="quick_approve"
            pending={actionPending}
            disabled={isDisabled}
            onClick={handleAction}
            variant="success"
          />
          <ActionButton
            label="Approve"
            action="approve"
            pending={actionPending}
            disabled={isDisabled}
            onClick={handleAction}
            variant="success-outline"
          />
          <SubmenuToggle
            label="Schedule"
            active={submenu === "schedule"}
            disabled={isDisabled}
            onClick={() => setSubmenu(submenu === "schedule" ? null : "schedule")}
            variant="primary"
          />
          <SubmenuToggle
            label="Edit"
            active={submenu === "edit"}
            disabled={isDisabled}
            onClick={() => setSubmenu(submenu === "edit" ? null : "edit")}
            variant="neutral"
          />
          <SubmenuToggle
            label="Reject"
            active={submenu === "reject"}
            disabled={isDisabled}
            onClick={() => setSubmenu(submenu === "reject" ? null : "reject")}
            variant="danger"
          />
        </div>

        {/* Schedule submenu */}
        {submenu === "schedule" && (
          <SubmenuRow>
            <ActionButton
              label="Optimal time"
              action="schedule_optimal"
              pending={actionPending}
              disabled={isDisabled}
              onClick={handleAction}
              variant="primary-outline"
            />
            <button
              onClick={() => openTextPrompt("schedule_custom")}
              disabled={isDisabled}
              className="rounded-md border border-blue-300 px-3 py-1.5 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-50 disabled:opacity-50 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-900/20"
            >
              Custom time...
            </button>
          </SubmenuRow>
        )}

        {/* Edit submenu */}
        {submenu === "edit" && (
          <SubmenuRow>
            <button
              onClick={() => openTextPrompt("edit_text")}
              disabled={isDisabled}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              Change text...
            </button>
            <button
              onClick={() => openTextPrompt("edit_angle")}
              disabled={isDisabled}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              Change angle...
            </button>
            <ActionButton
              label="Regenerate media"
              action="media_regen"
              pending={actionPending}
              disabled={isDisabled || draft.media_spec === draft.media_spec_used}
              onClick={handleAction}
              variant="neutral-outline"
            />
            <ActionButton
              label="Remove media"
              action="media_remove"
              pending={actionPending}
              disabled={isDisabled}
              onClick={handleAction}
              variant="neutral-outline"
            />
          </SubmenuRow>
        )}

        {/* Reject submenu */}
        {submenu === "reject" && (
          <SubmenuRow>
            <ActionButton
              label="Just reject"
              action="reject_now"
              pending={actionPending}
              disabled={isDisabled}
              onClick={handleAction}
              variant="danger-outline"
            />
            <button
              onClick={() => openTextPrompt("reject_note")}
              disabled={isDisabled}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 transition-colors hover:bg-red-50 disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
            >
              Reject with note...
            </button>
          </SubmenuRow>
        )}
      </div>
    );
  }

  if (status === "approved") {
    return (
      <div className="flex flex-wrap gap-2">
        <ActionButton
          label="Schedule optimal"
          action="schedule_optimal"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="primary"
        />
        <button
          onClick={() => openTextPrompt("schedule_custom")}
          disabled={isDisabled}
          className="rounded-md border border-blue-300 px-3 py-1.5 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-50 disabled:opacity-50 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-900/20"
        >
          Schedule custom...
        </button>
        <ActionButton
          label="Cancel"
          action="cancel"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="neutral-outline"
        />
      </div>
    );
  }

  if (status === "scheduled") {
    return (
      <div className="flex flex-wrap gap-2">
        <ActionButton
          label="Cancel"
          action="cancel"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="danger-outline"
        />
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="space-y-2">
        {draft.last_error && (
          <p className="text-xs text-destructive">{draft.last_error}</p>
        )}
        <div className="flex flex-wrap gap-2">
          <ActionButton
            label="Retry"
            action="approve"
            pending={actionPending}
            disabled={isDisabled}
            onClick={handleAction}
            variant="primary"
          />
          <ActionButton
            label="Cancel"
            action="cancel"
            pending={actionPending}
            disabled={isDisabled}
            onClick={handleAction}
            variant="danger-outline"
          />
        </div>
      </div>
    );
  }

  // No actions for posted, rejected, cancelled, superseded
  return null;
}

// --- Sub-components ---

const variantStyles: Record<string, string> = {
  success: "bg-green-600 text-white hover:bg-green-700",
  "success-outline": "border border-green-300 text-green-700 hover:bg-green-50 dark:border-green-700 dark:text-green-400 dark:hover:bg-green-900/20",
  primary: "bg-blue-600 text-white hover:bg-blue-700",
  "primary-outline": "border border-blue-300 text-blue-700 hover:bg-blue-50 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-900/20",
  danger: "bg-red-600 text-white hover:bg-red-700",
  "danger-outline": "border border-red-300 text-red-700 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20",
  neutral: "bg-muted text-foreground hover:bg-muted/80",
  "neutral-outline": "border border-border text-foreground hover:bg-muted",
};

function ActionButton({
  label,
  action,
  pending,
  disabled,
  onClick,
  variant,
}: {
  label: string;
  action: string;
  pending: string;
  disabled: boolean;
  onClick: (action: string) => void;
  variant: string;
}) {
  const style = variantStyles[variant] ?? variantStyles.neutral;
  return (
    <button
      onClick={() => onClick(action)}
      disabled={disabled}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${style}`}
    >
      {pending === action ? "..." : label}
    </button>
  );
}

function SubmenuToggle({
  label,
  active,
  disabled,
  onClick,
  variant,
}: {
  label: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
  variant: string;
}) {
  const baseStyle = variantStyles[variant] ?? variantStyles.neutral;
  const activeRing = active ? "ring-2 ring-accent ring-offset-1" : "";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${baseStyle} ${activeRing}`}
    >
      {label} {active ? "\u25B4" : "\u25BE"}
    </button>
  );
}

function SubmenuRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap gap-2 rounded-md border border-border bg-muted/30 p-2">
      {children}
    </div>
  );
}
