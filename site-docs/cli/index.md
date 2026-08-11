# social-hook CLI Reference

Automated social media content from development activity.

## Global Options

These options can be placed before any command.


## Command Groups

| Group | Description |
|-------|-------------|
| [`account`](account.md) | Manage OAuth-authenticated platform accounts (X, LinkedIn). |
| [`advisory`](advisory.md) | Manage advisory items — operator action items for manual tasks. |
| [`arc`](arc.md) | Manage narrative arcs — multi-post storylines that group related commits into coherent threads over days or weeks. |
| [`bot`](bot.md) | Control the background bot daemon that continuously runs scheduler-tick and consolidation-tick to automate posting. |
| [`brief`](brief.md) | View and edit the project brief used by the evaluator and drafter. |
| [`config`](config.md) | View and edit the YAML configuration. Use dotted key paths to read or update individual settings (e.g., social-hook config set posting.interval_hours 4). |
| [`content`](content.md) | Submit content ideas, combine topics, and trigger hero launch drafts. |
| [`credentials`](credentials.md) | Manage API keys and secrets in ~/.social-hook/.env. |
| [`cycles`](cycles.md) | Inspect evaluation cycle history and per-strategy outcomes. |
| [`decision`](decision.md) | Manage evaluator decisions on commits. Delete decisions and their associated drafts, re-trigger evaluation, or batch-evaluate grouped decisions. |
| [`draft`](draft.md) | Manage the full draft lifecycle: approve, reject, schedule, cancel, edit content, manage attached media, and control posting. |
| [`inspect`](inspect.md) | Query system state: view the decision log, list pending drafts, check LLM token usage and costs, and see platform configuration status. |
| [`journey`](journey.md) | Control Development Journey capture. When enabled, Claude Code hooks record session narratives that feed into the evaluation pipeline as rich development context. |
| [`logs`](logs.md) | Query, tail, and manage application logs. Check system health and clear old log entries. |
| [`manual`](manual.md) | Manually trigger individual pipeline steps outside automation: evaluate commits, create drafts, consolidate multi-commit posts, or post immediately. |
| [`media`](media.md) | Manage generated media assets. Garbage-collect orphaned media files that are no longer referenced by any draft. |
| [`memory`](memory.md) | Store and manage voice memories — short feedback snippets and editorial preferences that guide the drafting LLM's tone and style. |
| [`project`](project.md) | Register and manage projects. A project links a git repository (or folder) to Social Hook so commits are evaluated, content is drafted, and briefs are maintained. |
| [`snapshot`](snapshot.md) | Create, restore, and manage point-in-time database snapshots for backup, recovery, or testing. |
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
