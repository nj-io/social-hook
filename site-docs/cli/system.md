# social-hook system

Monitor system health, view error feed, and check process status.

---

### `social-hook system errors`

Show recent system errors.

Displays the system error feed, showing recent errors from all
processes (scheduler, CLI, web server). Read-only.

Example: social-hook system errors
Example: social-hook system errors --limit 10 --json

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit`, `-n` | integer | 50 | Max errors to show |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook system health`

Show overall system health status.

Displays error counts by severity in the last 24 hours.
Useful for monitoring and alerting.

Example: social-hook system health
Example: social-hook system health --json

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---
