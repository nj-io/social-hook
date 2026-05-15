# social-hook CLI Reference

Automated social media content from development activity.

## Global Options

These options can be placed before any command.

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--config`, `-c` | path |  | Override config location |
| `--dry-run` | boolean | false | Run full pipeline without posting or DB writes (for testing) |
| `--verbose`, `-v` | boolean | false | Verbose output |
| `--json` | boolean | false | JSON output for scripting |

## Command Groups

| Group | Description |
|-------|-------------|
| [`account`](account.md) | Manage OAuth-authenticated platform accounts (X, LinkedIn). |
| [`advisory`](advisory.md) | Manage advisory items — operator action items for manual tasks. |
| [`arc`](arc.md) | Manage narrative arcs — multi-post story threads that give the evaluator and drafter continuity across related commits. |
| [`bot`](bot.md) | Start, stop, and monitor the bot daemon. The daemon listens for platform messages (Telegram, Discord) and surfaces drafts, approvals, and scheduling via chat commands. |
| [`brief`](brief.md) | View and edit the project brief used by the evaluator and drafter. |
| [`config`](config.md) | View and modify config.yaml via dotted key paths (e.g., scheduling.optimal_hours). Changes persist to disk immediately. |
| [`content`](content.md) | Submit content ideas, combine topics, and trigger hero launch drafts. |
| [`credentials`](credentials.md) | Manage API keys and secrets in ~/.social-hook/.env. |
| [`cycles`](cycles.md) | Inspect evaluation cycle history and per-strategy outcomes. |
| [`decision`](decision.md) | Manage evaluation decisions — list, delete, retrigger, batch-evaluate, or rewind decisions and their downstream drafts. |
| [`draft`](draft.md) | Full draft lifecycle — approve, reject, schedule, edit, redraft, promote, and post. Covers the entire path from LLM-generated content to published post. |
| [`inspect`](inspect.md) | Inspect system state — view the decision log, pending drafts, token usage, and configured platforms. |
| [`journey`](journey.md) | Control Development Journey capture. When enabled, Claude Code hooks record session narratives that feed into the evaluation pipeline as rich development context. |
| [`logs`](logs.md) | Query and tail system logs, clear stored errors, and check overall health status across the bot, scheduler, and pipeline components. |
| [`manual`](manual.md) | Manually trigger pipeline stages — evaluate a commit, create a draft from a decision, consolidate multiple decisions, or post an approved draft. |
| [`media`](media.md) | Manage generated media assets (images, diagrams). Currently provides garbage collection to remove orphaned cache files. |
| [`memory`](memory.md) | Manage voice memories — persistent style notes that guide the drafter's tone, vocabulary, and formatting choices across all future drafts. |
| [`project`](project.md) | Register and manage projects. A project links a git repository (or folder) to Social Hook so commits are evaluated, content is drafted, and briefs are maintained. |
| [`snapshot`](snapshot.md) | Save, restore, and manage database snapshots. Useful for testing, reverting state, or branching experiments without losing data. |
| [`strategy`](strategy.md) | View and customize content strategies (voice, audience, editorial rules). |
| [`target`](target.md) | Configure where content is distributed (account + destination + strategy). |
| [`topics`](topics.md) | Manage the prioritised content topic queue per strategy. |

## Commands

| Command | Description |
|---------|-------------|
| [`consolidation-tick`](root-commands.md#social-hook-consolidation-tick) | Process held decisions — commits not post-worthy alone but interesting together. |
| [`discover`](root-commands.md#social-hook-discover) | Analyse your repo with LLM-powered two-pass discovery. |
| [`events`](root-commands.md#social-hook-events) | Watch live pipeline events (commits, decisions, drafts). |
| [`help`](root-commands.md#social-hook-help) | Show command help. Use --json for machine-readable output. |
| [`init`](root-commands.md#social-hook-init) | Initialize social-hook (create directories and database). |
| [`quickstart`](root-commands.md#social-hook-quickstart) | Run the quickstart flow. |
| [`rate-limits`](root-commands.md#social-hook-rate-limits) | Show current rate limit status (daily cap, gap timer, queue, cost). |
| [`scheduler-tick`](root-commands.md#social-hook-scheduler-tick) | Post scheduled drafts whose time has arrived and promote deferred drafts. |
| [`setup`](root-commands.md#social-hook-setup) | Run the interactive setup wizard for social-hook. Walks through project registration, platform credentials, content strategy, and scheduling. Bypass with --only to configure a single component. |
| [`test`](root-commands.md#social-hook-test) | Dry-run commit evaluation without creating decisions or drafts. Supports --output to save results and --compare to diff against a previous run for regression testing. |
| [`trigger`](root-commands.md#social-hook-trigger) | Run the full evaluation-to-draft pipeline for a single commit. |
| [`version`](root-commands.md#social-hook-version) | Show version information. |
| [`web`](root-commands.md#social-hook-web) | Start the web dashboard for managing your social-hook workflow visually. |
