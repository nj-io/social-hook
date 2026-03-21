"use client";

import type { StrategyTemplate } from "@/lib/types";
import { CardSelect } from "./card-select";

interface StepStrategyProps {
  templates: StrategyTemplate[];
  value: string;
  onChange: (id: string) => void;
}

export function StepStrategy({ templates, value, onChange }: StepStrategyProps) {
  const options = templates.map((t) => ({
    id: t.id,
    label: t.name,
    description: t.description,
  }));

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Content Strategy</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          What kind of content do you want to create? This pre-fills sensible defaults for voice, audience, and posting behavior.
        </p>
      </div>
      <CardSelect options={options} value={value} onChange={onChange} columns={2} />
    </div>
  );
}
