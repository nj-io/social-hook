# config.yaml

The main infrastructure configuration file. Located at `~/.social-hook/config.yaml`.

Controls which platforms are enabled, LLM model selection, API keys, scheduling windows, and posting cadence.

## Location

Social Hook looks for config in this order:

1. Path passed via `--config` / `-c` flag
2. `SOCIAL_HOOK_CONFIG` environment variable
3. `~/.social-hook/config.yaml` (default)

## Interactive setup

The easiest way to configure:

```bash
social-hook setup
```

Or configure a specific section:

```bash
social-hook setup --only apikeys
social-hook setup --only platforms
social-hook setup --only scheduling
```

## View current config

```bash
social-hook config show
social-hook config get models.evaluator
```

## Key sections

| Section | Purpose |
|---------|---------|
| `models` | LLM provider and model for evaluator, drafter, expert |
| `api_keys` | API keys for LLM providers and platforms |
| `platforms` | Enable/disable X, LinkedIn, Telegram, Slack |
| `scheduling` | Posting windows, timezone, cadence limits |
| `media_generation` | Enable/disable media tools (Mermaid, ray.so, etc.) |
| `web` | Web dashboard port and host settings |
| `bot` | Telegram/Slack bot configuration |

!!! note
    For content guidance (voice, strategy, media prompts), see [content-config.yaml](content-config.md) and [social-context.md](social-context.md).
