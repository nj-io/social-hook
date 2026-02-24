"use client";

import { useCallback, useEffect, useState } from "react";
import type { Config, MediaGenerationConfig, MediaToolGuidance, Project } from "@/lib/types";
import { fetchContentConfigParsed, updateContentConfigParsed } from "@/lib/api";
import { MediaToolCard } from "./media-tool-card";

const DEFAULT_TOOLS: Record<string, boolean> = {
  mermaid: true,
  nano_banana_pro: true,
  playwright: true,
  ray_so: true,
};

interface MediaGenerationSectionProps {
  config: Config;
  onConfigChange: (updates: Partial<Config>) => void;
  projects?: Project[];
  onGuidanceSave?: () => void;
}

export function MediaGenerationSection({ config, onConfigChange, projects, onGuidanceSave }: MediaGenerationSectionProps) {
  const mediaGen: MediaGenerationConfig = config.media_generation ?? { enabled: true, tools: {} };
  const [selectedProjectPath, setSelectedProjectPath] = useState<string>("");
  const [mediaToolsGuidance, setMediaToolsGuidance] = useState<Record<string, MediaToolGuidance>>({});
  const [loadingGuidance, setLoadingGuidance] = useState(false);
  const [savingGuidance, setSavingGuidance] = useState(false);

  const loadGuidance = useCallback(async (projectPath: string) => {
    setLoadingGuidance(true);
    try {
      const parsed = await fetchContentConfigParsed(projectPath || undefined);
      const tools = (parsed.media_tools ?? {}) as Record<string, MediaToolGuidance>;
      setMediaToolsGuidance(tools);
    } catch {
      setMediaToolsGuidance({});
    } finally {
      setLoadingGuidance(false);
    }
  }, []);

  useEffect(() => {
    loadGuidance(selectedProjectPath);
  }, [selectedProjectPath, loadGuidance]);

  function handleGlobalToggle() {
    onConfigChange({
      media_generation: { ...mediaGen, enabled: !mediaGen.enabled },
    });
  }

  function handleToolToggle(toolName: string, enabled: boolean) {
    // Always include all known tools so partial saves don't lose tools
    const allTools = { ...DEFAULT_TOOLS, ...mediaGen.tools, [toolName]: enabled };
    onConfigChange({
      media_generation: { ...mediaGen, tools: allTools },
    });
  }

  async function handleGuidanceChange(toolName: string, guidance: MediaToolGuidance) {
    const newGuidance = { ...mediaToolsGuidance, [toolName]: guidance };
    setMediaToolsGuidance(newGuidance);

    setSavingGuidance(true);
    try {
      await updateContentConfigParsed(
        { media_tools: { [toolName]: guidance } },
        selectedProjectPath || undefined,
      );
      onGuidanceSave?.();
    } finally {
      setSavingGuidance(false);
    }
  }

  const toolNames = Object.keys({ ...DEFAULT_TOOLS, ...mediaGen.tools });

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Media Generation</h2>
      <p className="text-sm text-muted-foreground">
        Configure media generation tools for social media posts.
      </p>

      {/* Global enable/disable */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleGlobalToggle}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
            mediaGen.enabled ? "bg-accent" : "bg-border"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
              mediaGen.enabled ? "left-[22px]" : "left-0.5"
            }`}
          />
        </button>
        <span className="text-sm">{mediaGen.enabled ? "Enabled" : "Disabled"}</span>
      </div>

      {/* Project selector for per-project guidance */}
      {projects && projects.length > 0 && (
        <div>
          <label className="mb-1 block text-sm font-medium">Per-project guidance</label>
          <div className="flex items-center gap-2">
            <select
              value={selectedProjectPath}
              onChange={(e) => setSelectedProjectPath(e.target.value)}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
            >
              <option value="">Global defaults</option>
              {projects.map((p) => (
                <option key={p.id} value={p.repo_path}>
                  {p.name}
                </option>
              ))}
            </select>
            {loadingGuidance && (
              <span className="text-xs text-muted-foreground">Loading...</span>
            )}
            {savingGuidance && (
              <span className="text-xs text-muted-foreground">Saving...</span>
            )}
          </div>
        </div>
      )}

      {/* Tool cards */}
      <div className="space-y-3">
        {toolNames.map((toolName) => (
          <MediaToolCard
            key={toolName}
            toolName={toolName}
            enabled={mediaGen.tools[toolName] ?? true}
            onToggle={(enabled) => handleToolToggle(toolName, enabled)}
            guidance={mediaToolsGuidance[toolName]}
            onGuidanceChange={(guidance) => handleGuidanceChange(toolName, guidance)}
            projectSelected={selectedProjectPath !== ""}
          />
        ))}
      </div>
    </div>
  );
}
