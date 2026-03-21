"use client";

import type { IdentityEntry, PlatformEntry } from "./use-wizard-state";

interface StepConnectionProps {
  identities: IdentityEntry[];
  platforms: PlatformEntry[];
  defaultIdentity: string;
  onPlatformsChange: (platforms: PlatformEntry[]) => void;
  onDefaultIdentityChange: (name: string) => void;
}

export function StepConnection({
  identities,
  platforms,
  defaultIdentity,
  onPlatformsChange,
  onDefaultIdentityChange,
}: StepConnectionProps) {
  const enabledPlatforms = platforms.filter((p) => p.enabled);
  const namedIdentities = identities.filter((i) => i.name);

  function updatePlatformIdentity(platformName: string, identityName: string) {
    onPlatformsChange(
      platforms.map((p) =>
        p.name === platformName ? { ...p, identity: identityName } : p,
      ),
    );
  }

  // Auto-assign if single identity
  const singleIdentity = namedIdentities.length === 1;

  return (
    <div className="animate-wizard-dissolve space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Connection</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Link identities to platforms. {singleIdentity ? "Your single identity will be used for all platforms." : "Choose which identity posts on each platform."}
        </p>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Default identity</label>
        <select
          value={defaultIdentity}
          onChange={(e) => onDefaultIdentityChange(e.target.value)}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="">Select default...</option>
          {namedIdentities.map((i) => (
            <option key={i.name} value={i.name}>
              {i.label || i.name}
            </option>
          ))}
        </select>
      </div>

      {!singleIdentity && enabledPlatforms.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">Platform assignments</p>
          {enabledPlatforms.map((platform) => (
            <div key={platform.name} className="flex items-center justify-between rounded-md border border-border px-4 py-3">
              <span className="text-sm font-medium capitalize">{platform.name}</span>
              <select
                value={platform.identity || defaultIdentity}
                onChange={(e) => updatePlatformIdentity(platform.name, e.target.value)}
                className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
              >
                <option value="">Use default</option>
                {namedIdentities.map((i) => (
                  <option key={i.name} value={i.name}>
                    {i.label || i.name}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      {singleIdentity && enabledPlatforms.length > 0 && (
        <div className="rounded-md border border-border bg-muted/50 p-4 text-sm text-muted-foreground">
          All platforms will use: <strong className="text-foreground">{namedIdentities[0]?.label || namedIdentities[0]?.name}</strong>
        </div>
      )}
    </div>
  );
}
