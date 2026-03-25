"use client";

import { useState } from "react";
import type { PlatformConfig } from "@/lib/types";
import { PlatformCard } from "./platform-card";
import { AddPlatformModal } from "./add-platform-modal";

interface PlatformsSectionProps {
  platforms: Record<string, PlatformConfig>;
  onChange: (platforms: Record<string, PlatformConfig>) => void;
  env: Record<string, string>;
  onEnvRefresh: () => void;
}

export function PlatformsSection({ platforms, onChange, env, onEnvRefresh }: PlatformsSectionProps) {
  const [modalOpen, setModalOpen] = useState(false);

  function handlePlatformChange(name: string, config: PlatformConfig) {
    onChange({ ...platforms, [name]: config });
  }

  function handleRemove(name: string) {
    const next = { ...platforms };
    delete next[name];
    onChange(next);
  }

  function handleAdd(name: string, extra: { format?: string; description?: string; max_length?: number }) {
    onChange({
      ...platforms,
      [name]: {
        enabled: true,
        priority: "secondary",
        type: "custom",
        ...extra,
      },
    });
  }

  // Filter out legacy "preview" platform — preview is now a per-target state, not a platform
  const entries = Object.entries(platforms).filter(([name]) => name !== "preview");

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Platforms</h2>
      <p className="text-sm text-muted-foreground">
        Configure output platforms. Platforms start in preview mode until an account is connected.
      </p>

      <div className="space-y-3">
        {entries.map(([name, config]) => (
          <PlatformCard
            key={name}
            name={name}
            config={config}
            onChange={(c) => handlePlatformChange(name, c)}
            onRemove={config.type === "custom" ? () => handleRemove(name) : undefined}
            env={env}
            onEnvRefresh={onEnvRefresh}
          />
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setModalOpen(true)}
          className="flex-1 rounded-lg border-2 border-dashed border-border p-3 text-sm text-muted-foreground transition-colors hover:border-accent hover:text-foreground"
        >
          + Add Custom Platform
        </button>
      </div>

      <AddPlatformModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onAdd={handleAdd}
        existingNames={Object.keys(platforms)}
      />
    </div>
  );
}
