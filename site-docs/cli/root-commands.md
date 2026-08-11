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

---

### `social-hook events`

Watch live pipeline events (commits, decisions, drafts).

Example: social-hook events --json

---

### `social-hook help`

Show command help. Use --json for machine-readable output.

Examples: social-hook help draft, social-hook help draft approve, social-hook help --json

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

---

### `social-hook rate-limits`

Show current rate limit status (daily cap, gap timer, queue, cost).

Example: social-hook rate-limits
Example: social-hook --json rate-limits

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

Run the interactive setup wizard to configure social-hook — credentials, accounts, projects, and strategies. Use --only to configure a single component.

---

### `social-hook test`

Dry-run commit evaluation without creating drafts. Supports --output to save results and --compare to diff against a previous run.

---

### `social-hook trigger`

Run the full evaluation-to-draft pipeline for a single commit.

Evaluates the commit with the LLM, records a decision, and creates
drafts for each enabled platform if the commit is post-worthy.
This is the same pipeline the git post-commit hook runs automatically.
Use 'social-hook test' for dry-run evaluation without database writes.

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

---
