/**
 * Locale-aware relative time formatting.
 * Handles the Z suffix convention used by the API (UTC timestamps).
 */

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * Convert an ISO timestamp string to a human-readable relative time.
 * Returns "just now", "2m ago", "3h ago", "yesterday", "3d ago", etc.
 */
export function relativeTime(dateStr: string): string {
  // Ensure Z suffix for UTC parsing
  const normalized = dateStr.endsWith("Z") ? dateStr : dateStr + "Z";
  const date = new Date(normalized);
  const now = Date.now();
  const diffSec = Math.floor((now - date.getTime()) / 1000);

  if (diffSec < 60) return "just now";
  if (diffSec < HOUR) return rtf.format(-Math.floor(diffSec / MINUTE), "minute");
  if (diffSec < DAY) return rtf.format(-Math.floor(diffSec / HOUR), "hour");
  if (diffSec < 7 * DAY) return rtf.format(-Math.floor(diffSec / DAY), "day");

  // Beyond a week, show absolute date
  return date.toLocaleDateString();
}

/**
 * Return the absolute timestamp string for use in title attributes (hover).
 */
export function absoluteTime(dateStr: string): string {
  const normalized = dateStr.endsWith("Z") ? dateStr : dateStr + "Z";
  return new Date(normalized).toLocaleString();
}
