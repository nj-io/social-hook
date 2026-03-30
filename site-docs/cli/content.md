# social-hook content

Submit content ideas, combine topics, and trigger hero launch drafts.

---

### `social-hook content combine`

Combine 2+ held brand-primary topics into one draft.

Creates a single draft from multiple held topics. Topics must belong
to the brand-primary strategy and be in 'holding' status.
This is an LLM operation.

Example: social-hook content combine --topics topic_abc --topics topic_def

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--topics`, `-t` | string |  | Topic IDs to combine (at least 2) |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook content dismiss`

Dismiss a content suggestion.

Marks the suggestion as dismissed. This is a destructive operation.

Example: social-hook content dismiss suggestion_abc123 --yes

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `suggestion_id` | yes | Suggestion ID to dismiss |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook content hero-launch`

Trigger a hero launch draft using full project context.

Assembles the full project brief, all held brand-primary candidates,
and all covered topics to create a comprehensive launch draft.
This is an LLM operation.

Example: social-hook content hero-launch --project /path/to/repo

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook content list`

List previous content suggestions with status.

Shows all content suggestions for the project with their current status
(pending, evaluated, drafted, dismissed).

Example: social-hook content list

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook content suggest`

Suggest content for the project.

Creates a content suggestion. If --strategy is omitted, the evaluator
will decide which strategy fits best. This is an LLM operation when
the evaluator runs.

Example: social-hook content suggest --idea "Show the new dashboard feature"
Example: social-hook content suggest --strategy brand-primary --idea "Launch announcement"

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--idea`, `-i` | string |  | Content idea to suggest |
| `--strategy`, `-s` | string |  | Strategy to suggest for (omit to let evaluator decide) |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---
