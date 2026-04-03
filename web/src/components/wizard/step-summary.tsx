"use client";

import type { WizardData } from "./use-wizard-state";
import type { StrategyTemplate } from "@/lib/types";

interface StepSummaryProps {
  data: WizardData;
  templates: StrategyTemplate[];
  onEditStep: (step: number) => void;
  saving: boolean;
  error: string;
}

export function StepSummary({ data, templates, onEditStep, saving, error }: StepSummaryProps) {
  const primaryId = data.strategyIds[0];
  const strategyDisplay = data.strategyIds
    .map((id) => {
      const tmpl = templates.find((t) => t.id === id);
      const name = tmpl?.name ?? id;
      return id === primaryId ? `${name} (primary)` : name;
    })
    .join(", ") || "None selected";
  const enabledPlatforms = data.platforms.filter((p) => p.enabled);

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Review & Finish</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Review your configuration before saving. Click any section to edit.
        </p>
      </div>

      <div className="space-y-2">
        <SummaryRow label="Strategies" value={strategyDisplay} onEdit={() => onEditStep(0)} />

        <SummaryRow
          label="Identities"
          value={data.identities.filter((i) => i.name).map((i) => `${i.label} (${i.type})`).join(", ") || "None defined"}
          onEdit={() => onEditStep(1)}
        />

        <SummaryRow
          label="Platforms"
          value={enabledPlatforms.map((p) => p.name).join(", ") || "None enabled"}
          onEdit={() => onEditStep(2)}
        />

        <SummaryRow
          label="Default Identity"
          value={data.defaultIdentity || "Not set"}
          onEdit={() => onEditStep(3)}
        />

        <SummaryRow
          label="Voice"
          value={data.voiceTone || "Not set"}
          onEdit={() => onEditStep(4)}
        />

        <SummaryRow
          label="Audience"
          value={data.audience || "Not set"}
          onEdit={() => onEditStep(5)}
        />

        <SummaryRow
          label="LLM API Key"
          value={data.llmApiKey ? "Configured" : "Not set"}
          onEdit={() => onEditStep(6)}
        />

        <SummaryRow
          label="Project"
          value={data.repoPath || "Not set"}
          onEdit={() => onEditStep(7)}
        />
      </div>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {saving && (
        <div className="rounded-md border border-border bg-muted/50 p-3 text-sm text-muted-foreground">
          Saving configuration...
        </div>
      )}
    </div>
  );
}

function SummaryRow({ label, value, onEdit }: { label: string; value: string; onEdit: () => void }) {
  return (
    <button
      onClick={onEdit}
      className="flex w-full items-center justify-between rounded-md border border-border px-4 py-3 text-left transition-colors hover:bg-muted"
    >
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="mt-0.5 truncate text-sm">{value}</p>
      </div>
      <span className="ml-4 shrink-0 text-xs text-accent">Edit</span>
    </button>
  );
}
