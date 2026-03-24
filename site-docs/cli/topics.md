# social-hook topics

Content topic queue.

---

### `social-hook topics add`

Add a new topic to the queue.

Topics track areas of content to cover for a strategy.
New topics start with 'uncovered' status and priority rank 0.

Example: social-hook topics add --strategy technical --topic "evaluation pipeline" --description "How we built the evaluation system"

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--strategy`, `-s` | string |  | Strategy name |
| `--topic`, `-t` | string |  | Topic name |
| `--description`, `-d` | string |  | Topic description |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook topics draft-now`

Force a draft on a held topic.

Creates a draft from the topic's content, bypassing normal scheduling.
This is an LLM operation — may take a moment.

Example: social-hook topics draft-now topic_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `topic_id` | yes | Topic ID to draft |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook topics list`

List all topics, grouped by strategy.

Shows the content topic queue with status, commit count, and priority.
Use --strategy to filter by a specific strategy.

Example: social-hook topics list --strategy building-public

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--strategy`, `-s` | string |  | Filter by strategy name |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook topics reorder`

Reorder a topic within its strategy by setting its priority rank.

Higher rank = higher priority. Inserts topic at rank, shifts others down.

Example: social-hook topics reorder --strategy technical --id topic_abc123 --rank 1

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--strategy`, `-s` | string |  | Strategy name |
| `--id` | string |  | Topic ID |
| `--rank`, `-r` | integer |  | New priority rank (higher = more priority) |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook topics status`

Set a topic's status.

Valid statuses: uncovered, holding, partial, covered.

Example: social-hook topics status topic_abc123 covered

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `topic_id` | yes | Topic ID |
| `new_status` | yes | New status (uncovered, holding, partial, covered) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---
