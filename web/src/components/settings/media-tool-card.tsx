"use client";

import { useState } from "react";
import type { MediaToolGuidance } from "@/lib/types";

const TOOL_DESCRIPTIONS: Record<string, string> = {
  mermaid: "Text-based diagram generation",
  nano_banana_pro: "AI image generation (Google Gemini)",
  playwright: "Browser screenshot capture",
  ray_so: "Code screenshot generation",
};

function toolDisplayName(name: string): string {
  const names: Record<string, string> = {
    mermaid: "Mermaid",
    nano_banana_pro: "Nano Banana Pro",
    playwright: "Playwright",
    ray_so: "Ray.so",
  };
  return names[name] ?? name;
}

interface MediaToolCardProps {
  toolName: string;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  guidance?: MediaToolGuidance;
  onGuidanceChange?: (guidance: MediaToolGuidance) => void;
  projectSelected: boolean;
}

export function MediaToolCard({
  toolName,
  enabled,
  onToggle,
  guidance,
  onGuidanceChange,
  projectSelected,
}: MediaToolCardProps) {
  const [expanded, setExpanded] = useState(false);

  const description = TOOL_DESCRIPTIONS[toolName] ?? "Media generation tool";
  const overrideValue = guidance?.enabled === null || guidance?.enabled === undefined
    ? "global"
    : guidance.enabled
      ? "enable"
      : "disable";

  function handleOverrideChange(value: string) {
    if (!onGuidanceChange) return;
    const newEnabled = value === "global" ? null : value === "enable";
    onGuidanceChange({ ...guidance, enabled: newEnabled });
  }

  function handleListChange(field: "use_when" | "constraints", index: number, value: string) {
    if (!onGuidanceChange || !guidance) return;
    const list = [...(guidance[field] ?? [])];
    if (value === "") {
      list.splice(index, 1);
    } else {
      list[index] = value;
    }
    onGuidanceChange({ ...guidance, [field]: list });
  }

  function handleListAdd(field: "use_when" | "constraints") {
    if (!onGuidanceChange) return;
    const list = [...(guidance?.[field] ?? []), ""];
    onGuidanceChange({ ...guidance, [field]: list });
  }

  return (
    <div className="rounded-lg border border-border">
      <div className="flex items-center gap-3 p-4">
        <button
          onClick={() => onToggle(!enabled)}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
            enabled ? "bg-accent" : "bg-border"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
              enabled ? "left-[22px]" : "left-0.5"
            }`}
          />
        </button>

        <div className="min-w-0 flex-1">
          <span className="font-medium">{toolDisplayName(toolName)}</span>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>

      <div className="border-t border-border px-4 py-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <span className={`transition-transform ${expanded ? "rotate-90" : ""}`}>&#9654;</span>
          Per-project guidance
        </button>
      </div>

      {expanded && (
        <div className="space-y-3 border-t border-border p-4">
          {!projectSelected ? (
            <p className="text-xs text-muted-foreground italic">
              Select a project above to edit per-project guidance. Showing defaults (read-only).
            </p>
          ) : null}

          {/* Project override */}
          <div>
            <label className="mb-1 block text-xs font-medium">Project override</label>
            <select
              value={overrideValue}
              onChange={(e) => handleOverrideChange(e.target.value)}
              disabled={!projectSelected}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-50"
            >
              <option value="global">Use global default</option>
              <option value="enable">Enable for project</option>
              <option value="disable">Disable for project</option>
            </select>
          </div>

          {/* use_when */}
          <div>
            <label className="mb-1 block text-xs font-medium">Use when</label>
            {(guidance?.use_when ?? []).map((item, i) => (
              <div key={`use-when-${i}-${item.slice(0, 10)}`} className="mb-1 flex gap-1">
                <input
                  type="text"
                  value={item}
                  onChange={(e) => handleListChange("use_when", i, e.target.value)}
                  disabled={!projectSelected}
                  className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm disabled:opacity-50"
                />
              </div>
            ))}
            {projectSelected && (
              <button
                onClick={() => handleListAdd("use_when")}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                + Add condition
              </button>
            )}
          </div>

          {/* constraints */}
          <div>
            <label className="mb-1 block text-xs font-medium">Constraints</label>
            {(guidance?.constraints ?? []).map((item, i) => (
              <div key={`constraint-${i}-${item.slice(0, 10)}`} className="mb-1 flex gap-1">
                <input
                  type="text"
                  value={item}
                  onChange={(e) => handleListChange("constraints", i, e.target.value)}
                  disabled={!projectSelected}
                  className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm disabled:opacity-50"
                />
              </div>
            ))}
            {projectSelected && (
              <button
                onClick={() => handleListAdd("constraints")}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                + Add constraint
              </button>
            )}
          </div>

          {/* prompt_example */}
          <div>
            <label className="mb-1 block text-xs font-medium">Prompt example</label>
            <textarea
              value={guidance?.prompt_example ?? ""}
              onChange={(e) =>
                onGuidanceChange?.({ ...guidance, prompt_example: e.target.value || undefined })
              }
              disabled={!projectSelected}
              placeholder="Example prompt for this tool..."
              rows={2}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent disabled:opacity-50"
            />
          </div>
        </div>
      )}
    </div>
  );
}
