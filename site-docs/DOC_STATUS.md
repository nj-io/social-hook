<!-- maintenance-state
last_run_commit: ffba1371fb6e8e3fe20f061b29f7f8eba55ddc32
last_run_date: 2026-04-01
-->

# Documentation Status

Tracking file for the daily docs maintenance loop. Updated automatically.

## Coverage

| Section | Pages | Status | Notes |
|---------|-------|--------|-------|
| Getting Started | 2 | current | installation.md, quickstart.md |
| CLI Reference | 14 | current | Auto-generated via `scripts/generate_cli_docs.py` |
| Concepts | 5 | current | pipeline, narrative-arcs, voice-memory, media-generation |
| Configuration | 3 | current | config.yaml, content-config.yaml, social-context.md |

**Total:** 24 pages (excluding index files)

## Recurring Checks

These conditions are verified on each maintenance run. If a check fails, the
maintenance loop fixes it autonomously (existing content) or flags it for review
(new content).

| Check | Last passed |
|-------|-------------|
| CLI docs match current commands (`generate_cli_docs.py` produces no diff) | 2026-04-01 |
| All `@app.command()` functions in `src/social_hook/cli/` have docstrings | 2026-04-01 |
| Getting Started install instructions match `pyproject.toml` Python version | 2026-04-01 |
| Config defaults in `configuration/config.md` match `src/social_hook/config/yaml.py` | 2026-04-01 |
| Media tool names in docs match `MEDIA_ADAPTER_NAMES` in `src/social_hook/adapters/registry.py` | 2026-04-01 |
| Pipeline stages in `concepts/pipeline.md` match actual implementation | 2026-04-01 |
| `ruff check src/ tests/` passes | 2026-04-01 |
| All CLI commands in `quickstart.md` exist in the Typer app | 2026-04-01 |

## Backlog (waiting_approval)

Items identified as documentation gaps. Each needs approval before work begins.

- [ ] **Web dashboard guide** — README prominently features the web dashboard (14 settings sections, draft review, WebSocket notifications) but site-docs has no dedicated page
- [ ] **Telegram bot setup guide** — Messaging channel setup (bot start/stop/status) has no walkthrough
- [ ] **Agent/CI usage guide** — README "For Agents" section describes JSON output, non-interactive flags, exit codes; deserves a dedicated doc page for automation consumers
- [ ] **Plugin development guide** — Custom evaluators, drafters, media tools, platform adapters mentioned in README but no development docs
- [ ] **Content strategies guide** — Build in Public, Release Updates, Curated Technical, Custom strategies mentioned but not documented
- [ ] **Development Journey concept page** — CLI commands exist (`journey on/off/status`) but no concept explanation

## Log

| Date | Summary |
|------|---------|
| 2026-04-01 | Initial bootstrap — created DOC_STATUS.md, audited all 24 doc pages against codebase, all current. Identified 6 backlog items. |
