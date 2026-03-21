# config.yaml

Infrastructure configuration for social-hook. Controls models, platforms, scheduling, channels, and media generation.

## Location

| Priority | Location |
|----------|----------|
| 1 | `--config` / `-c` CLI flag |
| 2 | `SOCIAL_HOOK_CONFIG` environment variable |
| 3 | `~/.social-hook/config.yaml` (default) |

## Interactive setup

```bash
social-hook setup                  # Full wizard
social-hook setup --only apikeys   # Just API keys
social-hook setup --only platforms # Just platforms
social-hook config show            # View current config
social-hook config show --content  # View content-config.yaml
social-hook config get models.evaluator
social-hook config set scheduling.timezone America/Los_Angeles
social-hook config set context.max_discovery_tokens 80000 --content  # Edit content config
```

---

## models

LLM model selection. Format: `provider/model-id`.

Known providers: `anthropic`, `claude-cli`, `openai`, `openrouter`, `ollama`.

| Field | Default | Description |
|-------|---------|-------------|
| `evaluator` | `anthropic/claude-opus-4-5` | Evaluates commits, makes draft/skip decisions, runs discovery |
| `drafter` | `anthropic/claude-opus-4-5` | Drafts social media content |
| `gatekeeper` | `anthropic/claude-haiku-4-5` | Lightweight checks, project summaries |

```yaml
models:
  evaluator: anthropic/claude-opus-4-5
  drafter: anthropic/claude-opus-4-5
  gatekeeper: anthropic/claude-haiku-4-5
```

---

## platforms

Each key is a platform name. Built-in platforms: `x`, `linkedin`. Custom platform names are also supported.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Whether this platform is active |
| `priority` | string | `"secondary"` | `"primary"` or `"secondary"` — affects smart defaults |
| `type` | string | auto | `"builtin"` for x/linkedin, `"custom"` otherwise |
| `account_tier` | string | — | X-specific: `"free"` (280 chars), `"basic"`, `"premium"`, `"premium_plus"` (25000 chars) |
| `description` | string | — | Extra context for the drafter (custom platforms) |
| `format` | string | — | Output format hint (e.g., `"tweet"`, `"post"`, `"article"`) |
| `max_length` | int | — | Character limit. `null` = no limit |
| `filter` | string | smart default | Content filter: `"all"`, `"notable"`, `"significant"` |
| `frequency` | string | smart default | Posting frequency: `"high"`, `"moderate"`, `"low"`, `"minimal"` |
| `scheduling` | object | — | Per-platform scheduling overrides |

### Smart defaults

When `filter` and `frequency` are omitted, they resolve based on platform name and priority:

| Platform | Primary | Secondary |
|----------|---------|-----------|
| x | filter=`all`, freq=`high` | filter=`notable`, freq=`moderate` |
| linkedin | filter=`notable`, freq=`moderate` | filter=`significant`, freq=`low` |
| custom | filter=`notable`, freq=`moderate` | filter=`significant`, freq=`low` |

### Content filters

| Filter | Episode types that pass |
|--------|------------------------|
| `all` | Everything |
| `notable` | milestone, launch, synthesis, demo_proof, before_after, postmortem |
| `significant` | milestone, launch, synthesis |

### Frequency presets

| Frequency | max_posts_per_day | min_gap_minutes |
|-----------|-------------------|-----------------|
| `high` | 3 | 30 |
| `moderate` | 1 | 120 |
| `low` | 1 | 2880 (2 days) |
| `minimal` | 1 | 10080 (7 days) |

```yaml
platforms:
  x:
    enabled: true
    priority: primary
    account_tier: free
  linkedin:
    enabled: true
    priority: secondary
```

---

## scheduling

Global scheduling defaults. Per-platform overrides take precedence.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timezone` | string | `"UTC"` | IANA timezone (e.g., `"America/Los_Angeles"`) |
| `max_posts_per_day` | int | `3` | Maximum posts per day |
| `min_gap_minutes` | int | `30` | Minimum gap between posts |
| `optimal_days` | list | `["Tue", "Wed", "Thu"]` | Preferred posting days |
| `optimal_hours` | list | `[9, 12, 17]` | Preferred posting hours (24h) |
| `max_per_week` | int | `10` | Maximum posts per week |
| `thread_min_tweets` | int | `4` | Minimum tweets in an X thread |

```yaml
scheduling:
  timezone: America/New_York
  max_posts_per_day: 2
  min_gap_minutes: 60
  optimal_days: [Mon, Tue, Wed, Thu, Fri]
  optimal_hours: [9, 12, 17]
```

---

## media_generation

Controls which media tools are available for draft content.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Master toggle for all media generation |
| `tools.mermaid` | bool | `true` | Mermaid diagram generation |
| `tools.nano_banana_pro` | bool | `true` | AI image generation (Google Gemini) |
| `tools.playwright` | bool | `true` | Browser screenshot capture |
| `tools.ray_so` | bool | `true` | Code screenshot generation |

```yaml
media_generation:
  enabled: true
  tools:
    mermaid: true
    nano_banana_pro: true
    playwright: true
    ray_so: true
```

!!! note
    Tool availability is set here. Content guidance for *how* to use each tool is in [content-config.yaml](content-config.md).

---

## channels

Messaging channels for notifications and bot interaction. Keys: `telegram`, `slack`, `web`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable this channel |
| `allowed_chat_ids` | list | `[]` | Authorized chat IDs (Telegram/Slack) |

The `web` channel is enabled by default.

```yaml
channels:
  web:
    enabled: true
  telegram:
    enabled: true
    allowed_chat_ids: ["123456789"]
```

---

## consolidation

Batches rapid-fire commits into consolidated evaluations.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable consolidation processing |
| `mode` | string | `"notify_only"` | `"notify_only"` or `"re_evaluate"` |
| `batch_size` | int | `20` | Max decisions per consolidation batch |
| `auto_consolidate_drafts` | bool | `true` | Auto-consolidate draft decisions |
| `consolidate_approved` | bool | `false` | Include approved drafts in consolidation |
| `time_window_hours` | float | `4.0` | Time window for grouping |
| `time_window_max_drafts` | int | `3` | Max drafts per time window |

---

## journey_capture

Development Journey capture via Claude Code hooks.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable journey capture |
| `model` | string | — | Override model for capture. `null` = use `models.evaluator` |

---

## notification_level

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `notification_level` | string | `"all_decisions"` | `"all_decisions"` or `"drafts_only"` |

---

## Environment variables (.env)

Stored in `~/.social-hook/.env`. Real environment variables override file values.

| Variable | Required for | Description |
|----------|-------------|-------------|
| `ANTHROPIC_API_KEY` | `anthropic/` models | Claude API key |
| `OPENAI_API_KEY` | `openai/` models | OpenAI API key |
| `OPENROUTER_API_KEY` | `openrouter/` models | OpenRouter API key |
| `OLLAMA_BASE_URL` | `ollama/` models | Ollama server URL |
| `X_API_KEY` | X platform | X/Twitter API key |
| `X_API_SECRET` | X platform | X/Twitter API secret |
| `X_ACCESS_TOKEN` | X platform | X/Twitter access token |
| `X_ACCESS_TOKEN_SECRET` | X platform | X/Twitter access token secret |
| `LINKEDIN_CLIENT_ID` | LinkedIn | OAuth client ID |
| `LINKEDIN_CLIENT_SECRET` | LinkedIn | OAuth client secret |
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn | Access token |
| `TELEGRAM_BOT_TOKEN` | Telegram channel | Bot token |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Telegram channel | Comma-separated chat IDs |
| `GEMINI_API_KEY` | nano_banana_pro media | Google Gemini API key |
