# social-hook memory

Manage voice memories.

---

### `social-hook memory add`

Add a voice memory to the project.

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

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Project path (default: cwd) |

---
