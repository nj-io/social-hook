export function platformLabel(platform: string): string {
  const labels: Record<string, string> = { x: "X (Twitter)", linkedin: "LinkedIn" };
  return labels[platform] ?? platform;
}
