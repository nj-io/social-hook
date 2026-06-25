# social-hook media

Media cache maintenance. Garbage-collect orphaned files from the media cache that are no longer referenced by any draft.

---

### `social-hook media gc`

Remove orphaned files from media cache.

Example: social-hook media gc --dry-run
Example: social-hook media gc --yes  (skip confirmation)

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dry-run` | boolean | false | Show what would be removed |
| `--yes`, `-y` | boolean | false | Skip confirmation prompt |

---
