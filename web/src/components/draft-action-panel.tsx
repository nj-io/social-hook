"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { sendCallback, sendMessage, promoteDraft } from "@/lib/api";
import type { BackgroundTask } from "@/lib/api";
import type { Draft } from "@/lib/types";
import { platformLabel } from "@/lib/platform";
import { useBackgroundTasks } from "@/lib/use-background-tasks";
import { useToast } from "@/lib/toast-context";

interface DraftActionPanelProps {
  draft: Draft;
  onUpdate: () => void;
  enabledPlatforms?: Record<string, { priority: string; type: string }>;
  onRefreshPlatforms?: () => void;
}

type Submenu = "schedule" | "edit" | "reject" | "promote" | null;
type TextPrompt = "edit_text" | "edit_angle" | "reject_note" | "schedule_custom" | null;

/**
 * Aggregate spec-unchanged guard for the Regenerate-media button.
 *
 * Returns true when any ``media_specs[i]`` differs from its
 * ``media_specs_used[i]`` snapshot. Used to disable the batch regen button
 * when everything is already in sync — avoids wasting adapter calls. The
 * per-item regen guard lives on ``MediaToolHeader`` and fires per-tab.
 */
function hasMediaSpecChanges(draft: Draft): boolean {
  const specs = draft.media_specs ?? [];
  const used = draft.media_specs_used ?? [];
  if (specs.length === 0) return false;
  if (specs.length !== used.length) return true;
  return specs.some((s, i) => JSON.stringify(s.spec) !== JSON.stringify(used[i]?.spec));
}

export function DraftActionPanel({ draft, onUpdate, enabledPlatforms, onRefreshPlatforms }: DraftActionPanelProps) {
  const [actionPending, setActionPending] = useState("");
  const [submenu, setSubmenu] = useState<Submenu>(null);
  const [textPrompt, setTextPrompt] = useState<TextPrompt>(null);
  const [textInput, setTextInput] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const { addToast } = useToast();

  // Track background tasks for LLM actions (edit_angle, etc.)
  const onTaskCompleted = useCallback((task: BackgroundTask) => {
    if (task.status === "failed") {
      setActionError(task.error || "Action failed");
      addToast("Draft action failed", { variant: "error", detail: task.error ?? "Unknown error" });
    }
    onUpdate();
    setActionPending("");
    setTextPrompt(null);
    setTextInput("");
    setSubmenu(null);
  }, [onUpdate, addToast]);
  const { trackTask } = useBackgroundTasks(draft.project_id, onTaskCompleted);

  // Actions that stay in the edit submenu (no navigation away from current view)
  const keepSubmenuActions = new Set<string>();

  async function handleAction(action: string) {
    setActionPending(action);
    try {
      await sendCallback(action, draft.id);
      onUpdate();
    } catch {
      onUpdate();
    } finally {
      setActionPending("");
      if (!keepSubmenuActions.has(action)) {
        setSubmenu(null);
      }
    }
  }

  async function handlePromote(platform: string) {
    setActionPending("promote");
    try {
      const res = await promoteDraft(draft.id, platform);
      if (res.task_id) {
        trackTask(res.task_id, `promote-${draft.id}-${Date.now()}`, "promote");
        // Keep loading state — onTaskCompleted handles cleanup
      } else {
        onUpdate();
        setActionPending("");
        setSubmenu(null);
      }
    } catch {
      onUpdate();
      setActionPending("");
      setSubmenu(null);
    }
  }

  async function handleTextSubmit() {
    if (!textPrompt || !textInput.trim()) return;

    setActionPending(textPrompt);
    setActionError(null);
    try {
      // First trigger the callback to set up pending state on the server
      await sendCallback(textPrompt, draft.id);
      // Then send the text as a message (returns 202 with task_id)
      const res = await sendMessage(textInput.trim());
      if (res.task_id) {
        // Track background task — onTaskCompleted clears UI state when done
        trackTask(res.task_id, `action-${draft.id}-${Date.now()}`, "chat_message");
        // Keep text prompt visible in loading state — cleared by onTaskCompleted
      } else {
        // Synchronous completion — clear immediately
        onUpdate();
        setActionPending("");
        setTextPrompt(null);
        setTextInput("");
        setSubmenu(null);
      }
    } catch {
      onUpdate();
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

  const submenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (submenu && submenuRef.current) {
      submenuRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [submenu]);

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

  if (status === "draft" || status === "deferred") {
    const isPreview = !!draft.preview_mode;
    const realPlatforms = enabledPlatforms
      ? Object.keys(enabledPlatforms)
      : [];

    return (
      <div className="space-y-3">
        {/* Preview info banner */}
        {isPreview && (
          <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
            No account connected. Connect an account to enable posting, or use Promote to redraft for another platform.
          </div>
        )}

        {/* Primary actions row */}
        <div className="flex flex-wrap gap-2">
          {!isPreview && (
            <>
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
              <ActionButton
                label="Post Now"
                action="post_now"
                pending={actionPending}
                disabled={isDisabled}
                onClick={handleAction}
                variant="primary"
              />
              <SubmenuToggle
                label="Schedule"
                active={submenu === "schedule"}
                disabled={isDisabled}
                onClick={() => setSubmenu(submenu === "schedule" ? null : "schedule")}
                variant="primary"
              />
            </>
          )}
          {isPreview && (
            <SubmenuToggle
              label="Promote"
              active={submenu === "promote"}
              disabled={isDisabled}
              onClick={() => {
                if (submenu !== "promote") onRefreshPlatforms?.();
                setSubmenu(submenu === "promote" ? null : "promote");
              }}
              variant="primary"
            />
          )}
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
          <div ref={submenuRef}>
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
          </div>
        )}

        {/* Promote submenu */}
        {submenu === "promote" && (
          <div ref={submenuRef}>
            <SubmenuRow>
              {realPlatforms.length > 0 ? (
                realPlatforms.map((p) => (
                  <ActionButton
                    key={p}
                    label={`Redraft for ${platformLabel(p)}`}
                    action="promote"
                    pending={actionPending}
                    disabled={isDisabled}
                    onClick={() => handlePromote(p)}
                    variant="primary-outline"
                  />
                ))
              ) : (
                <span className="text-sm text-muted-foreground">
                  No platforms enabled.{" "}
                  <a href="/settings?section=platforms" className="text-accent hover:underline">
                    Configure platforms
                  </a>
                </span>
              )}
            </SubmenuRow>
          </div>
        )}

        {/* Edit submenu */}
        {submenu === "edit" && (
          <div ref={submenuRef}>
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
                disabled={isDisabled || !hasMediaSpecChanges(draft)}
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
          </div>
        )}

        {/* Reject submenu */}
        {submenu === "reject" && (
          <div ref={submenuRef}>
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
          </div>
        )}
      </div>
    );
  }

  if (status === "advisory") {
    return (
      <div className="space-y-3">
        <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
          This {draft.vehicle || "content"} requires manual posting. Review the{" "}
          <a href="/advisory" className="underline font-medium hover:text-blue-900 dark:hover:text-blue-200">Advisory page</a>{" "}
          for next steps.
        </div>
        <div className="flex flex-wrap gap-2">
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
        {submenu === "edit" && (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => openTextPrompt("edit_text")}
              disabled={isDisabled}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              Edit text
            </button>
            <button
              onClick={() => openTextPrompt("edit_angle")}
              disabled={isDisabled}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              Change angle
            </button>
          </div>
        )}
        {submenu === "reject" && (
          <div className="flex flex-wrap gap-2">
            <ActionButton
              label="Reject"
              action="reject"
              pending={actionPending}
              disabled={isDisabled}
              onClick={handleAction}
              variant="danger"
            />
            <button
              onClick={() => openTextPrompt("reject_note")}
              disabled={isDisabled}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 transition-colors hover:bg-red-50 disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20"
            >
              Reject with note...
            </button>
          </div>
        )}
      </div>
    );
  }

  if (status === "approved") {
    return (
      <div className="flex flex-wrap gap-2">
        <ActionButton
          label="Post Now"
          action="post_now"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="success"
        />
        <ActionButton
          label="Schedule optimal"
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
          Schedule custom...
        </button>
        <ActionButton
          label="Undo"
          action="unapprove"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="neutral-outline"
        />
      </div>
    );
  }

  if (status === "deferred") {
    return (
      <div className="flex flex-wrap gap-2">
        <ActionButton
          label="Post Now"
          action="post_now"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="primary"
        />
        <ActionButton
          label="Approve"
          action="approve"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="success-outline"
        />
      </div>
    );
  }

  if (status === "scheduled") {
    return (
      <div className="flex flex-wrap gap-2">
        <ActionButton
          label="Unschedule"
          action="unschedule"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="neutral-outline"
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

  // cancelled / rejected — offer reopen (not for intro drafts, backend rejects those)
  if ((status === "cancelled" || status === "rejected") && !draft.is_intro) {
    return (
      <div className="flex flex-wrap gap-2">
        <ActionButton
          label="Reopen"
          action="reopen"
          pending={actionPending}
          disabled={isDisabled}
          onClick={handleAction}
          variant="neutral-outline"
        />
      </div>
    );
  }

  // No actions for posted, superseded
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
