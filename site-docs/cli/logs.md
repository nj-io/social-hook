# social-hook logs

Query and tail system logs, clear stored errors, and check overall health status across the bot, scheduler, and pipeline components.

---

### `social-hook logs clear`

Clear system errors from the database.

Without --older-than, deletes all errors. Prompts for confirmation
unless --yes is given.

Example: social-hook logs clear --yes
Example: social-hook logs clear --older-than 7

---

### `social-hook logs health`

Show overall system health status.

Displays error counts by severity in the last 24 hours.

Example: social-hook logs health
Example: social-hook logs health --json

---

### `social-hook logs tail`

Tail log files. Optionally filter by component.

Interactive terminal tool -- the web dashboard has the system tab for log viewing.

Example: social-hook logs tail trigger
Example: social-hook logs tail

---
