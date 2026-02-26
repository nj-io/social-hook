"use client";

const sections = [
  { id: "models", label: "Models" },
  { id: "api-keys", label: "API Keys" },
  { id: "projects", label: "Projects" },
  { id: "installations", label: "Installations" },
  { id: "platforms", label: "Platforms" },
  { id: "scheduling", label: "Scheduling" },
  { id: "media-generation", label: "Media Generation" },
  { id: "consolidation", label: "Consolidation" },
  { id: "journey-capture", label: "Journey Capture" },
  { id: "notifications", label: "Notifications" },
  { id: "voice-style", label: "Voice & Style" },
  { id: "content-config", label: "Content Config" },
];

export function SettingsSidebar({ active, onSelect }: { active: string; onSelect: (id: string) => void }) {
  return (
    <nav className="w-48 shrink-0 space-y-0.5">
      {sections.map((s) => (
        <button
          key={s.id}
          onClick={() => onSelect(s.id)}
          className={`w-full rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
            active === s.id
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          }`}
        >
          {s.label}
        </button>
      ))}
    </nav>
  );
}
