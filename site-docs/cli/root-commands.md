# social-hook commands

Top-level commands that are not part of a command group.

### `social-hook consolidation-tick`

Process held decisions — commits not post-worthy alone but interesting together.

When the evaluator marks a commit as 'hold', it means the commit isn't worth
a standalone post but could be combined with others. This command batches
those held decisions and either sends a summary notification (notify_only mode)
or re-evaluates the batch as a group (re_evaluate mode).

Typically run on a cron (e.g. every few hours) or by the bot daemon.

Example: social-hook consolidation-tick

---

### `social-hook discover`

Analyse your repo with LLM-powered two-pass discovery.

Pass 1: the AI selects the most important files from your repo listing.
Pass 2: reads those files and generates a project summary, per-file
summaries, and identifies key documentation. This context is used by
the evaluator and drafter in all future pipeline runs.

Usually run automatically by quickstart, but can be re-run to refresh
the project summary after significant changes.

Example: social-hook discover my-project-id

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

Zero-to-first-draft onboarding. Auto-detects your LLM provider,
registers your repo, imports commit history, runs AI project discovery,
and generates an introductory draft — all in one command.

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

Post scheduled drafts whose time has arrived and promote deferred drafts.

Checks for drafts with status 'scheduled' past their scheduled time and
posts them to their platform. Also promotes deferred drafts when scheduling
slots open up, and drains rate-limited evaluations.

Typically run on a cron (e.g. every minute) or by the bot daemon.

Example: social-hook scheduler-tick
Example: social-hook --dry-run scheduler-tick

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

Run the full evaluation-to-draft pipeline for a single commit.

Evaluates the commit with the LLM, records a decision, and creates
drafts for each enabled platform if the commit is post-worthy.
This is the same pipeline the git post-commit hook runs automatically.
Use 'social-hook test' for dry-run evaluation without database writes.

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

Start the web dashboard for managing your social-hook workflow visually.

Launches a Next.js frontend and FastAPI backend. From the dashboard you can
review and edit drafts, approve or reject posts, manage projects, configure
settings, monitor the pipeline in real time, and more.

Requires Node.js. Use --install to run npm install on first launch.

Example: social-hook web
Example: social-hook web --port 8080 --install

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--port`, `-p` | integer | 3000 | Port for Next.js dev server |
| `--api-port` | integer | 8741 | Port for FastAPI server |
| `--host` | string | 127.0.0.1 | Host to bind to |
| `--install` | boolean | false | Run npm install before starting |

---
