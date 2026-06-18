# social-hook snapshot

DB snapshot management.

---

### `social-hook snapshot delete`

Delete a saved snapshot.

Example: social-hook snapshot delete old-snapshot --yes

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Snapshot name to delete |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook snapshot list`

List saved snapshots.

Example: social-hook snapshot list

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook snapshot reset`

Reset database to empty state (backs up current DB first).

Example: social-hook snapshot reset --yes

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook snapshot restore`

Restore a database snapshot (backs up current DB first).

Example: social-hook snapshot restore before-refactor
Example: social-hook snapshot restore before-refactor --yes  (skip confirmation)

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Snapshot name to restore |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook snapshot save`

Save a snapshot of the current database.

Example: social-hook snapshot save before-refactor
Example: social-hook snapshot save before-refactor --yes  (overwrite without prompting)

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Snapshot name |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---
