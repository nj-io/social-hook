# social-hook draft

Draft lifecycle management.

---

### `social-hook draft approve`

Mark a draft as approved for posting.

The scheduler will post it when its scheduled time arrives.
Preview drafts must be promoted to a platform first.

Example: social-hook draft approve draft_abc123

---

### `social-hook draft cancel`

Cancel a pending draft, removing it from the posting queue.

Example: social-hook draft cancel draft_abc123

---

### `social-hook draft connect`

Connect a preview-mode draft to an account.

Links the draft's target to an existing OAuth account, clearing preview mode.
The account's platform must match the draft's platform.

Example: social-hook draft connect draft-abc123 --account my-x-account
Example: social-hook draft connect draft-abc123 --account my-x-account --yes  (skip confirmation)

---

### `social-hook draft edit`

Edit draft content.

Records the change in the draft's change history (visible in draft show).
If the draft is a thread, tweet boundaries are automatically re-split.

Example: social-hook draft edit draft-abc123 --content "Updated post text here"

---

### `social-hook draft list`

List drafts with optional filters.

Example: social-hook draft list --pending --json
Example: social-hook draft list --decision decision-abc123
Example: social-hook draft list --commit 47a5191
Example: social-hook draft list --tag auth

---

### `social-hook draft media-edit`

Edit the media spec for a draft.

The media spec is a JSON object that controls media generation (e.g.,
code snippet, language, theme). After editing, run media-regen to
produce a new media file from the updated spec.

Example: social-hook draft media-edit draft-abc123 --spec '{"code": "print(42)", "language": "python"}'

---

### `social-hook draft media-regen`

Regenerate media for a draft using its stored media spec.

The media spec is a JSON object describing what to generate (e.g., code
snippet image, diagram). Edit the spec first with media-edit, then run
this command to produce a new file from the updated spec.

Example: social-hook draft media-regen draft-abc123

---

### `social-hook draft media-remove`

Remove media from a draft.

Example: social-hook draft media-remove draft-abc123

---

### `social-hook draft post-now`

Post a draft immediately to its platform.

Requires platform credentials in ~/.social-hook/.env.

Example: social-hook draft post-now draft_abc123
Example: social-hook draft post-now draft_abc123 --yes  (skip confirmation)

---

### `social-hook draft promote`

Promote a preview draft to a real platform.

Creates a new draft for the target platform using the LLM drafter,
then marks the preview draft as superseded.

Example: social-hook draft promote draft-abc123 --platform x

---

### `social-hook draft quick-approve`

Approve and schedule a draft for the next optimal posting time in one step.

Combines approve + schedule. Considers your configured posting limits,
preferred time windows, and minimum gap between posts to pick the best slot.

Example: social-hook draft quick-approve draft_abc123

---

### `social-hook draft redraft`

Redraft content using the Expert agent with a new angle.

Calls the Expert LLM agent to rewrite the draft with a different
direction. May also update the media spec. Changes are recorded
in the draft's change history.

Example: social-hook draft redraft draft-abc123 --angle "focus on the performance gains"

---

### `social-hook draft reject`

Reject a draft and optionally record feedback as voice memory.

When --reason is provided, the feedback is saved to voice memory so the
drafter learns from it in future runs. If the draft is an intro draft,
rejection cascades to re-draft the introduction for that platform.

Example: social-hook draft reject draft-abc123 --reason "too technical for the audience"

---

### `social-hook draft reopen`

Reopen a cancelled or rejected draft, returning it to 'draft' status.

Intro drafts cannot be reopened -- create a new draft instead.
Clears any previous error message on the draft.

Example: social-hook draft reopen draft-abc123

---

### `social-hook draft retry`

Re-queue a failed draft for another posting attempt.

Resets the retry counter and sets status back to scheduled so
the scheduler will try posting it again.

Example: social-hook draft retry draft_abc123

---

### `social-hook draft schedule`

Schedule a draft for posting at a specific or optimal time.

With --time, posts at that exact ISO datetime. Without --time,
automatically picks the next optimal slot based on your configured
posting limits, time windows, and minimum gap between posts.

Example: social-hook draft schedule draft_abc123
Example: social-hook draft schedule draft_abc123 --time 2026-03-25T10:00:00

---

### `social-hook draft show`

Show full detail for a draft including media spec and change history.

Example: social-hook draft show draft-abc123

---

### `social-hook draft unapprove`

Revert approval on a draft, returning it to 'draft' status.

Use when you approved a draft prematurely and want to make further
edits before scheduling or posting.

Example: social-hook draft unapprove draft-abc123

---

### `social-hook draft unschedule`

Revert scheduling on a draft, returning it to 'draft' status.

Clears the scheduled time. Use when you need to edit or reschedule
a draft that was already queued for posting.

Example: social-hook draft unschedule draft-abc123

---
