# Contributing to Social Hook

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Development Setup

**Prerequisites:** Python 3.10+ and Node.js 18.17+ (for the web dashboard).

```bash
# Clone and install
git clone https://github.com/nj-io/social-hook.git
cd social-hook
pip install -e ".[dev]"

# Install pre-commit hooks (lint, format, and commit message validation)
pre-commit install

# Install web dashboard dependencies
social-hook web --install
```

Optional extras:

```bash
pip install -e ".[dev,media]"          # + Playwright for media generation
pip install -e ".[dev,multi-provider]" # + OpenAI-compatible providers
pip install -e ".[dev,slack]"          # + Slack messaging adapter
```

## Running Checks

All three CI checks must pass before a PR can merge:

```bash
# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# Type check
mypy src/social_hook/

# Tests
pytest tests/ -q

# Skip slow performance tests
pytest tests/ -q -m 'not perf'
```

Pre-commit hooks run `ruff --fix`, `ruff-format`, TypeScript checking (`tsc --noEmit` on the web frontend), and conventional commit validation automatically on each commit.

## Commits and Releases

This project uses [Conventional Commits](https://www.conventionalcommits.org/) — **this is not optional**. Commit messages directly drive automated releases via [Release Please](https://github.com/googleapis/release-please), which reads commit history on `main` to determine version bumps, generate the changelog, and publish to PyPI.

**How your commits become releases:**

| Commit type | Effect | Changelog section |
|---|---|---|
| `feat: ...` | Bumps **minor** version (0.5.0 → 0.6.0) | Features |
| `fix: ...` | Bumps **patch** version (0.5.0 → 0.5.1) | Bug Fixes |
| `perf: ...` | Bumps **patch** version | Performance |
| `docs: ...` | No version bump | Documentation |
| `BREAKING CHANGE:` in footer | Bumps **minor** version (pre-1.0) | Breaking Changes |
| `chore:`, `ci:`, `test:`, `refactor:`, `build:` | No version bump | Hidden from changelog |

The `commit-msg` pre-commit hook validates the format locally. If your commit message doesn't match, the commit will be rejected.

**Format:**

```
type: short description

Optional longer body explaining the change.

Optional footer, e.g.:
BREAKING CHANGE: description of what breaks
```

**Examples:**

```
feat: add Bluesky adapter
fix: prevent WAL corruption on snapshot restore
docs: update CLI reference
refactor: extract rate limit logic into shared module
feat: cross-post references with abstract adapter interface

BREAKING CHANGE: PostAdapter.post() now requires a context parameter
```

**Common mistakes:**
- `update: ...` — not a valid type. Use `feat:` for enhancements or `fix:` for corrections.
- `feat(scope): ...` — scopes are allowed but not required.
- Missing type prefix — the hook will reject the commit.

## Pull Requests

- Branch from `main` and target `main` with your PR.
- Keep commits focused — one logical change per commit.
- When a PR is squash-merged, the **PR title** becomes the commit message on `main`, so make sure the PR title follows conventional commit format (e.g., `feat: add Bluesky adapter`).
- CI runs lint, typecheck, and tests (Python 3.10, 3.11, 3.12) automatically.
- Fill out the PR template with a summary, type of change, and how you tested.

## Project Structure

```
src/social_hook/
├── cli/            # Typer CLI commands (14 subcommand modules)
├── adapters/
│   ├── platform/   # Social media posting (X/Twitter, LinkedIn)
│   └── media/      # Image generation (Playwright, Mermaid, Ray.so)
├── bot/            # Telegram bot daemon
├── config/         # Configuration loading (YAML, env, platform creds)
├── db/             # SQLite database, schema, migrations
├── llm/            # LLM provider abstraction and AI agents
├── messaging/      # Messaging adapters (Telegram, Slack, Web)
├── narrative/      # Narrative arcs, voice memories
├── prompts/        # LLM system prompts (markdown)
├── setup/          # Setup wizard and validation
├── web/            # FastAPI backend server
├── trigger.py      # Hook entry point — evaluates commits
├── drafting.py     # Draft generation orchestration
├── consolidation.py # Batch commit consolidation
└── scheduling.py   # Scheduled posting
web/                # Next.js frontend (React 19, Tailwind 4, TypeScript)
tests/              # pytest test suite
examples/           # Example config files
```

## Code Style

- **Line length:** 100 characters
- **Linter:** Ruff (rules: E, F, I, UP, B, SIM)
- **Formatter:** Ruff (Black-compatible)
- **Type checker:** mypy (target: Python 3.10)
- **Import sorting:** handled by Ruff's isort rule

## Reporting Issues

Please use the [GitHub issue templates](https://github.com/nj-io/social-hook/issues/new/choose) for bug reports and feature requests. For security vulnerabilities, see [SECURITY.md](SECURITY.md).
