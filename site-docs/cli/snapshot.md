# social-hook snapshot

Create, restore, and manage point-in-time database snapshots for backup, recovery, or testing.

---

### `social-hook snapshot delete`

Delete a saved snapshot.

Example: social-hook snapshot delete old-snapshot --yes

---

### `social-hook snapshot list`

List saved snapshots.

Example: social-hook snapshot list

---

### `social-hook snapshot reset`

Reset database to empty state (backs up current DB first).

Example: social-hook snapshot reset --yes

---

### `social-hook snapshot restore`

Restore a database snapshot (backs up current DB first).

Example: social-hook snapshot restore before-refactor
Example: social-hook snapshot restore before-refactor --yes  (skip confirmation)

---

### `social-hook snapshot save`

Save a snapshot of the current database.

Example: social-hook snapshot save before-refactor
Example: social-hook snapshot save before-refactor --yes  (overwrite without prompting)

---
