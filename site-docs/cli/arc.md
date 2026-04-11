# social-hook arc

Manage narrative arcs — story threads that guide tone and framing of generated posts.

---

### `social-hook arc abandon`

Mark a narrative arc as abandoned.

Abandoned arcs are removed from the LLM evaluation context.
Unlike completed arcs, abandonment signals the theme was
dropped rather than concluded. Use 'arc resume' to reactivate.

Example: social-hook arc abandon arc_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `arc_id` | yes | Arc ID to abandon |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--notes`, `-n` | string |  | Optional notes |

---

### `social-hook arc complete`

Mark a narrative arc as completed.

Completed arcs are no longer included in the LLM evaluation
context. The post count is preserved. Use 'arc resume' to
reactivate a completed arc later (subject to the 3-arc limit).

Example: social-hook arc complete arc_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `arc_id` | yes | Arc ID to complete |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--notes`, `-n` | string |  | Optional completion notes |

---

### `social-hook arc create`

Create a new narrative arc.

Arcs give the LLM a thematic thread to weave through posts.
A project can have at most 3 active arcs; complete or
abandon an existing arc to make room.

Example: social-hook arc create "WebSocket migration"
Example: social-hook arc create "Performance sprint" --notes "Q2 focus"

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `theme` | yes | Theme/topic for the narrative arc |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |
| `--notes`, `-n` | string |  | Optional notes |

---

### `social-hook arc list`

List narrative arcs for a project.

Shows ID, status, post count, and theme for each arc.
Defaults to active arcs only; use --status to filter
(active, completed, abandoned, all).

Example: social-hook arc list
Example: social-hook arc list --status all

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |
| `--status`, `-s` | string |  | Filter by status: active, completed, abandoned, all |

---

### `social-hook arc resume`

Resume a completed or abandoned arc.

Moves the arc back to active status so it is included in
future LLM evaluations. Fails if 3 arcs are already active.

Example: social-hook arc resume arc_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `arc_id` | yes | Arc ID to resume |

---
