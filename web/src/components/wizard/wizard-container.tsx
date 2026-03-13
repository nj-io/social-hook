"use client";

import { useCallback, useEffect, useState } from "react";
import type { StrategyTemplate } from "@/lib/types";
import {
  createSummaryDraft,
  fetchWizardTemplates,
  importCommits,
  registerProject,
  updateConfig,
  updateEnv,
  updateSocialContext,
} from "@/lib/api";
import { assembleSocialContext } from "@/lib/assemble-social-context";
import { useWizardState } from "./use-wizard-state";
import { WizardStepper } from "./wizard-stepper";
import { StepStrategy } from "./step-strategy";
import { StepIdentity } from "./step-identity";
import { StepPlatforms } from "./step-platforms";
import { StepConnection } from "./step-connection";
import { StepVoice } from "./step-voice";
import { StepAudience } from "./step-audience";
import { StepCredentials } from "./step-credentials";
import { StepProject } from "./step-project";
import { StepSummary } from "./step-summary";

const STEP_LABELS = [
  "Strategy",
  "Identity",
  "Platforms",
  "Connection",
  "Voice",
  "Audience",
  "Credentials",
  "Project",
  "Summary",
];

interface WizardContainerProps {
  onComplete: () => void;
  onClose: () => void;
}

export function WizardContainer({ onComplete, onClose }: WizardContainerProps) {
  const {
    data,
    updateData,
    currentStep,
    setCurrentStep,
    completedSteps,
    markStepComplete,
    reset,
  } = useWizardState();

  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  // Fetch templates on mount
  useEffect(() => {
    fetchWizardTemplates()
      .then((res) => setTemplates(res.templates))
      .catch(() => {
        // Use fallback templates if API not available yet
        setTemplates([
          {
            id: "building-public",
            name: "Build in Public",
            description: "Share your journey transparently — struggles, decisions, and progress",
            defaults: { identity: "myself", voiceTone: "Conversational, honest, journey-focused. Shows the messy parts.", audience: "Developers, indie hackers, builders", technicalLevel: "intermediate", platformFilter: "all", platformFrequency: "high", postWhen: "All development activity — decisions, struggles, progress, mistakes", avoid: "Corporate speak, polished-only outcomes, hype", exampleIntroHook: "Hi, I'm [name]. I'm building [project] and sharing the journey — the wins, the mistakes, and everything in between." },
          },
          {
            id: "product-news",
            name: "Release Updates",
            description: "Announce features, improvements, and milestones professionally",
            defaults: { identity: "company", voiceTone: "Clear, professional, outcome-focused. Emphasizes value to users.", audience: "Users and developers interested in the product", technicalLevel: "intermediate", platformFilter: "significant", platformFrequency: "low", postWhen: "Features, improvements, launches, milestones", avoid: "Internal refactoring, process narratives, struggles", exampleIntroHook: "We're [company], building [project]. Follow along for feature updates and what's coming next." },
          },
          {
            id: "technical-deep-dive",
            name: "Curated Technical",
            description: "Polished technical posts about architecture, patterns, and implementations",
            defaults: { identity: "myself", voiceTone: "Technical, detailed, confident. Shows depth without being dry.", audience: "Senior developers, architects, technical leads", technicalLevel: "advanced", platformFilter: "notable", platformFrequency: "moderate", postWhen: "Architecture decisions, interesting patterns, deep implementations, trade-offs", avoid: "Surface-level updates, announcements without technical substance", exampleIntroHook: "I'm [name], [role]. I write about the technical decisions behind [project] — architecture, patterns, and trade-offs." },
          },
          {
            id: "custom",
            name: "Custom",
            description: "Start from scratch with your own content strategy",
            defaults: { identity: "myself", voiceTone: "", audience: "", technicalLevel: "intermediate", platformFilter: "all", platformFrequency: "moderate", postWhen: "", avoid: "", exampleIntroHook: "" },
          },
        ]);
      });
  }, []);

  const selectedTemplate = templates.find((t) => t.id === data.strategyId);
  const isTemplateSelected = !!selectedTemplate && selectedTemplate.id !== "custom";

  // Determine which steps are skippable
  const isSkippable = useCallback(
    (step: number): boolean => {
      if (!isTemplateSelected) return false;
      // Connection skippable if single identity
      if (step === 3) {
        const namedIdentities = data.identities.filter((i) => i.name);
        return namedIdentities.length <= 1;
      }
      // Voice, Audience skippable when template pre-fills them
      if (step === 4 || step === 5) return true;
      // Credentials skippable if already configured
      if (step === 6) return !!data.llmApiKey;
      return false;
    },
    [isTemplateSelected, data.identities, data.llmApiKey],
  );

  function applyTemplateDefaults(templateId: string) {
    const template = templates.find((t) => t.id === templateId);
    if (!template || template.id === "custom") {
      updateData({ strategyId: templateId });
      return;
    }
    updateData({
      strategyId: templateId,
      voiceTone: template.defaults.voiceTone,
      audience: template.defaults.audience,
      technicalLevel: template.defaults.technicalLevel,
      platformFilter: template.defaults.platformFilter,
      platformFrequency: template.defaults.platformFrequency,
      postWhen: template.defaults.postWhen,
      avoid: template.defaults.avoid,
      identities: data.identities.map((i, idx) =>
        idx === 0 ? { ...i, type: template.defaults.identity as "myself" | "company" | "project" | "character" } : i,
      ),
    });
  }

  function handleNext() {
    markStepComplete(currentStep);
    if (currentStep < STEP_LABELS.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  }

  function handleBack() {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  }

  function handleSkip() {
    markStepComplete(currentStep);
    if (currentStep < STEP_LABELS.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaveError("");
    try {
      // 1. Build and save config
      const identities: Record<string, { type: string; label: string; description?: string; intro_hook?: string }> = {};
      for (const i of data.identities.filter((i) => i.name)) {
        identities[i.name] = {
          type: i.type,
          label: i.label,
          ...(i.description ? { description: i.description } : {}),
          ...(i.introHook ? { intro_hook: i.introHook } : {}),
        };
      }

      const platforms: Record<string, { enabled: boolean; priority: string; type: string; identity?: string; account_tier?: string; filter?: string; frequency?: string }> = {};
      for (const p of data.platforms.filter((p) => p.enabled)) {
        platforms[p.name] = {
          enabled: true,
          priority: p.priority,
          type: p.name === "x" || p.name === "linkedin" || p.name === "preview" ? "builtin" : "custom",
          ...(p.identity ? { identity: p.identity } : {}),
          ...(p.accountTier ? { account_tier: p.accountTier } : {}),
        };
      }

      const contentStrategies: Record<string, { audience: string; voice: string; post_when?: string; avoid?: string }> = {};
      if (data.strategyId && data.strategyId !== "custom") {
        contentStrategies[data.strategyId] = {
          audience: data.audience,
          voice: data.voiceTone,
          ...(data.postWhen ? { post_when: data.postWhen } : {}),
          ...(data.avoid ? { avoid: data.avoid } : {}),
        };
      }

      await updateConfig({
        platforms,
        identities,
        default_identity: data.defaultIdentity || data.identities[0]?.name || undefined,
        content_strategies: Object.keys(contentStrategies).length > 0 ? contentStrategies : undefined,
        content_strategy: data.strategyId !== "custom" ? data.strategyId : undefined,
      } as Record<string, unknown>);

      // 2. Save social context
      const socialContext = assembleSocialContext(data);
      if (socialContext.trim()) {
        await updateSocialContext("", socialContext);
      }

      // 3. Save credentials
      if (data.llmApiKey) {
        await updateEnv("ANTHROPIC_API_KEY", data.llmApiKey);
      }
      for (const [key, value] of Object.entries(data.platformCredentials)) {
        if (value) {
          await updateEnv(key, value);
        }
      }

      // 4. Register project
      if (data.repoPath) {
        const projectRes = await registerProject(
          data.repoPath,
          data.projectName || undefined,
          data.installGitHook,
        );

        // 5. Import commits + generate summary draft
        if (projectRes.project?.id) {
          try {
            await importCommits(projectRes.project.id);
          } catch {
            // Non-fatal: import can happen later
          }
          try {
            await createSummaryDraft(projectRes.project.id);
          } catch {
            // Non-fatal: draft generation may fail if no summary yet
          }
        }
      }

      // Success
      reset();
      onComplete();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  }

  const isSummaryStep = currentStep === STEP_LABELS.length - 1;

  return (
    <div className="flex h-full flex-col">
      {/* Stepper */}
      <div className="mb-6 border-b border-border pb-4">
        <WizardStepper
          steps={STEP_LABELS}
          currentStep={currentStep}
          completedSteps={completedSteps}
          onStepClick={(step) => {
            if (completedSteps.has(step) || step <= currentStep) {
              setCurrentStep(step);
            }
          }}
        />
      </div>

      {/* Step content */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {currentStep === 0 && (
          <StepStrategy
            templates={templates}
            value={data.strategyId}
            onChange={(id) => applyTemplateDefaults(id)}
          />
        )}
        {currentStep === 1 && (
          <StepIdentity
            identities={data.identities}
            onChange={(identities) => updateData({ identities })}
            exampleIntroHook={selectedTemplate?.defaults.exampleIntroHook ?? ""}
          />
        )}
        {currentStep === 2 && (
          <StepPlatforms
            platforms={data.platforms}
            onChange={(platforms) => updateData({ platforms })}
          />
        )}
        {currentStep === 3 && (
          <StepConnection
            identities={data.identities}
            platforms={data.platforms}
            defaultIdentity={data.defaultIdentity}
            onPlatformsChange={(platforms) => updateData({ platforms })}
            onDefaultIdentityChange={(defaultIdentity) => updateData({ defaultIdentity })}
          />
        )}
        {currentStep === 4 && (
          <StepVoice
            voiceTone={data.voiceTone}
            writingSamples={data.writingSamples}
            petPeeves={data.petPeeves}
            grammarPrefs={data.grammarPrefs}
            onVoiceToneChange={(voiceTone) => updateData({ voiceTone })}
            onWritingSamplesChange={(writingSamples) => updateData({ writingSamples })}
            onPetPeevesChange={(petPeeves) => updateData({ petPeeves })}
            onGrammarPrefsChange={(grammarPrefs) => updateData({ grammarPrefs })}
            templatePreFilled={isTemplateSelected}
          />
        )}
        {currentStep === 5 && (
          <StepAudience
            audience={data.audience}
            technicalLevel={data.technicalLevel}
            audienceCares={data.audienceCares}
            onAudienceChange={(audience) => updateData({ audience })}
            onTechnicalLevelChange={(technicalLevel) => updateData({ technicalLevel })}
            onAudienceCaresChange={(audienceCares) => updateData({ audienceCares })}
            templatePreFilled={isTemplateSelected}
          />
        )}
        {currentStep === 6 && (
          <StepCredentials
            llmApiKey={data.llmApiKey}
            platformCredentials={data.platformCredentials}
            enabledPlatforms={data.platforms.filter((p) => p.enabled).map((p) => p.name)}
            onLlmApiKeyChange={(llmApiKey) => updateData({ llmApiKey })}
            onPlatformCredentialsChange={(platformCredentials) => updateData({ platformCredentials })}
            templatePreFilled={isTemplateSelected}
          />
        )}
        {currentStep === 7 && (
          <StepProject
            repoPath={data.repoPath}
            projectName={data.projectName}
            installGitHook={data.installGitHook}
            onRepoPathChange={(repoPath) => updateData({ repoPath })}
            onProjectNameChange={(projectName) => updateData({ projectName })}
            onInstallGitHookChange={(installGitHook) => updateData({ installGitHook })}
          />
        )}
        {currentStep === 8 && (
          <StepSummary
            data={data}
            templates={templates}
            onEditStep={(step) => setCurrentStep(step)}
            saving={saving}
            error={saveError}
          />
        )}
      </div>

      {/* Navigation buttons */}
      <div className="mt-6 flex items-center justify-between border-t border-border pt-4">
        <div>
          {currentStep > 0 && (
            <button
              onClick={handleBack}
              className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
            >
              Back
            </button>
          )}
          {currentStep === 0 && (
            <button
              onClick={onClose}
              className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
            >
              Cancel
            </button>
          )}
        </div>
        <div className="flex gap-2">
          {isSkippable(currentStep) && !isSummaryStep && (
            <button
              onClick={handleSkip}
              className="rounded-md border border-border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted"
            >
              Skip
            </button>
          )}
          {isSummaryStep ? (
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-md bg-accent px-6 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Start Generating Content"}
            </button>
          ) : (
            <button
              onClick={handleNext}
              disabled={currentStep === 0 && !data.strategyId}
              className="rounded-md bg-accent px-6 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/80 disabled:opacity-50"
            >
              Continue
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
