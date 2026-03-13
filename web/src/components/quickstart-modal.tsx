"use client";

import { useCallback, useEffect, useState } from "react";
import { Modal } from "@/components/ui/modal";
import { CardSelect } from "@/components/wizard/card-select";
import { FolderPickerModal } from "@/components/settings/folder-picker-modal";
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
  onOpenFullWizard: () => void;
}

export function QuickstartModal({ open, onClose, onComplete, onOpenFullWizard }: QuickstartModalProps) {
  const [step, setStep] = useState(0);
  const [repoPath, setRepoPath] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

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

  useEffect(() => {
    if (!open) {
      setStep(0);
      setRepoPath("");
      setStrategyId("");
      setError("");
      setDone(false);
      setSaving(false);
    }
  }, [open]);

  const handleSubmit = useCallback(async () => {
    if (!repoPath || !strategyId) return;
    setSaving(true);
    setError("");

    const template = templates.find((t) => t.id === strategyId);
    if (!template) {
      setError("Template not found");
      setSaving(false);
      return;
    }

    try {
      // 1. Minimal config with preview platform + template defaults
      const identityName = template.defaults.identity === "company" ? "company" : "default";
      await updateConfig({
        platforms: {
          preview: { enabled: true, priority: "secondary", type: "builtin" },
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

      // 2. Social context from template
      const socialContext = [
        "## Voice & Style",
        "",
        `**Tone**: ${template.defaults.voiceTone}`,
        "",
        "## Audience",
        "",
        `**Primary audience**: ${template.defaults.audience}`,
        `**Technical level**: ${template.defaults.technicalLevel}`,
        "",
      ].join("\n");
      await updateSocialContext("", socialContext);

      // 3. Register project
      const projectRes = await registerProject(repoPath, undefined, true);

      // 4. Import commits + generate summary draft
      if (projectRes.project?.id) {
        try {
          await importCommits(projectRes.project.id);
        } catch {
          // Non-fatal
        }
        try {
          await createSummaryDraft(projectRes.project.id);
        } catch {
          // Non-fatal — draft generation may fail if no summary yet
        }
      }

      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setSaving(false);
    }
  }, [repoPath, strategyId, templates]);

  if (!open) return null;

  if (done) {
    return (
      <Modal open={true} onClose={() => { onComplete(); onClose(); }} maxWidth="max-w-lg">
        <div className="animate-wizard-dissolve space-y-4 text-center">
          <h3 className="text-lg font-semibold">Generating your first draft</h3>
          <p className="text-sm text-muted-foreground">
            Your project has been registered and a draft is being generated. You&apos;ll see a notification on the dashboard when it&apos;s ready for review.
          </p>
          <div className="rounded-md border border-accent/30 bg-accent/5 p-4 text-sm">
            Like what you see?{" "}
            <button
              onClick={() => {
                onClose();
                onOpenFullWizard();
              }}
              className="font-medium text-accent hover:underline"
            >
              Complete full setup
            </button>
          </div>
          <button
            onClick={() => { onComplete(); onClose(); }}
            className="rounded-md bg-accent px-6 py-2 text-sm font-medium text-accent-foreground hover:bg-accent/80 transition-colors"
          >
            Go to Dashboard
          </button>
        </div>
      </Modal>
    );
  }

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
                disabled={!strategyId || saving}
                className="rounded-md bg-accent px-6 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
              >
                {saving ? "Setting up..." : "Start Preview"}
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
