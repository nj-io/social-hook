"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Modal } from "@/components/ui/modal";
import { CardSelect } from "@/components/wizard/card-select";
import { FolderPickerModal } from "@/components/settings/folder-picker-modal";
import { ElapsedTime } from "@/components/async-button";
import { TopBanner } from "@/components/top-banner";
import { useBackgroundTasks } from "@/lib/use-background-tasks";
import { useToast } from "@/lib/toast-context";
import type { BackgroundTask } from "@/lib/api";
import type { StrategyTemplate } from "@/lib/types";
import {
  createSummaryDraft,
  fetchWizardTemplates,
  importCommits,
  registerProject,
  updateConfig,
  updateSocialContext,
} from "@/lib/api";

interface QuickstartModalProps {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
  onOpenFullWizard: (project?: { repoPath: string; projectId: string }) => void;
}

type Phase = "input" | "generating" | "complete" | "error";

const GEN_STEPS = [
  "Configuring settings",
  "Registering project",
  "Importing commits",
  "Analyzing your project",
  "Generating your first draft",
] as const;

const SLOW_THRESHOLD_MS = 45_000;

/**
 * 3D negative-space animation — three contrasting planes (white, grey, black)
 * orbit in 3D space. As they rotate, they naturally mask and reveal each other
 * through perspective occlusion, creating evolving negative-space patterns.
 */
function GenerationMark() {
  return (
    <div className="gen-mark">
      <div className="gen-scene">
        <div className="gen-plane gen-a" />
        <div className="gen-plane gen-b" />
        <div className="gen-plane gen-c" />
      </div>
    </div>
  );
}

export function QuickstartModal({ open, onClose, onComplete, onOpenFullWizard }: QuickstartModalProps) {
  // Input state
  const [step, setStep] = useState(0);
  const [repoPath, setRepoPath] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);

  // Generation state
  const [phase, setPhase] = useState<Phase>("input");
  const [genStep, setGenStep] = useState(0);
  const [startTime, setStartTime] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [registeredProject, setRegisteredProject] = useState<{ repoPath: string; projectId: string } | null>(null);
  const [slowBannerVisible, setSlowBannerVisible] = useState(false);

  // Background task tracking — projectId drives the useBackgroundTasks hook.
  // We set projectId after registration, then a useEffect fires the summary
  // draft call once the hook has re-armed its WS listener with the real ID.
  const [projectId, setProjectId] = useState("");
  const [readyToGenerate, setReadyToGenerate] = useState(false);
  const slowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { addToast } = useToast();

  const onTaskCompleted = useCallback((task: BackgroundTask) => {
    if (task.type !== "summary_draft") return;
    if (task.status === "completed") {
      setGenStep(GEN_STEPS.length);
      setPhase("complete");
      setSlowBannerVisible(false);
      if (slowTimerRef.current) {
        clearTimeout(slowTimerRef.current);
        slowTimerRef.current = null;
      }
    } else {
      setError(task.error ?? "Draft generation failed. You can try again from the dashboard.");
      setPhase("error");
      setSlowBannerVisible(false);
    }
  }, []);

  const { trackTask } = useBackgroundTasks(projectId, onTaskCompleted);

  // Fire summary draft AFTER projectId is committed to the hook (next render)
  useEffect(() => {
    if (!readyToGenerate || !projectId) return;
    setReadyToGenerate(false);

    createSummaryDraft(projectId)
      .then((res) => {
        trackTask(res.task_id, `summary:${projectId}`, "summary_draft");
        // Fake progress: advance from "Analyzing" to "Generating" after 5s
        setTimeout(() => {
          setGenStep((prev) => (prev === 3 ? 4 : prev));
        }, 5000);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Draft generation failed");
        setPhase("error");
      });
  }, [readyToGenerate, projectId, trackTask]);

  // Fetch templates on open
  useEffect(() => {
    if (open) {
      fetchWizardTemplates()
        .then((res) => setTemplates(res.templates.filter((t) => t.id !== "custom")))
        .catch(() => {
          setTemplates([
            { id: "building-public", name: "Build in Public", description: "Share your journey transparently", defaults: { identity: "myself", voiceTone: "Conversational, honest, journey-focused.", audience: "Developers, indie hackers, builders", technicalLevel: "intermediate", platformFilter: "all", platformFrequency: "high", postWhen: "", avoid: "", exampleIntroHook: "" } },
            { id: "product-news", name: "Release Updates", description: "Announce features and milestones", defaults: { identity: "company", voiceTone: "Clear, professional, outcome-focused.", audience: "Users and developers", technicalLevel: "intermediate", platformFilter: "significant", platformFrequency: "low", postWhen: "", avoid: "", exampleIntroHook: "" } },
            { id: "technical-deep-dive", name: "Curated Technical", description: "Polished technical posts", defaults: { identity: "myself", voiceTone: "Technical, detailed, confident.", audience: "Senior developers, architects", technicalLevel: "advanced", platformFilter: "notable", platformFrequency: "moderate", postWhen: "", avoid: "", exampleIntroHook: "" } },
          ]);
        });
    }
  }, [open]);

  // Reset all state when modal closes
  useEffect(() => {
    if (!open) {
      setStep(0);
      setRepoPath("");
      setStrategyId("");
      setError("");
      setPhase("input");
      setGenStep(0);
      setStartTime(null);
      setRegisteredProject(null);
      setSlowBannerVisible(false);
      setProjectId("");
      setReadyToGenerate(false);
      if (slowTimerRef.current) {
        clearTimeout(slowTimerRef.current);
        slowTimerRef.current = null;
      }
    }
  }, [open]);

  const handleSubmit = useCallback(async () => {
    if (!repoPath || !strategyId) return;

    const template = templates.find((t) => t.id === strategyId);
    if (!template) {
      setError("Template not found");
      return;
    }

    // Transition to generation phase
    setPhase("generating");
    setGenStep(0);
    setError("");
    const now = new Date().toISOString();
    setStartTime(now);
    addToast("Quickstart generating", { detail: "Configuring and analyzing your project..." });

    // Start slow task timer
    slowTimerRef.current = setTimeout(() => {
      setSlowBannerVisible(true);
    }, SLOW_THRESHOLD_MS);

    try {
      // Step 0: Configure settings
      const identityName = template.defaults.identity === "company" ? "company" : "default";
      // save_config merges dict keys (.update()), so sending only preview
      // leaves any previously-enabled platforms (like x) intact. Explicitly
      // disable the other builtins so only preview is active.
      await updateConfig({
        platforms: {
          preview: { enabled: true, priority: "secondary", type: "builtin" },
          x: { enabled: false, priority: "primary", type: "builtin" },
          linkedin: { enabled: false, priority: "primary", type: "builtin" },
        },
        identities: {
          [identityName]: {
            type: template.defaults.identity,
            label: identityName === "company" ? "Company" : "Default",
          },
        },
        default_identity: identityName,
        content_strategies: {
          [strategyId]: {
            audience: template.defaults.audience,
            voice: template.defaults.voiceTone,
            ...(template.defaults.postWhen ? { post_when: template.defaults.postWhen } : {}),
            ...(template.defaults.avoid ? { avoid: template.defaults.avoid } : {}),
          },
        },
        content_strategy: strategyId,
      } as Record<string, unknown>);

      const socialContext = [
        "## Voice & Style", "",
        `**Tone**: ${template.defaults.voiceTone}`, "",
        "## Audience", "",
        `**Primary audience**: ${template.defaults.audience}`,
        `**Technical level**: ${template.defaults.technicalLevel}`, "",
      ].join("\n");
      await updateSocialContext("", socialContext);

      setGenStep(1);

      // Step 1: Register project
      const projectRes = await registerProject(repoPath, undefined, true);
      const pid = projectRes.project?.id;
      if (pid) {
        setRegisteredProject({ repoPath, projectId: pid });
        setProjectId(pid);
      }

      setGenStep(2);

      // Step 2: Import commits (fire and advance — runs in background)
      if (pid) {
        try {
          await importCommits(pid);
        } catch {
          // Non-fatal
        }
      }

      setGenStep(3);

      // Steps 3-4: Generate summary draft — deferred to useEffect so the
      // useBackgroundTasks hook has re-armed its WS listener with the real
      // projectId before we call trackTask.
      if (pid) {
        setReadyToGenerate(true);
      } else {
        setError("Failed to register project");
        setPhase("error");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
      setPhase("error");
      if (slowTimerRef.current) {
        clearTimeout(slowTimerRef.current);
        slowTimerRef.current = null;
      }
    }
  }, [repoPath, strategyId, templates, addToast]);

  if (!open) return null;

  // ── Phase: Complete ──
  if (phase === "complete") {
    return (
      <Modal open={true} onClose={() => { onComplete(); onClose(); }} maxWidth="max-w-lg">
        <div className="animate-draft-ready space-y-6 py-8 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
            <svg className="h-8 w-8 text-green-600 dark:text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-semibold">Draft ready for review!</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Your first draft has been generated and is waiting on the dashboard.
            </p>
          </div>
          <div className="rounded-md border border-accent/30 bg-accent/5 p-4 text-sm">
            Like what you see?{" "}
            <button
              onClick={() => {
                onClose();
                onOpenFullWizard(registeredProject ?? undefined);
              }}
              className="font-medium text-accent hover:underline"
            >
              Complete full setup
            </button>
            {" "}to configure real platforms, voice, and more.
          </div>
          <button
            onClick={() => { onComplete(); onClose(); }}
            className="rounded-md bg-accent px-8 py-2.5 text-sm font-medium text-accent-foreground hover:bg-accent/80 transition-colors"
          >
            Go to Dashboard
          </button>
        </div>
      </Modal>
    );
  }

  // ── Phase: Generating ──
  if (phase === "generating" || phase === "error") {
    return (
      <Modal open={true} onClose={() => {}} maxWidth="max-w-lg">
        {/* "Taking too long?" banner — positioned inside modal */}
        <TopBanner
          visible={slowBannerVisible}
          onDismiss={() => setSlowBannerVisible(false)}
        >
          Taking longer than expected? Add your own API key in{" "}
          <span className="font-medium">Settings &rarr; API Keys</span>{" "}
          for faster results.
        </TopBanner>

        <div className="flex flex-col items-center py-8">
          <h3 className="mb-8 text-lg font-semibold">Generating your first draft</h3>

          {/* Negative-space SVG animation */}
          <div className="mb-8">
            <GenerationMark />
          </div>

          {/* Progress steps */}
          <div className="mb-6 w-full max-w-xs space-y-3">
            {GEN_STEPS.map((label, i) => {
              const isComplete = genStep > i;
              const isActive = genStep === i;
              const isPending = genStep < i;

              return (
                <div
                  key={i}
                  className={`flex items-center gap-3 transition-opacity duration-300 ${
                    isPending ? "opacity-30" : "opacity-100"
                  } ${isActive || isComplete ? "animate-step-enter" : ""}`}
                  style={isActive || isComplete ? { animationDelay: `${i * 100}ms` } : undefined}
                >
                  <div className="flex h-5 w-5 shrink-0 items-center justify-center">
                    {isComplete ? (
                      <svg className="h-5 w-5 text-green-500 animate-checkmark-pop" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : isActive ? (
                      <svg className="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                    ) : (
                      <div className="h-2 w-2 rounded-full bg-border" />
                    )}
                  </div>
                  <span className={`text-sm ${isActive ? "font-medium" : isComplete ? "text-muted-foreground" : "text-muted-foreground"}`}>
                    {label}{isActive ? "..." : ""}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Elapsed timer */}
          {startTime && (
            <div className="text-xs text-muted-foreground">
              <ElapsedTime startTime={startTime} />
            </div>
          )}

          {/* Error state */}
          {phase === "error" && (
            <div className="mt-4 w-full space-y-3">
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-center text-sm text-destructive">
                {error}
              </div>
              <div className="flex justify-center gap-2">
                <button
                  onClick={() => { onComplete(); onClose(); }}
                  className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
                >
                  Go to Dashboard
                </button>
              </div>
            </div>
          )}
        </div>
      </Modal>
    );
  }

  // ── Phase: Input (steps 0-1) ──
  return (
    <Modal open={true} onClose={onClose} maxWidth="max-w-lg">
      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Quick Preview</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            2 steps to see your first draft. Pick a repo and a strategy — we handle the rest.
          </p>
        </div>

        {step === 0 && (
          <div className="animate-wizard-dissolve space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">Pick a repository</label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={repoPath}
                  onChange={(e) => setRepoPath(e.target.value)}
                  placeholder="/path/to/your/repo"
                  className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
                <button
                  onClick={() => setFolderPickerOpen(true)}
                  className="shrink-0 rounded-md border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted"
                >
                  Browse
                </button>
              </div>
              {repoPath && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Selected: <span className="font-medium text-foreground">{repoPath.split("/").pop()}</span> at {repoPath}
                </p>
              )}
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setStep(1)}
                disabled={!repoPath}
                className="rounded-md bg-accent px-6 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="animate-wizard-dissolve space-y-4">
            <div>
              <label className="mb-2 block text-sm font-medium">Pick a content strategy</label>
              <CardSelect
                options={templates.map((t) => ({ id: t.id, label: t.name, description: t.description }))}
                value={strategyId}
                onChange={setStrategyId}
                columns={3}
              />
            </div>
            {error && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}
            <div className="flex justify-between">
              <button
                onClick={() => setStep(0)}
                className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
              >
                Back
              </button>
              <button
                onClick={handleSubmit}
                disabled={!strategyId}
                className="rounded-md bg-accent px-6 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
              >
                Start Preview
              </button>
            </div>
          </div>
        )}
      </div>

      <FolderPickerModal
        open={folderPickerOpen}
        onClose={() => setFolderPickerOpen(false)}
        onSelect={(path) => setRepoPath(path)}
      />
    </Modal>
  );
}
