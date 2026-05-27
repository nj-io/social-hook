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
| [`arc`](arc.md) | Manage narrative arcs that track thematic threads across multiple posts, maintaining storyline continuity for long-form content initiatives. |
| [`bot`](bot.md) | Manage the Telegram bot daemon that delivers draft previews, approval buttons, and scheduling prompts to your chat. |
| [`brief`](brief.md) | View and edit the project brief used by the evaluator and drafter. |
| [`config`](config.md) | View and modify configuration. |
| [`content`](content.md) | Submit content ideas, combine topics, and trigger hero launch drafts. |
| [`credentials`](credentials.md) | Manage API keys and secrets in ~/.social-hook/.env. |
| [`cycles`](cycles.md) | Inspect evaluation cycle history and per-strategy outcomes. |
| [`decision`](decision.md) | Browse and manage evaluator decisions: view the verdict history for commits, re-trigger evaluation, rewind decisions, or batch-evaluate deferred items. |
| [`draft`](draft.md) | Manage drafts through their full lifecycle: approve, reject, schedule, edit, redraft, and post content across platforms. |
| [`inspect`](inspect.md) | Inspect pipeline state and resource usage: view decision logs, pending drafts, LLM token costs, and configured platforms. |
| [`journey`](journey.md) | Control Development Journey capture. When enabled, Claude Code hooks record session narratives that feed into the evaluation pipeline as rich development context. |
| [`logs`](logs.md) | Log queries, tailing, and health. |
| [`manual`](manual.md) | Run pipeline stages by hand: evaluate a commit, create drafts from a decision, consolidate multiple commits, or post a draft immediately. |
| [`media`](media.md) | Manage the media cache: garbage-collect orphaned image and video files no longer referenced by any draft. |
| [`memory`](memory.md) | Store and recall voice memories — short feedback notes from draft rejections that teach the drafter your preferences over time. |
| [`project`](project.md) | Register and manage projects. A project links a git repository (or folder) to Social Hook so commits are evaluated, content is drafted, and briefs are maintained. |
| [`snapshot`](snapshot.md) | Save and restore database snapshots for safe experimentation and rollback. Snapshots capture all decisions, drafts, and posts at a point in time. |
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
