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
| [`arc`](arc.md) | Manage narrative arcs — multi-episode story threads the drafter weaves across posts within a strategy. |
| [`bot`](bot.md) | Start, stop, and check the status of the bot daemon that listens for chat commands. |
| [`brief`](brief.md) | View and edit the project brief used by the evaluator and drafter. |
| [`config`](config.md) | View and modify configuration values. Use 'show' for the full config, 'get' for a single key, or 'set' to update a value. |
| [`content`](content.md) | Submit content ideas, combine topics, and trigger hero launch drafts. |
| [`credentials`](credentials.md) | Manage API keys and secrets in ~/.social-hook/.env. |
| [`cycles`](cycles.md) | Inspect evaluation cycle history and per-strategy outcomes. |
| [`decision`](decision.md) | View, delete, retrigger, or rewind evaluation decisions from the pipeline log. |
| [`draft`](draft.md) | Draft lifecycle — approve, reject, schedule, edit, redraft, cancel, and post content drafts. |
| [`inspect`](inspect.md) | View decision log, pending drafts, LLM token usage, and connected platform capabilities. |
| [`journey`](journey.md) | Control Development Journey capture. When enabled, Claude Code hooks record session narratives that feed into the evaluation pipeline as rich development context. |
| [`logs`](logs.md) | Query, tail, and clear application event logs. Includes a health check for pipeline and LogBus status. |
| [`manual`](manual.md) | Manually trigger pipeline stages — evaluate a commit, create a draft, consolidate holds, or post a scheduled draft. |
| [`media`](media.md) | Manage generated media assets. Use 'gc' to garbage-collect orphaned media files. |
| [`memory`](memory.md) | Manage voice memories — persistent style and tone notes the drafter references when composing content. |
| [`project`](project.md) | Register and manage projects. A project links a git repository (or folder) to Social Hook so commits are evaluated, content is drafted, and briefs are maintained. |
| [`snapshot`](snapshot.md) | Save, restore, list, and delete database snapshots for backup and experimentation. |
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
| [`setup`](root-commands.md#social-hook-setup) | Run the interactive setup wizard to configure social-hook — credentials, accounts, projects, and strategies. Use --only to configure a single component. |
| [`test`](root-commands.md#social-hook-test) | Dry-run commit evaluation without creating drafts. Supports --output to save results and --compare to diff against a previous run. |
| [`trigger`](root-commands.md#social-hook-trigger) | Run the full evaluation-to-draft pipeline for a single commit. |
| [`version`](root-commands.md#social-hook-version) | Show version information. |
| [`web`](root-commands.md#social-hook-web) | Start the web dashboard for managing your social-hook workflow visually. |
