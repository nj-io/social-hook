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

## Quickstart

The fastest way to get going — registers your project, discovers its structure, and generates your first draft in one command:

```bash
cd /path/to/your/repo
social-hook quickstart
```

This will:

1. Prompt for your Anthropic API key (if not already configured)
2. Register the repo as a project
3. Install the git post-commit hook
4. Run project discovery (AI reads your codebase to understand what it does)
5. Generate an introductory draft

Pass `--evaluate-last 3` to also evaluate your 3 most recent commits for additional drafts.

## Guided setup

For more control over configuration, use the setup wizard:

```bash
social-hook setup
```

This walks you through:

1. **API keys** — Configure your LLM provider (Anthropic, OpenAI, etc.)
2. **Platforms** — Enable X, LinkedIn, Telegram, and/or Slack
3. **Voice** — Set up your social-context.md with voice and style preferences
4. **Scheduling** — Configure posting windows and cadence

## Verify

```bash
social-hook project list
social-hook test --repo . --last 3
```

The `test` command evaluates recent commits with real LLM calls but makes no DB writes — safe to run anytime.
