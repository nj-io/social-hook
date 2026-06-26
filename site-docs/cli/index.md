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
| [`arc`](arc.md) | Manage narrative arcs. Create, complete, abandon, or resume multi-post story arcs that give the drafter thematic continuity across a series of posts. |
| [`bot`](bot.md) | Bot daemon management. Start, stop, and check the status of the Telegram/Discord bot that lets you approve, reject, and schedule drafts from chat. |
| [`brief`](brief.md) | View and edit the project brief used by the evaluator and drafter. |
| [`config`](config.md) | View and modify configuration. Show the full config as YAML, get individual values by dotted key path, or set values at runtime. |
| [`content`](content.md) | Submit content ideas, combine topics, and trigger hero launch drafts. |
| [`credentials`](credentials.md) | Manage API keys and secrets in ~/.social-hook/.env. |
| [`cycles`](cycles.md) | Inspect evaluation cycle history and per-strategy outcomes. |
| [`decision`](decision.md) | Decision management. List, delete, retrigger, or rewind evaluation decisions. Supports batch evaluation and full pipeline re-runs from a commit. |
| [`draft`](draft.md) | Draft lifecycle management. Approve, reject, schedule, edit, redraft, and post drafts. Covers the full workflow from initial draft through review to publication. |
| [`inspect`](inspect.md) | Inspect system state. View the decision log, pending drafts, configured platforms, and LLM token usage across projects. |
| [`journey`](journey.md) | Control Development Journey capture. When enabled, Claude Code hooks record session narratives that feed into the evaluation pipeline as rich development context. |
| [`logs`](logs.md) | Log queries, tailing, and health. |
| [`manual`](manual.md) | Manual operations. Evaluate commits, create drafts, consolidate multiple decisions, and post approved drafts outside the automated pipeline. |
| [`media`](media.md) | Media management. Clean up orphaned files from the media cache to reclaim disk space. |
| [`memory`](memory.md) | Manage voice memories. Add, list, and delete per-project voice memories that guide the LLM's tone, style, and content preferences during drafting. |
| [`project`](project.md) | Register and manage projects. A project links a git repository (or folder) to Social Hook so commits are evaluated, content is drafted, and briefs are maintained. |
| [`snapshot`](snapshot.md) | DB snapshot management. Save, restore, reset, list, and delete database snapshots for backup, testing, or recovery. |
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
| [`setup`](root-commands.md#social-hook-setup) | Configure social-hook. |
| [`test`](root-commands.md#social-hook-test) | Test commit evaluation. |
| [`trigger`](root-commands.md#social-hook-trigger) | Run the full evaluation-to-draft pipeline for a single commit. |
| [`version`](root-commands.md#social-hook-version) | Show version information. |
| [`web`](root-commands.md#social-hook-web) | Start the web dashboard for managing your social-hook workflow visually. |
