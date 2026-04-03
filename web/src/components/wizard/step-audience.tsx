"use client";

import { useState } from "react";
import { CardSelect } from "./card-select";

interface StepAudienceProps {
  audience: string;
  technicalLevel: string;
  audienceCares: string;
  onAudienceChange: (v: string) => void;
  onTechnicalLevelChange: (v: string) => void;
  onAudienceCaresChange: (v: string) => void;
  templatePreFilled: boolean;
  primaryStrategyName?: string;
}

const TECHNICAL_LEVELS = [
  { id: "beginner", label: "Beginner", description: "New to programming or the topic" },
  { id: "intermediate", label: "Intermediate", description: "Comfortable with basics, learning advanced topics" },
  { id: "advanced", label: "Advanced", description: "Senior developers, architects, deep practitioners" },
  { id: "mixed", label: "Mixed", description: "Broad audience with varying skill levels" },
];

export function StepAudience({
  audience,
  technicalLevel,
  audienceCares,
  onAudienceChange,
  onTechnicalLevelChange,
  onAudienceCaresChange,
  templatePreFilled,
  primaryStrategyName,
}: StepAudienceProps) {
  const [expanded, setExpanded] = useState(!templatePreFilled);

  if (templatePreFilled && !expanded) {
    return (
      <div className="animate-wizard-dissolve space-y-4">
        <div>
          <h3 className="text-lg font-semibold">Audience{primaryStrategyName ? ` (${primaryStrategyName})` : ""}</h3>
          <p className="mt-1 text-sm text-muted-foreground">Pre-filled from your {primaryStrategyName || "strategy"} template. Other strategies use their template defaults.</p>
        </div>
        <div className="rounded-md border border-border bg-muted/50 p-4 text-sm space-y-1">
          <p><strong>Who:</strong> {audience}</p>
          <p><strong>Technical level:</strong> {technicalLevel}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setExpanded(true)}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            Customize
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Audience{primaryStrategyName ? ` (${primaryStrategyName})` : ""}</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Who are you writing for with your {primaryStrategyName || "primary"} strategy?
        </p>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Primary audience</label>
        <input
          type="text"
          value={audience}
          onChange={(e) => onAudienceChange(e.target.value)}
          placeholder="Developers, indie hackers, product managers..."
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
        />
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium">Technical level</label>
        <CardSelect
          options={TECHNICAL_LEVELS}
          value={technicalLevel}
          onChange={onTechnicalLevelChange}
          columns={2}
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">What do they care about?</label>
        <textarea
          value={audienceCares}
          onChange={(e) => onAudienceCaresChange(e.target.value)}
          placeholder="What topics, problems, or outcomes matter to your audience..."
          rows={3}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
        />
      </div>
    </div>
  );
}
