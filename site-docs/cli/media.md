# social-hook media

Media cache management — clean up orphaned generated images.

---

### `social-hook media gc`

Remove orphaned files from media cache.

Orphaned media are cache directories whose associated draft
no longer exists in the database (e.g. after draft deletion).
Use --dry-run to preview what would be removed.

Example: social-hook media gc --dry-run
Example: social-hook media gc --yes

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dry-run` | boolean | false | Show what would be removed |
| `--yes`, `-y` | boolean | false | Skip confirmation prompt |

---
