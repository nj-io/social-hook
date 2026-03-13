# Installation

## Requirements

- Python 3.10+
- [Claude Code](https://claude.ai/code) (for the commit hook integration)
- Git

## Install from PyPI

```bash
pip install social-hook
```

## Install from source

```bash
git clone https://github.com/nj-io/social-hook.git
cd social-hook
pip install -e ".[dev]"
```

## Initial setup

After installation, run the interactive setup wizard:

```bash
social-hook setup
```

This will walk you through:

1. **API keys** — Configure your LLM provider (Anthropic, OpenAI, etc.)
2. **Platforms** — Enable X, LinkedIn, Telegram, and/or Slack
3. **Voice** — Set up your social-context.md with voice and style preferences
4. **Scheduling** — Configure posting windows and cadence

Or for a minimal start:

```bash
social-hook init
```

This creates the `~/.social-hook/` directory with default config templates.

## Register a project

```bash
cd /path/to/your/repo
social-hook project register
```

This installs a git post-commit hook and registers the project for evaluation.

## Verify

```bash
social-hook project list
social-hook test --repo . --last 3
```

The `test` command evaluates recent commits with real LLM calls but makes no DB writes — safe to run anytime.
