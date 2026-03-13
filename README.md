<p align="center">
  <img src="assets/social-preview.png" alt="Social Hook — The marketing engine built for devs" width="700">
</p>

<h1 align="center">Social Hook</h1>

<p align="center">The marketing engine built for devs.</p>

[![CI](https://github.com/nj-io/social-hook/actions/workflows/ci.yml/badge.svg)](https://github.com/nj-io/social-hook/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/nj-io/social-hook/graph/badge.svg)](https://codecov.io/gh/nj-io/social-hook)
[![PyPI](https://img.shields.io/pypi/v/social-hook)](https://pypi.org/project/social-hook/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Social Hook watches your development, drafts what matters, and publishes where your audience lives. It evaluates every commit, decides what's post-worthy, drafts platform-native content in your voice, and routes it for approval — or runs fully autonomous.

## Try It Out

```bash
pip install social-hook
social-hook quickstart /path/to/repo
```

Quickstart auto-detects your LLM provider, registers your project, imports commit history, analyzes your repo, and generates your first draft. To evaluate your last few commits through the full pipeline:

```bash
social-hook quickstart /path/to/repo --evaluate-last 3
```

To activate automatic triggers on every future commit:

```bash
social-hook project install-hook /path/to/repo
```

Then open the dashboard to see your drafts:

```bash
social-hook web
```

## For Humans

### Web Dashboard

The web dashboard is the primary interface for managing your content pipeline:

```bash
social-hook web
```

- Draft review — approve, reject, schedule, edit content and media
- Setup wizard and quick preview mode for onboarding
- Project management with commit history import
- Real-time notifications via WebSocket
- Media generation and preview
- Settings across 14 configuration sections
- Chat interface for bot commands

### CLI Setup Wizard

For terminal-based configuration:

```bash
social-hook setup                # Guided setup (strategy, identity, platforms, voice, audience, keys)
social-hook setup --advanced     # Include scheduling, media, rate limits
social-hook setup --only voice   # Configure a single section
```

### Messaging Channels

Social Hook separates notification channels (where you review drafts) from publishing platforms (where content gets posted). A platform-agnostic messaging adapter layer means channels are pluggable:

- **Web** — built-in. Notifications appear in the dashboard via WebSocket. Always available.
- **Telegram** — review and approve drafts from your phone. `social-hook bot start`

The adapter abstraction (`MessagingAdapter`) makes adding new channels (Slack, Discord, etc.) straightforward — each adapter handles send, edit, and callback independently.

## For Agents

Social Hook is agent-first. Every capability is accessible programmatically:

```bash
social-hook help --json                    # Full command tree as structured JSON
social-hook help draft approve --json      # Drill into any subcommand
social-hook quickstart /path/to/repo --json  # Structured output from quickstart
```

- Every CLI command has a corresponding web API endpoint (and vice versa)
- All commands work non-interactively with `--json` output and `--yes`/`--force` flags
- Exit codes: 0 = success, 1 = user error, 2 = system error

## How It Works

1. **Detect** — A git post-commit hook fires on every commit (installed per-project, works with any editor or agent)
2. **Evaluate** — An AI evaluator decides if the commit is post-worthy, assigns narrative arcs and episode types
3. **Draft** — Platform-native content is drafted in your voice, with per-platform identity and optional media
4. **Publish** — Drafts are scheduled, approved, or posted autonomously via platform adapters

## Features

- **Narrative Arcs** — groups commits into storylines so posts tell a coherent story over time
- **Media Generation** — diagrams, code screenshots, diff images — generated and attached automatically
- **Smart Scheduling** — rate limits, optimal timing, posting cadence
- **Multi-Platform** — X, LinkedIn, Bluesky, Mastodon, custom platforms with per-platform identity
- **Content Strategies** — bundled templates (Build in Public, Release Updates, Curated Technical, Custom)
- **Brand Discovery** — AI analyzes your repo to understand what you're building and generate context
- **Plugin System** — custom evaluators, drafters, media tools, platform adapters
- **Decision Rewind** — undo a pipeline decision and all its downstream artifacts
- **Batch Evaluate** — evaluate multiple commits holistically in one pass

## Free for Claude Code Users

If you have a Claude Code subscription, set your LLM provider to `claude-cli/sonnet` — zero additional API cost. Social Hook uses the Claude CLI as a backend, so your existing subscription covers all LLM calls.

## Multi-Provider LLM

Social Hook supports multiple LLM providers via a `provider/model-id` format:

- `anthropic/claude-sonnet-4-5` — Anthropic API (default)
- `claude-cli/sonnet` — Claude Code subprocess (free for subscribers)
- `openrouter/anthropic/claude-sonnet-4.5` — OpenRouter
- `ollama/llama3.3` — Local Ollama

## Documentation

Full documentation: [nj-io.github.io/social-hook/docs](https://nj-io.github.io/social-hook/docs/)

## Configuration

Social Hook uses a two-level config system:

- **Global config** (`~/.social-hook/config.yaml`) — API keys, platform credentials, LLM provider settings
- **Project config** (`.social-hook/` in your repo) — `social-context.md` (project voice/context), `content-config.yaml` (content rules)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, running checks, and PR guidelines.

## Versioning

Social Hook uses [Semantic Versioning](https://semver.org/). Releases are automated via [Release Please](https://github.com/googleapis/release-please) — conventional commits on `main` trigger version bumps, changelog generation, and PyPI publishing.

## License

[MIT](LICENSE)
