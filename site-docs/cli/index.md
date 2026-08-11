# social-hook CLI Reference

Automated social media content from development activity.

## Global Options

These options can be placed before any command.


## Command Groups

| Group | Description |
|-------|-------------|
| [`account`](account.md) | Manage OAuth-authenticated platform accounts (X, LinkedIn). |
| [`advisory`](advisory.md) | Manage advisory items — operator action items for manual tasks. |
| [`arc`](arc.md) | Manage narrative arcs — multi-episode story threads that give your content thematic continuity across posts. |
| [`bot`](bot.md) | Manage the bot daemon — a long-running process that sends draft notifications, handles chat commands, and runs scheduled ticks. |
| [`brief`](brief.md) | View and edit the project brief used by the evaluator and drafter. |
| [`config`](config.md) | View and modify configuration — show the resolved config tree, get individual keys, or set values. |
| [`content`](content.md) | Submit content ideas, combine topics, and trigger hero launch drafts. |
| [`credentials`](credentials.md) | Manage API keys and secrets in ~/.social-hook/.env. |
| [`cycles`](cycles.md) | Inspect evaluation cycle history and per-strategy outcomes. |
| [`decision`](decision.md) | View and manage evaluation decisions — the evaluator's per-commit verdicts on what to draft and how. |
| [`draft`](draft.md) | Manage the full draft lifecycle — approve, reject, schedule, edit, redraft, post, and more. |
| [`inspect`](inspect.md) | Inspect pipeline state — query the event log, view pending evaluations, check LLM token usage, and list connected platforms. |
| [`journey`](journey.md) | Control Development Journey capture. When enabled, Claude Code hooks record session narratives that feed into the evaluation pipeline as rich development context. |
| [`logs`](logs.md) | Log queries, tailing, and health. |
| [`manual`](manual.md) | Run pipeline stages manually — evaluate commits, draft content, or post to a platform without automated triggers. |
| [`media`](media.md) | Manage generated media — garbage-collect orphaned image files no longer referenced by any draft. |
| [`memory`](memory.md) | Manage voice memories — persistent style notes that shape how the drafter writes (tone, preferences, pet peeves). |
| [`project`](project.md) | Register and manage projects. A project links a git repository (or folder) to Social Hook so commits are evaluated, content is drafted, and briefs are maintained. |
| [`snapshot`](snapshot.md) | Save and restore database snapshots for testing, debugging, or reverting to a known state. |
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
| [`setup`](root-commands.md#social-hook-setup) | Configure social-hook interactively — credentials, accounts, targets, and scheduling. Use --only to run a single section. |
| [`test`](root-commands.md#social-hook-test) | Dry-run commit evaluation without creating drafts. Use --output and --compare for regression testing. |
| [`trigger`](root-commands.md#social-hook-trigger) | Run the full evaluation-to-draft pipeline for a single commit. |
| [`version`](root-commands.md#social-hook-version) | Show version information. |
| [`web`](root-commands.md#social-hook-web) | Start the web dashboard for managing your social-hook workflow visually. |
