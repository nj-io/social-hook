# social-hook advisory

Manage advisory items — operator action items for manual tasks.

---

### `social-hook advisory complete`

Mark an advisory item as completed.

Use after you've taken the recommended action (e.g., posted an article
manually, set up a platform account).

Example: social-hook advisory complete advisory_abc123

---

### `social-hook advisory create`

Create an advisory item manually.

Advisory items track actions that need operator attention — posting
articles, setting up accounts, infrastructure changes, etc.

Example: social-hook advisory create --title "Set up LinkedIn" --category platform_presence
Example: social-hook advisory create -t "Post article draft" -c content_asset -u blocking

---

### `social-hook advisory dismiss`

Dismiss an advisory item.

Marks the item as dismissed with an optional reason. This is a
destructive operation — dismissed items are hidden from the active list.

Example: social-hook advisory dismiss advisory_abc123 --reason "Not applicable"

---

### `social-hook advisory list`

List advisory items for a project.

Shows action items that need operator attention — article posts,
platform setup, infrastructure tasks, etc.

Example: social-hook advisory list
Example: social-hook advisory list --status pending --urgency blocking

---
