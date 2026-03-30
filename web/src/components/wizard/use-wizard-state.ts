"use client";

import { useCallback, useEffect, useState } from "react";

export interface IdentityEntry {
  name: string;
  type: "myself" | "company" | "project" | "character";
  label: string;
  description: string;
  introHook: string;
}

export interface PlatformEntry {
  name: string;
  enabled: boolean;
  priority: "primary" | "secondary";
  accountTier: string;
  introduce: boolean;
  identity: string;
}

export interface WizardData {
  // Step 0: Strategy
  strategyId: string;
  // Step 1: Identity
  identities: IdentityEntry[];
  defaultIdentity: string;
  // Step 2: Platforms
  platforms: PlatformEntry[];
  platformFilter: string;
  platformFrequency: string;
  // Step 3: Connection (platform→identity mapping is in platforms[].identity)
  // Step 4: Voice
  voiceTone: string;
  writingSamples: string[];
  petPeeves: string[];
  grammarPrefs: Record<string, boolean>;
  // Step 5: Audience
  audience: string;
  technicalLevel: string;
  audienceCares: string;
  // Step 6: Credentials
  llmApiKey: string;
  platformCredentials: Record<string, string>;
  // Step 7: Project
  repoPath: string;
  projectName: string;
  installGitHook: boolean;
  triggerBranch: string;
  // Strategy fields
  postWhen: string;
  avoid: string;
}

const STORAGE_KEY = "social-hook-wizard";

const DEFAULT_PLATFORMS: PlatformEntry[] = [
  { name: "x", enabled: false, priority: "primary", accountTier: "free", introduce: true, identity: "" },
  { name: "linkedin", enabled: false, priority: "primary", accountTier: "", introduce: true, identity: "" },
];

export function createDefaultWizardData(): WizardData {
  return {
    strategyId: "",
    identities: [{ name: "", type: "myself", label: "", description: "", introHook: "" }],
    defaultIdentity: "",
    platforms: DEFAULT_PLATFORMS.map((p) => ({ ...p })),
    platformFilter: "all",
    platformFrequency: "moderate",
    voiceTone: "",
    writingSamples: [],
    petPeeves: [],
    grammarPrefs: {},
    audience: "",
    technicalLevel: "intermediate",
    audienceCares: "",
    llmApiKey: "",
    platformCredentials: {},
    repoPath: "",
    projectName: "",
    installGitHook: true,
    triggerBranch: "",
    postWhen: "",
    avoid: "",
  };
}

export function useWizardState() {
  const [data, setData] = useState<WizardData>(createDefaultWizardData);
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set());

  // Restore from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.data) setData(parsed.data);
        if (parsed.currentStep != null) setCurrentStep(parsed.currentStep);
        if (parsed.completedSteps) setCompletedSteps(new Set(parsed.completedSteps));
      }
    } catch {
      // Ignore parse errors
    }
  }, []);

  // Persist to localStorage on change
  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          data,
          currentStep,
          completedSteps: Array.from(completedSteps),
        }),
      );
    } catch {
      // Ignore storage errors
    }
  }, [data, currentStep, completedSteps]);

  const updateData = useCallback((updates: Partial<WizardData>) => {
    setData((prev) => ({ ...prev, ...updates }));
  }, []);

  const markStepComplete = useCallback((step: number) => {
    setCompletedSteps((prev) => new Set(prev).add(step));
  }, []);

  const reset = useCallback(() => {
    setData(createDefaultWizardData());
    setCurrentStep(0);
    setCompletedSteps(new Set());
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const hasProgress = data.strategyId !== "" || data.identities.some((i) => i.label !== "");

  return {
    data,
    updateData,
    currentStep,
    setCurrentStep,
    completedSteps,
    markStepComplete,
    reset,
    hasProgress,
  };
}
