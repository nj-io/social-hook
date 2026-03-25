<!-- last_run_commit: f07f52124396725fc2b848897c3c1587c8f237c5 -->
<!-- last_run_date: 2026-03-25 -->

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
| pipeline.md | complete | 298 lines, thorough stage-by-stage walkthrough |
| narrative-arcs.md | complete | |
| voice-memory.md | complete | |
| media-generation.md | complete | |
| web-dashboard.md | missing | No page exists — waiting_approval |
| scheduling.md | missing | Covered briefly in config.md — waiting_approval |

## Configuration Docs (site-docs/configuration/)

| Page | Status | Notes |
|------|--------|-------|
| config.md | complete | Full field-by-field reference |
| content-config.md | complete | |
| social-context.md | complete | |

## Getting Started (site-docs/getting-started/)

| Page | Status | Notes |
|------|--------|-------|
| installation.md | complete | Leads with quickstart |
| quickstart.md | complete | Step-by-step guide |

## Backlog (waiting_approval)

- [ ] Web dashboard usage guide (#19)
- [ ] Workflow tutorials (#20)
- [ ] examples/ directory (#22)
- [ ] Scheduling deep-dive (how optimal times are calculated, posting windows, rate limits)
- [ ] Agent-first CLI equivalents — interactive commands like `setup` need non-interactive agent equivalents, then documented
- [ ] Update docs when targets branch merges (preview concept changing)
