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
| [`account`](account.md) | Platform account management. |
| [`arc`](arc.md) | Manage narrative arcs. |
| [`bot`](bot.md) | Bot daemon management. |
| [`brief`](brief.md) | Project brief management. |
| [`config`](config.md) | View and modify configuration. |
| [`content`](content.md) | Content suggestions and operations. |
| [`credentials`](credentials.md) | Platform credential management. |
| [`cycles`](cycles.md) | Evaluation cycle history. |
| [`decision`](decision.md) | Decision management. |
| [`draft`](draft.md) | Draft lifecycle management. |
| [`inspect`](inspect.md) | Inspect system state. |
| [`journey`](journey.md) | Development Journey capture. |
| [`logs`](logs.md) | Log queries, tailing, and health. |
| [`manual`](manual.md) | Manual operations. |
| [`media`](media.md) | Media management. |
| [`memory`](memory.md) | Manage voice memories. |
| [`project`](project.md) | Project management. |
| [`snapshot`](snapshot.md) | DB snapshot management. |
| [`strategy`](strategy.md) | Content strategy management. |
| [`target`](target.md) | Content distribution targets. |
| [`topics`](topics.md) | Content topic queue. |

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
