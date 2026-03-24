# social-hook target

Content distribution targets.

---

### `social-hook target add`

Add a content distribution target.

Maps an account + destination to a content strategy.
Max targets per project is configurable (default: 10).

Example: social-hook target add --account product --destination timeline --strategy product-news

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--account` | string |  | Account name |
| `--destination` | string | timeline | Destination (timeline, etc.) |
| `--strategy` | string |  | Content strategy name |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook target disable`

Disable a target and archive its pending drafts.

Sets the target status to 'disabled' and cancels any pending drafts.
The target remains in the system and can be re-enabled.

Example: social-hook target disable product/timeline --yes

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Target name (account/destination) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook target enable`

Re-enable a disabled target.

Example: social-hook target enable product/timeline

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `name` | yes | Target name (account/destination) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook target list`

List targets with account, destination, and strategy.

Shows all content distribution targets for the project.
Each target maps an account + destination to a content strategy.

Example: social-hook target list

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---
