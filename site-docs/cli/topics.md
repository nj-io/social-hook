# social-hook topics

Manage the prioritised content topic queue per strategy.

---

### `social-hook topics add`

Add a new topic to the queue.

Topics track areas of content to cover for a strategy.
New topics start with 'uncovered' status and priority rank 0.

Example: social-hook topics add --strategy technical --topic "evaluation pipeline" --description "How we built the evaluation system"

---

### `social-hook topics dismiss`

Dismiss a topic so no posts are created about it.

Dismissed topics are hidden from the queue and will not be recreated
by auto-seeding. Use 'topics list --include-dismissed' to see them.

Example: social-hook topics dismiss topic_abc123
Example: social-hook topics dismiss topic_abc123 --yes  (skip confirmation)

---

### `social-hook topics draft-now`

Force-draft a held or uncovered topic via LLM evaluation and drafting.

Topics with status 'holding' or 'uncovered' can be force-drafted. Runs the
full evaluation and drafting pipeline (same as the web UI "Draft Now" button).
This is an LLM operation — may take a moment.

Example: social-hook topics draft-now topic_abc123

---

### `social-hook topics list`

List all topics, grouped by strategy.

Shows the content topic queue with status, commit count, and priority.
Use --strategy to filter by a specific strategy. Dismissed topics are
hidden by default; use --include-dismissed to show them.

Example: social-hook topics list --strategy building-public

---

### `social-hook topics reorder`

Reorder a topic within its strategy by setting its priority rank.

Higher rank = higher priority. Inserts topic at rank, shifts others down.

Example: social-hook topics reorder --strategy technical --id topic_abc123 --rank 1

---

### `social-hook topics status`

Set a topic's status.

Valid statuses: uncovered, holding, partial, covered, dismissed.

Example: social-hook topics status topic_abc123 covered

---
