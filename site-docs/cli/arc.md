# social-hook arc

Manage narrative arcs.

---

### `social-hook arc abandon`

Mark a narrative arc as abandoned.

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

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |
| `--status`, `-s` | string |  | Filter by status: active, completed, abandoned, all |

---

### `social-hook arc resume`

Resume a completed or abandoned arc.

Example: social-hook arc resume arc_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `arc_id` | yes | Arc ID to resume |

---
