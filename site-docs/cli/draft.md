# social-hook draft

Draft lifecycle management.

---

### `social-hook draft approve`

Mark a draft as approved for posting.

The scheduler will post it when its scheduled time arrives.
Preview drafts must be promoted to a platform first.

Example: social-hook draft approve draft_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to approve |

---

### `social-hook draft cancel`

Cancel a pending draft, removing it from the posting queue.

Example: social-hook draft cancel draft_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to cancel |

---

### `social-hook draft connect`

Connect a preview-mode draft to an account.

Links the draft's target to an existing OAuth account, clearing preview mode.
The account's platform must match the draft's platform.

Example: social-hook draft connect draft-abc123 --account my-x-account

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Preview-mode draft ID to connect |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--account`, `-a` | string |  | Account name to connect (must match draft platform) |
| `--json` | boolean | false | Output as JSON |
| `--yes`, `-y` | boolean | false | Skip confirmation |

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

### `social-hook draft post-now`

Post a draft immediately to its platform.

Requires platform credentials in ~/.social-hook/.env.

Example: social-hook draft post-now draft_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to post immediately |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes`, `-y` | boolean | false | Skip confirmation prompt |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook draft promote`

Promote a preview draft to a real platform.

Creates a new draft for the target platform using the LLM drafter,
then marks the preview draft as superseded.

Example: social-hook draft promote draft-abc123 --platform x

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Preview draft ID to promote |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--platform`, `-p` | string |  | Target platform (e.g., x, linkedin) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook draft quick-approve`

Approve and schedule a draft for the next optimal posting time in one step.

Combines approve + schedule. Considers your configured posting limits,
preferred time windows, and minimum gap between posts to pick the best slot.

Example: social-hook draft quick-approve draft_abc123

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

### `social-hook draft reopen`

Reopen a cancelled or rejected draft.

Example: social-hook draft reopen draft-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to reopen |

---

### `social-hook draft retry`

Re-queue a failed draft for another posting attempt.

Resets the retry counter and sets status back to scheduled so
the scheduler will try posting it again.

Example: social-hook draft retry draft_abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to retry |

---

### `social-hook draft schedule`

Schedule a draft for posting at a specific or optimal time.

With --time, posts at that exact ISO datetime. Without --time,
automatically picks the next optimal slot based on your configured
posting limits, time windows, and minimum gap between posts.

Example: social-hook draft schedule draft_abc123
Example: social-hook draft schedule draft_abc123 --time 2026-03-25T10:00:00

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

### `social-hook draft unapprove`

Revert approval on a draft.

Example: social-hook draft unapprove draft-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to unapprove |

---

### `social-hook draft unschedule`

Revert scheduling on a draft.

Example: social-hook draft unschedule draft-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to unschedule |

---
