# social-hook logs

Log queries, tailing, and health.

**Group options:**

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--severity`, `-s` | string |  | Filter by severity |
| `--component`, `-c` | string |  | Filter by component |
| `--source` | string |  | Filter by source module |
| `--limit`, `-n` | integer | 50 | Max errors to show |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook logs clear`

Clear system errors from the database.

Without --older-than, deletes all errors. Prompts for confirmation
unless --yes is given.

Example: social-hook logs clear --yes
Example: social-hook logs clear --older-than 7

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--older-than` | integer |  | Only delete errors older than N days |
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook logs health`

Show overall system health status.

Displays error counts by severity in the last 24 hours.

Example: social-hook logs health
Example: social-hook logs health --json

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook logs tail`

Tail log files. Optionally filter by component.

Interactive terminal tool -- the web dashboard has the system tab for log viewing.

Example: social-hook logs tail trigger
Example: social-hook logs tail

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `component` | no | Component to tail (trigger, scheduler, bot, web, narrative, consolidation, cli, or omit for all) |

---
