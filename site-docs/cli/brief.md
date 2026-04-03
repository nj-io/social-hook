# social-hook brief

View and edit the project brief used by the evaluator and drafter.

---

### `social-hook brief edit`

Open the project brief in $EDITOR.

Loads the current brief into a temporary file, opens in your editor
(VISUAL -> EDITOR -> vi), and saves changes back to the database.

Example: social-hook brief edit

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook brief show`

View the project brief.

Shows the structured project summary used by the evaluator and drafter
for context. Sections: What It Does, Key Capabilities, Technical
Architecture, Current State.

Example: social-hook brief show

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--project`, `-p` | string |  | Repository path (default: cwd) |
| `--json` | boolean | false | Output as JSON |

---
