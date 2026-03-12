/**
 * Per-tab session identity via sessionStorage.
 *
 * Each browser tab gets a unique session ID, enabling isolated chat contexts
 * in the web dashboard. The ID persists across page reloads within the same
 * tab but is unique per tab.
 */

const SESSION_KEY = "social-hook-session-id";

export function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}
