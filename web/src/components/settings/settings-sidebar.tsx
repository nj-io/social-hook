"use client";

import { useEffect, useRef, useState } from "react";

const sections = [
  { id: "models", label: "Models" },
  { id: "api-keys", label: "API Keys" },
  { id: "projects", label: "Projects" },
  { id: "installations", label: "Installations" },
  { id: "channels", label: "Channels" },
  { id: "platforms", label: "Platforms" },
  { id: "scheduling", label: "Scheduling" },
  { id: "media-generation", label: "Media Generation" },
  { id: "consolidation", label: "Consolidation" },
  { id: "journey-capture", label: "Journey Capture" },
  { id: "notifications", label: "Notifications" },
  { id: "voice-style", label: "Voice & Style" },
  { id: "content-config", label: "Content Config" },
];

export { sections };

export function SettingsSidebar({ active, onSelect }: { active: string; onSelect: (id: string) => void }) {
  const navRef = useRef<HTMLElement>(null);
  const [indicatorStyle, setIndicatorStyle] = useState<{ top: number; height: number }>({ top: 0, height: 0 });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!navRef.current) return;
    const activeIndex = sections.findIndex((s) => s.id === active);
    if (activeIndex === -1) return;
    const buttons = navRef.current.querySelectorAll<HTMLButtonElement>("button");
    const btn = buttons[activeIndex];
    if (!btn) return;
    setIndicatorStyle({
      top: btn.offsetTop,
      height: btn.offsetHeight,
    });
    if (!ready) setReady(true);
  }, [active, ready]);

  return (
    <nav ref={navRef} className="w-48 shrink-0 overflow-y-auto">
      <div className="relative">
        {/* Sliding indicator */}
        <div
          className="settings-sidebar-indicator absolute left-0 right-0 rounded-md bg-accent"
          style={{
            top: indicatorStyle.top,
            height: indicatorStyle.height,
            opacity: ready ? 1 : 0,
            transition: ready ? "top 0.25s cubic-bezier(0.4, 0, 0.2, 1), height 0.15s cubic-bezier(0.4, 0, 0.2, 1)" : "none",
          }}
        />
        {/* Buttons */}
        <div className="relative z-10 space-y-0.5">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`w-full rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
                active === s.id
                  ? "text-accent-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    </nav>
  );
}
