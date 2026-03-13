# social-hook draft

Draft lifecycle management.

---

### `social-hook draft approve`

Approve a draft for posting.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to approve |

---

### `social-hook draft cancel`

Cancel a draft.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to cancel |

---

### `social-hook draft edit`

Edit draft content.

Example: social-hook draft edit draft-abc123 --content "Updated post text here"

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to edit |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--content`, `-c` | string |  | New content |

---

### `social-hook draft list`

List drafts with optional filters.

Example: social-hook draft list --pending --json
Example: social-hook draft list --decision decision-abc123
Example: social-hook draft list --commit 47a5191

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--status`, `-s` | string |  | Filter by status |
| `--project`, `-i` | string |  | Filter by project ID |
| `--decision`, `-d` | string |  | Filter by decision ID |
| `--commit`, `-c` | string |  | Filter by commit hash |
| `--pending` | boolean | false | Show only actionable drafts (draft/approved/scheduled) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook draft media-edit`

Edit the media spec for a draft.

Example: social-hook draft media-edit draft-abc123 --spec '{"code": "print(42)", "language": "python"}'

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to edit media spec for |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--spec`, `-s` | string |  | New media spec as JSON string |

---

### `social-hook draft media-regen`

Regenerate media for a draft using its stored media spec.

Example: social-hook draft media-regen draft-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to regenerate media for |

---

### `social-hook draft media-remove`

Remove media from a draft.

Example: social-hook draft media-remove draft-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to remove media from |

---

### `social-hook draft quick-approve`

Approve and schedule at optimal time in one step.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to approve and schedule |

---

### `social-hook draft redraft`

Redraft content using the Expert agent with a new angle.

Example: social-hook draft redraft draft-abc123 --angle "focus on the performance gains"

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to redraft |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--angle`, `-a` | string |  | New angle or direction for the draft |

---

### `social-hook draft reject`

Reject a draft (saves reason as voice memory when --reason provided).

Example: social-hook draft reject draft-abc123 --reason "too technical for the audience"

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to reject |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--reason`, `-r` | string |  | Rejection reason |

---

### `social-hook draft retry`

Retry a failed draft.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to retry |

---

### `social-hook draft schedule`

Schedule a draft for posting.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to schedule |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--time`, `-t` | string |  | Schedule time (ISO format) |

---

### `social-hook draft show`

Show full detail for a draft including media spec and change history.

Example: social-hook draft show draft-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to show |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--open` | boolean | false | Open media files in default viewer |
| `--json` | boolean | false | Output as JSON |

---
