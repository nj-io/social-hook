# social-hook cycles

Evaluation cycle history.

---

### `social-hook cycles list`

List recent evaluation cycles.

Shows the history of content evaluation cycles for the project,
including trigger type and timing.

Example: social-hook cycles list --limit 10

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit`, `-n` | integer | 20 | Max cycles to show |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook cycles show`

Show evaluation cycle detail with per-strategy outcomes.

Displays the full cycle including trigger information, related
decisions, and drafts produced.

Example: social-hook cycles show cycle_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `cycle_id` | yes | Cycle ID to show |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---
