# social-hook decision

Decision management.

---

### `social-hook decision delete`

Delete a decision and its associated drafts.

A decision is the evaluator's verdict on a commit (draft, skip, or defer).
This permanently removes the decision and all linked drafts from the
database. This action cannot be undone.

Example: social-hook decision delete decision-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `decision_id` | yes | Decision ID to delete |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook decision list`

List decisions for a project.

Decisions are evaluator outcomes for commits (draft, skip, or defer).
Each row shows the decision ID, commit hash, type, media tool, content
angle, and date.

Examples:
    social-hook decision list --project .
    social-hook decision list --limit 50 --json

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |
| `--limit`, `-n` | integer | 20 | Max decisions to show |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook decision retrigger`

Delete a decision and re-evaluate the commit from scratch.

This re-runs the evaluator LLM, which may produce a different angle,
episode type, or even skip the commit entirely.

Example: social-hook decision retrigger decision-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `decision_id` | yes | Decision ID to re-evaluate |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook decision rewind`

Rewind a decision to its evaluation point, removing all downstream artifacts.

Keeps the evaluator's decision but deletes drafts, posts, and draft metadata.
Resets the decision to unprocessed so it can be re-drafted.

Accepts either a decision ID (e.g. decision_abc123) or a commit hash.
When non-commit trigger sources exist (plugins, external events), use
the decision ID directly.

Example: social-hook decision rewind abc1234
Example: social-hook decision rewind decision_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `identifier` | yes | Decision ID or commit hash (full or short prefix) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--force`, `-f` | boolean | false | Allow rewind even with posted drafts |
| `--json` | boolean | false | Output as JSON |

---
