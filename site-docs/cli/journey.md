# social-hook journey

Development Journey capture.

---

### `social-hook journey off`

Disable Development Journey capture.

Removes the Claude Code session hook and stops recording
narratives. Existing narrative files are preserved.

Example: social-hook journey off

---

### `social-hook journey on`

Enable Development Journey capture.

Installs a Claude Code session hook that records development
narratives (reasoning, decisions, context) to JSONL files.
These narratives enrich the LLM's understanding of your work.
Restart any running Claude Code sessions for the hook to take effect.

Example: social-hook journey on

---

### `social-hook journey status`

Show Development Journey status.

Displays: whether capture is enabled, hook installation state,
Claude CLI detection, and number of narrative files recorded.

Example: social-hook journey status

---
