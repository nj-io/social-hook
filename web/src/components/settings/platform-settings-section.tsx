"use client";

import { useCallback, useEffect, useState } from "react";
import type { PlatformSettings } from "@/lib/types";
import { fetchPlatformSettings, updatePlatformSettings } from "@/lib/api";

export function PlatformSettingsSection() {
  const [settings, setSettings] = useState<PlatformSettings[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchPlatformSettings();
      // API returns {platform_settings: {name: {...}}} — convert to array
      const ps = res.platform_settings;
      if (ps && typeof ps === "object" && !Array.isArray(ps)) {
        setSettings(
          Object.entries(ps).map(([name, val]: [string, Record<string, unknown>]) => ({
            name,
            platform: name,
            cross_account_gap_minutes: (val.cross_account_gap_minutes as number) || 0,
          }))
        );
      } else {
        setSettings([]);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleUpdate(platform: string, value: number) {
    setSaving(platform);
    try {
      await updatePlatformSettings(platform, { cross_account_gap_minutes: value });
      setSettings((prev) =>
        prev.map((s) => s.platform === platform ? { ...s, cross_account_gap_minutes: value } : s),
      );
    } catch {
      // silent
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Platform Settings</h2>
        <p className="text-sm text-muted-foreground">
          Per-platform posting configuration. Jitter is applied automatically.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : settings.length === 0 ? (
        <p className="text-sm text-muted-foreground">No platform settings configured.</p>
      ) : (
        <div className="space-y-3">
          {settings.map((s) => (
            <div key={s.platform} className="rounded-lg border border-border p-4">
              <div className="flex items-center justify-between">
                <span className="font-medium capitalize">{s.platform}</span>
                {saving === s.platform && <span className="text-xs text-muted-foreground">Saving...</span>}
              </div>
              <div className="mt-2">
                <label className="mb-1 block text-xs text-muted-foreground">Cross-account gap (minutes)</label>
                <input
                  type="number"
                  min={0}
                  value={s.cross_account_gap_minutes}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (isNaN(val)) return;
                    setSettings((prev) =>
                      prev.map((ps) => ps.platform === s.platform ? { ...ps, cross_account_gap_minutes: val } : ps),
                    );
                  }}
                  onBlur={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (!isNaN(val)) handleUpdate(s.platform, val);
                  }}
                  className="w-32 rounded-md border border-border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
