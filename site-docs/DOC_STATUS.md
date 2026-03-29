<!-- last_run_commit: 3c8d6cfa3b324968ffb3745b11362cc6f498e9c8 -->
<!-- last_run_date: 2026-03-28 -->

# Documentation Status

Tracks coverage of external docs against the codebase. Used by the docs maintenance loop to prioritize work.

## CLI Docstrings (source of truth for auto-generated CLI reference)

| Command | Coverage | Notes |
|---------|----------|-------|
| `quickstart` | ok | Enriched: explains full onboarding flow |
| `consolidation-tick` | ok | Enriched: explains hold processing, modes, cron usage |
| `scheduler-tick` | ok | Enriched: explains posting, deferred promotion, cron |
| `discover` | ok | Enriched: explains two-pass LLM analysis |
| `setup` | partial | `--only` component values still unexplained |
| `test` | ok | Enriched: explains dry-run, --output/--compare |
| `trigger` | ok | Enriched: explains full pipeline, contrasts with test |
| `init` | ok | |
| `events` | ok | Has examples |
| `help` | ok | Has examples |
| `rate-limits` | ok | Has examples |
| `version` | ok | |
| `web` | ok | Enriched: explains dashboard capabilities |
| `account *` | ok | Group help enriched; subcommand docstrings already good |
| `brief *` | ok | Group help enriched; subcommand docstrings already good |
| `content *` | ok | Group help enriched; subcommand docstrings already good |
| `credentials *` | ok | Group help enriched; subcommand docstrings already good |
| `cycles *` | ok | Group help enriched; subcommand docstrings already good |
| `strategy *` | ok | Group help enriched; subcommand docstrings already good |
| `system *` | ok | Group help enriched; subcommand docstrings already good |
| `target *` | ok | Group help enriched; subcommand docstrings already good |
| `topics *` | ok | Group help enriched; subcommand docstrings already good |
| `draft approve` | ok | Enriched: explains scheduler interaction |
| `draft cancel` | ok | Enriched: explains queue removal |
| `draft retry` | ok | Enriched: explains re-queuing |
| `draft quick-approve` | ok | Enriched: explains combined approve + optimal scheduling |
| `draft schedule` | ok | Enriched: explains auto-scheduling vs explicit --time |
| `draft edit` | ok | Has example |
| `draft list` | ok | Has examples |
| `draft media-edit` | ok | Has example |
| `draft media-regen` | ok | |
| `draft media-remove` | ok | |
| `draft post-now` | ok | |
| `draft promote` | ok | Has example |
| `draft redraft` | ok | Has example |
| `draft reject` | ok | Has example |
| `draft reopen` | ok | |
| `draft show` | ok | |
| `draft unapprove` | ok | |
| `draft unschedule` | ok | |

## Conceptual Docs (site-docs/concepts/)

| Page | Status | Notes |
|------|--------|-------|
| pipeline.md | stale | Needs update for targets/routing/topics — major pipeline changes |
| narrative-arcs.md | stale | Arcs now tied to strategies — needs update |
| voice-memory.md | complete | |
| media-generation.md | complete | |
| targets.md | missing | New core concept — waiting_approval |
| topics.md | missing | New content source system — waiting_approval |
| routing.md | missing | New target routing system — waiting_approval |
| web-dashboard.md | missing | No page exists — waiting_approval |
| scheduling.md | missing | Covered briefly in config.md — waiting_approval |

## Configuration Docs (site-docs/configuration/)

| Page | Status | Notes |
|------|--------|-------|
| config.md | updated | OAuth 2.0 env vars fixed; needs targets config section |
| content-config.md | complete | |
| social-context.md | complete | |

## Getting Started (site-docs/getting-started/)

| Page | Status | Notes |
|------|--------|-------|
| installation.md | stale | May reference preview platform — needs targets update |
| quickstart.md | stale | May reference preview platform — needs targets update |

## Recurring Checks

| Check | Last passed | Notes |
|-------|-------------|-------|

## Backlog (waiting_approval)

- [ ] Targets concept page — how accounts, targets, and strategies work
- [ ] Topics concept page — content sources, topic queue, suggestions
- [ ] Routing concept page — how drafts get routed to targets
- [ ] Web dashboard usage guide (#19)
- [ ] Workflow tutorials (#20)
- [ ] examples/ directory (#22)
- [ ] Scheduling deep-dive (how optimal times are calculated, posting windows, rate limits)
- [ ] Agent-first CLI equivalents — interactive commands like `setup` need non-interactive agent equivalents, then documented
- [x] ~~Enrich docstrings for 9 new CLI command groups~~ (done — group help enriched, subcommands already well-documented)
- [ ] Testing guide — unit tests, E2E test suite, snapshots, VCR cassettes, verification scripts (source: docs/E2E_TESTING.md, docs/CLAUDE.md E2E section)
- [ ] E2E test reference — sections, scenarios, three-dimension protocol, --pause mode, harness helpers (source: docs/E2E_TESTING.md, scripts/e2e/)
