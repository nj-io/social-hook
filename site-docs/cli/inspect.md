# social-hook inspect

Inspect system state.

---

### `social-hook inspect log`

View decision log.

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

### `social-hook inspect logs`

Tail log files. Optionally filter by component.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `component` | no | Component to tail (trigger, scheduler, bot, or omit for all) |

---

### `social-hook inspect pending`

View pending drafts.

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

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook inspect usage`

View token usage and costs.

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--days`, `-d` | integer | 30 | Number of days |
| `--recent`, `-r` | integer |  | Show last N individual operations |
| `--json` | boolean | false | Output as JSON |

---
