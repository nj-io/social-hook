# social-hook inspect

Inspect pipeline state: recent log, pending drafts, LLM usage, and platform status.

---

### `social-hook inspect log`

View the decision log showing evaluation outcomes for commits.

Each entry shows the decision ID, type (draft/skip/defer), commit hash,
and reasoning. Filter by project or view across all projects.

Examples:
    social-hook inspect log
    social-hook inspect log my-project --limit 5 --json

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | no | Project ID (optional) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit`, `-n` | integer | 20 | Number of entries |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook inspect pending`

View drafts awaiting action (draft, approved, scheduled, or deferred).

Pending drafts are those not yet posted or in a terminal state. Use this
to see what content is queued and needs review or approval.

Examples:
    social-hook inspect pending
    social-hook inspect pending my-project --json

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | no | Project ID (optional) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook inspect platforms`

List configured platforms with enabled/disabled status.

Shows each platform's name, priority, type, and account tier from the
global config.

Examples:
    social-hook inspect platforms
    social-hook inspect platforms --json

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook inspect usage`

View token usage and costs.

Shows aggregated LLM token consumption and costs by model. Use --recent
to see individual operations with timestamps and commit hashes.

Examples:
    social-hook inspect usage --days 7
    social-hook inspect usage --recent 10

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--days`, `-d` | integer | 30 | Number of days |
| `--recent`, `-r` | integer |  | Show last N individual operations |
| `--json` | boolean | false | Output as JSON |

---
