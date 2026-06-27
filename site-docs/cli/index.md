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
| [`arc`](arc.md) | Manage narrative arcs. Arcs are multi-post storylines that group related content under a theme, giving your audience a coherent thread to follow across posts. |
| [`bot`](bot.md) | Start, stop, and check status of the Telegram/Discord bot daemon. The bot provides an interactive chat interface for reviewing drafts, approving posts, and managing the pipeline. |
| [`brief`](brief.md) | View and edit the project brief used by the evaluator and drafter. |
| [`config`](config.md) | View and modify the Social Hook configuration. Read the full config as YAML, get individual values by dotted key path, or set scalar values without editing files directly. |
| [`content`](content.md) | Submit content ideas, combine topics, and trigger hero launch drafts. |
| [`credentials`](credentials.md) | Manage API keys and secrets in ~/.social-hook/.env. |
| [`cycles`](cycles.md) | Inspect evaluation cycle history and per-strategy outcomes. |
| [`decision`](decision.md) | Manage evaluation decisions. Decisions record whether a commit was deemed post-worthy by the LLM evaluator. Use these commands to list, delete, retrigger, rewind, or batch-evaluate decisions. |
| [`draft`](draft.md) | Manage the full draft lifecycle. Approve, reject, schedule, edit, redraft, promote, and post drafts. Also manage media attachments and view draft details and change history. |
| [`inspect`](inspect.md) | Inspect system state. View the event log, list pending drafts awaiting action, check LLM token usage, and see configured platform connections. |
| [`journey`](journey.md) | Control Development Journey capture. When enabled, Claude Code hooks record session narratives that feed into the evaluation pipeline as rich development context. |
| [`logs`](logs.md) | Query, tail, and manage log entries. View recent errors and warnings, follow live log output, clear old entries, and check overall system health across all pipeline components. |
| [`manual`](manual.md) | Run pipeline steps manually. Evaluate a commit, create drafts from a decision, consolidate multiple decisions into one draft, or post an approved draft — bypassing the automated scheduler. |
| [`media`](media.md) | Manage generated media assets. Run garbage collection to remove orphaned files from the media cache that are no longer referenced by any draft. |
| [`memory`](memory.md) | Manage voice memories. Voice memories are persistent style and tone instructions that the LLM drafter uses when generating content, such as 'avoid jargon' or 'use first person plural'. |
| [`project`](project.md) | Register and manage projects. A project links a git repository (or folder) to Social Hook so commits are evaluated, content is drafted, and briefs are maintained. |
| [`snapshot`](snapshot.md) | Save, restore, and manage database snapshots. Snapshots let you bookmark the full system state and roll back if needed. A safety backup is created automatically before any restore or reset. |
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
