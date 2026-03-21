import type { WizardData } from "@/components/wizard/use-wizard-state";

/**
 * Assemble structured WizardData into social-context.md markdown.
 * Voice + audience sections only — identity is in config.yaml.
 */
export function assembleSocialContext(data: WizardData): string {
  const sections: string[] = [];

  // Voice section
  if (data.voiceTone || data.writingSamples.length > 0 || data.petPeeves.length > 0) {
    const lines = ["## Voice & Style"];
    if (data.voiceTone) {
      lines.push("", `**Tone**: ${data.voiceTone}`);
    }
    if (data.writingSamples.length > 0) {
      lines.push("", "**Writing samples**:");
      for (const sample of data.writingSamples) {
        lines.push(`- ${sample}`);
      }
    }
    if (data.petPeeves.length > 0) {
      lines.push("", "**Pet peeves**:");
      for (const peeve of data.petPeeves) {
        lines.push(`- ${peeve}`);
      }
    }
    const grammarEntries = Object.entries(data.grammarPrefs).filter(([, v]) => v);
    if (grammarEntries.length > 0) {
      lines.push("", "**Grammar preferences**:");
      for (const [key] of grammarEntries) {
        lines.push(`- ${key}`);
      }
    }
    sections.push(lines.join("\n"));
  }

  // Audience section
  if (data.audience || data.technicalLevel || data.audienceCares) {
    const lines = ["## Audience"];
    if (data.audience) {
      lines.push("", `**Primary audience**: ${data.audience}`);
    }
    if (data.technicalLevel) {
      lines.push(`**Technical level**: ${data.technicalLevel}`);
    }
    if (data.audienceCares) {
      lines.push("", `**What they care about**: ${data.audienceCares}`);
    }
    sections.push(lines.join("\n"));
  }

  return sections.join("\n\n") + "\n";
}
