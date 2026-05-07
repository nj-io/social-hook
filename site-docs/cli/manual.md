# social-hook manual

Run pipeline steps manually — evaluate a commit, draft content, consolidate holds, or post a draft — bypassing the scheduler.

---

### `social-hook manual consolidate`

Consolidate multiple decisions into a single draft.

Combines two or more commit decisions into one draft when individual
commits are too small to post alone. All decisions must belong to the
same project. The most recent decision is used as the anchor.

Example: social-hook manual consolidate decision-aaa decision-bbb decision-ccc

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `decision_ids` | yes | Decision IDs to consolidate (at least 2) |

---

### `social-hook manual draft`

Manually create drafts from an existing decision.

Use when a decision exists but drafts were not generated automatically
(e.g., after a rewind). Calls the LLM drafter to produce platform-specific
content for all enabled platforms, or a single platform with --platform.

Example: social-hook manual draft decision-abc123 --platform x

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

Posts immediately rather than waiting for the scheduler. The draft must
be in a pending status (draft, approved, scheduled, or deferred) and
have a connected account (not in preview mode).

Example: social-hook manual post draft-abc123

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `draft_id` | yes | Draft ID to post |

---
