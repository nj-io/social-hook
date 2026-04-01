"use client";

import type { StrategyTemplate } from "@/lib/types";
import { CardSelect } from "./card-select";

interface StepStrategyProps {
  templates: StrategyTemplate[];
  value: string[];
  onChange: (ids: string[]) => void;
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
        <h3 className="text-lg font-semibold">Content Strategies</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Select one or more strategies. The first selected is your primary — voice and audience settings apply to it. Others use template defaults (customizable later in Settings).
        </p>
      </div>
      <CardSelect multiSelect options={options} value={value} onChange={onChange} columns={2} />
    </div>
  );
}
