"use client";

import { useEffect, useRef, useState } from "react";
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
  // Local state decoupled from parent to avoid re-render/focus-loss on every keystroke
  const [local, setLocal] = useState<MediaToolGuidance | undefined>(guidance);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync from parent when guidance prop changes (e.g. project switch)
  useEffect(() => { setLocal(guidance); }, [guidance]);

  const description = TOOL_DESCRIPTIONS[toolName] ?? "Media generation tool";
  const overrideValue = local?.enabled === null || local?.enabled === undefined
    ? "global"
    : local.enabled
      ? "enable"
      : "disable";

  function commitChange(updated: MediaToolGuidance) {
    setLocal(updated);
    if (!onGuidanceChange) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => onGuidanceChange(updated), 500);
  }

  function handleOverrideChange(value: string) {
    const newEnabled = value === "global" ? null : value === "enable";
    commitChange({ ...local, enabled: newEnabled });
  }

  function handleListChange(field: "use_when" | "constraints", index: number, value: string) {
    const list = [...(local?.[field] ?? [])];
    if (value === "") {
      list.splice(index, 1);
    } else {
      list[index] = value;
    }
    commitChange({ ...local, [field]: list });
  }

  function handleListAdd(field: "use_when" | "constraints") {
    const list = [...(local?.[field] ?? []), ""];
    commitChange({ ...local, [field]: list });
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
            {(local?.use_when ?? []).map((item, i) => (
              <div key={i} className="mb-1 flex gap-1">
                <input
                  type="text"
                  value={item}
                  onChange={(e) => handleListChange("use_when", i, e.target.value)}
                  disabled={!projectSelected}
                  className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm disabled:opacity-50"
                />
                {projectSelected && (
                  <button
                    onClick={() => handleListChange("use_when", i, "")}
                    className="shrink-0 rounded-md px-1.5 text-sm text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    title="Remove"
                  >
                    &times;
                  </button>
                )}
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
            {(local?.constraints ?? []).map((item, i) => (
              <div key={i} className="mb-1 flex gap-1">
                <input
                  type="text"
                  value={item}
                  onChange={(e) => handleListChange("constraints", i, e.target.value)}
                  disabled={!projectSelected}
                  className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm disabled:opacity-50"
                />
                {projectSelected && (
                  <button
                    onClick={() => handleListChange("constraints", i, "")}
                    className="shrink-0 rounded-md px-1.5 text-sm text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    title="Remove"
                  >
                    &times;
                  </button>
                )}
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
              value={local?.prompt_example ?? ""}
              onChange={(e) =>
                commitChange({ ...local, prompt_example: e.target.value || undefined })
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
