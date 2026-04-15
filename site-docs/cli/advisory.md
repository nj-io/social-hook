# social-hook advisory

Manage advisory items — operator action items for manual tasks.

---

### `social-hook advisory complete`

Mark an advisory item as completed.

Use after you've taken the recommended action (e.g., posted an article
manually, set up a platform account).

Example: social-hook advisory complete advisory_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `item_id` | yes | Advisory item ID to mark as completed |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook advisory create`

Create an advisory item manually.

Advisory items track actions that need operator attention — posting
articles, setting up accounts, infrastructure changes, etc.

Example: social-hook advisory create --title "Set up LinkedIn" --category platform_presence
Example: social-hook advisory create -t "Post article draft" -c content_asset -u blocking

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--title`, `-t` | string |  | Advisory item title |
| `--category`, `-c` | string |  | Category: platform_presence, product_infrastructure, content_asset, code_change, external_action, outreach |
| `--description`, `-d` | string |  | Detailed description |
| `--urgency`, `-u` | string | normal | Urgency: blocking or normal (default: normal) |
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook advisory dismiss`

Dismiss an advisory item.

Marks the item as dismissed with an optional reason. This is a
destructive operation — dismissed items are hidden from the active list.

Example: social-hook advisory dismiss advisory_abc123 --reason "Not applicable"

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `item_id` | yes | Advisory item ID to dismiss |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--reason`, `-r` | string |  | Reason for dismissing |
| `--yes`, `-y` | boolean | false | Skip confirmation |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook advisory list`

List advisory items for a project.

Shows action items that need operator attention — article posts,
platform setup, infrastructure tasks, etc.

Example: social-hook advisory list
Example: social-hook advisory list --status pending --urgency blocking

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--status`, `-s` | string |  | Filter by status: pending, completed, dismissed |
| `--category` | string |  | Filter by category |
| `--urgency` | string |  | Filter by urgency: blocking, normal |
| `--json` | boolean | false | Output as JSON |

---
