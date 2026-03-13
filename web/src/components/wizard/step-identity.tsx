"use client";

import type { IdentityEntry } from "./use-wizard-state";

interface StepIdentityProps {
  identities: IdentityEntry[];
  onChange: (identities: IdentityEntry[]) => void;
  exampleIntroHook: string;
}

const IDENTITY_TYPES: { value: IdentityEntry["type"]; label: string; description: string }[] = [
  { value: "myself", label: "Myself", description: "Post as yourself" },
  { value: "company", label: "Company", description: "Post as a company/brand" },
  { value: "project", label: "Project", description: "Post as the project itself" },
  { value: "character", label: "Character", description: "Post as a persona" },
];

export function StepIdentity({ identities, onChange, exampleIntroHook }: StepIdentityProps) {
  function updateEntry(index: number, updates: Partial<IdentityEntry>) {
    const next = identities.map((entry, i) => (i === index ? { ...entry, ...updates } : entry));
    onChange(next);
  }

  function addEntry() {
    onChange([...identities, { name: "", type: "myself", label: "", description: "", introHook: "" }]);
  }

  function removeEntry(index: number) {
    if (identities.length <= 1) return;
    onChange(identities.filter((_, i) => i !== index));
  }

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Identity</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Define who is posting. You can create multiple identities and assign them to different platforms.
        </p>
      </div>

      {identities.map((entry, i) => (
        <div key={i} className="space-y-3 rounded-lg border border-border p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Identity {identities.length > 1 ? i + 1 : ""}</span>
            {identities.length > 1 && (
              <button
                onClick={() => removeEntry(i)}
                className="text-xs text-destructive hover:underline"
              >
                Remove
              </button>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium">Name (key)</label>
              <input
                type="text"
                value={entry.name}
                onChange={(e) => updateEntry(i, { name: e.target.value.toLowerCase().replace(/\s+/g, "-") })}
                placeholder="neil, acme, etc."
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Display label</label>
              <input
                type="text"
                value={entry.label}
                onChange={(e) => updateEntry(i, { label: e.target.value })}
                placeholder="Neil, Acme Corp, etc."
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">Type</label>
            <div className="flex flex-wrap gap-2">
              {IDENTITY_TYPES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => updateEntry(i, { type: t.value })}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                    entry.type === t.value
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-border hover:bg-muted"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">Description (optional)</label>
            <input
              type="text"
              value={entry.description}
              onChange={(e) => updateEntry(i, { description: e.target.value })}
              placeholder="Brief description of this identity"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium">Intro hook (optional)</label>
            <textarea
              value={entry.introHook}
              onChange={(e) => updateEntry(i, { introHook: e.target.value })}
              placeholder={exampleIntroHook || "How you'd introduce yourself on this platform..."}
              rows={2}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
        </div>
      ))}

      <button
        onClick={addEntry}
        className="rounded-md border border-dashed border-border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:border-accent hover:text-accent"
      >
        + Add another identity
      </button>
    </div>
  );
}
