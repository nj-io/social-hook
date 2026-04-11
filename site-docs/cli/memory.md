# social-hook memory

Manage voice memories — persistent notes the LLM uses for consistent voice across drafts.

---

### `social-hook memory add`

Add a voice memory to the project.

Voice memories teach the LLM your tone preferences. The --context
describes the content type (e.g. "bug fix posts") and --feedback
provides the guidance (e.g. "keep it casual, skip jargon").
Optionally link to a specific draft with --draft-id.

Example: social-hook memory add -c "release announcements" -f "be enthusiastic but concise"

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--context`, `-c` | string |  | Brief description of content type |
| `--feedback`, `-f` | string |  | Human feedback text |
| `--draft-id`, `-d` | string |  | Reference to original draft |
| `--project`, `-p` | string |  | Project path (default: cwd) |

---

### `social-hook memory clear`

Clear all voice memories for a project.

Example: social-hook memory clear --yes  (skip confirmation)

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |
| `--yes`, `-y` | boolean | false | Skip confirmation |

---

### `social-hook memory delete`

Delete a voice memory by its number.

Use the 1-based index from 'memory list' to identify which
memory to remove.

Example: social-hook memory delete 3

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `index` | yes | Memory number to delete (1-based, from 'memory list') |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |

---

### `social-hook memory list`

List all voice memories for a project.

Voice memories are human feedback entries (context + feedback pairs)
that the LLM receives during drafting to shape tone and style.
Shows index number, date, context, feedback, and associated draft ID.

Example: social-hook memory list

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |

---
