# social-hook manual

Manual operations.

---

### `social-hook manual consolidate`

Consolidate multiple decisions into a single draft.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `decision_ids` | yes | Decision IDs to consolidate (at least 2) |

---

### `social-hook manual draft`

Manually create drafts from an existing decision.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `decision_id` | yes | Decision ID to create draft for |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--platform` | string |  | Target platform (default: all enabled) |

---

### `social-hook manual evaluate`

Manually evaluate a commit through the full pipeline.

Runs the same evaluation and drafting pipeline as the automatic hook trigger.

Example: social-hook manual evaluate abc1234 --repo /path/to/repo

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `commit` | yes | Commit hash to evaluate |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--repo` | string |  | Repository path |

---

### `social-hook manual post`

Manually post an approved draft.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to post |

---
