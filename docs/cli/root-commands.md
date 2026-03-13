# social-hook commands

Top-level commands that are not part of a command group.

### `social-hook consolidation-tick`

Run one consolidation tick: process batched decisions.

---

### `social-hook discover`

Run two-pass project discovery and print results.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `project_id` | yes | Project ID to discover |

---

### `social-hook events`

Watch live pipeline events (commits, decisions, drafts).

Example: social-hook events --json

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--since` | integer | -1 | Start from event ID (0=all history, -1=current, default: current) |
| `--entity`, `-e` | string |  | Filter by entity type (pipeline, decision, draft) |
| `--follow`, `-f`, `--no-follow` | boolean | true | Follow new events in real time |
| `--json` | boolean | false | Output as JSON |

---

### `social-hook help`

Show command help. Use --json for machine-readable output.

Examples: social-hook help draft, social-hook help draft approve, social-hook help --json

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as structured JSON |

---

### `social-hook init`

Initialize social-hook (create directories and database).

Creates ~/.social-hook/ with config templates and an empty database.
For guided setup with platform credentials, use 'social-hook setup' instead.

---

### `social-hook quickstart`

Run the quickstart flow.

**Arguments:**

| Name | Required | Description |
|------|----------|-------------|
| `path` | no | Repository path (default: current directory) |

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--key` | string |  | Anthropic API key (skips prompt) |
| `--evaluate-last` | integer | 0 | Evaluate last N commits for additional drafts (max 5) |
| `--yes`, `-y` | boolean | false | Skip all confirmation prompts |
| `--json` | boolean | false | JSON output |

---

### `social-hook rate-limits`

Show current rate limit status (daily cap, gap timer, queue, cost).

Example: social-hook rate-limits
Example: social-hook --json rate-limits

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | boolean | false | Output as JSON |

---

### `social-hook scheduler-tick`

Run one scheduler tick: post all due drafts.

---

### `social-hook setup`

Configure social-hook.

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--validate` | boolean | false | Validate existing configuration only |
| `--only` | string |  | Configure only a specific component (models, apikeys, voice, telegram, platforms, x, linkedin, image, scheduling, journey, web) |
| `--advanced`, `--no-advanced` | boolean |  | Include advanced sections (models, media, scheduling, etc.) |

---

### `social-hook test`

Test commit evaluation.

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--repo` | string |  | Repository path |
| `--commit` | string |  | Single commit hash |
| `--last` | integer | 0 | Test N most recent commits |
| `--from` | string |  | Start of commit range |
| `--to` | string |  | End of commit range |
| `--compare` | path |  | Compare results to golden JSON file |
| `--output`, `-o` | path |  | Save results to JSON file |
| `--show-prompt` | boolean | false | Print the full LLM prompt to stderr |

---

### `social-hook trigger`

Evaluate a commit and create draft if post-worthy (called by hook).

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--commit` | string |  | Commit hash to evaluate |
| `--repo` | string |  | Repository path |

---

### `social-hook version`

Show version information.

---

### `social-hook web`

Start the web dashboard (Next.js + FastAPI).

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--port`, `-p` | integer | 3000 | Port for Next.js dev server |
| `--api-port` | integer | 8741 | Port for FastAPI server |
| `--host` | string | 127.0.0.1 | Host to bind to |
| `--install` | boolean | false | Run npm install before starting |

---
