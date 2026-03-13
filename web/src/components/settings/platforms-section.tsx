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
    const next = { ...platforms, [name]: config };
    if (name !== "preview" && config.enabled && next["preview"]?.enabled) {
      next["preview"] = { ...next["preview"], enabled: false };
    }
    onChange(next);
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

  function handleAddPreview() {
    if (platforms["preview"]) return;
    onChange({
      ...platforms,
      preview: {
        enabled: true,
        priority: "secondary",
        type: "custom",
        description: "Generic preview for reviewing what the system would generate, without publishing",
        format: "post",
        max_length: 2000,
      },
    });
  }

  const entries = Object.entries(platforms);
  const hasPreview = "preview" in platforms;
  const hasRealPlatformEnabled = entries.some(([n, c]) => n !== "preview" && c.enabled);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Platforms</h2>
      <p className="text-sm text-muted-foreground">
        Configure output platforms. Each platform can be primary (more content) or secondary (filtered content).
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
        {!hasPreview && !hasRealPlatformEnabled && (
          <button
            onClick={handleAddPreview}
            className="rounded-lg border-2 border-dashed border-blue-300 p-3 text-sm text-blue-600 transition-colors hover:border-blue-500 hover:text-blue-800 dark:border-blue-700 dark:text-blue-400 dark:hover:border-blue-500 dark:hover:text-blue-300"
          >
            + Preview
          </button>
        )}
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
