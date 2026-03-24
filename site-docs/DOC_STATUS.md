<!-- last_run_commit: 21c6a1ffe50cdf762497b4b5c0b0879ddc1fdc56 -->
<!-- last_run_date: 2026-03-24 -->

# Documentation Status

Tracks coverage of external docs against the codebase. Used by the docs maintenance loop to prioritize work.

## CLI Docstrings (source of truth for auto-generated CLI reference)

| Command | Coverage | Notes |
|---------|----------|-------|
| `quickstart` | poor | "Run the quickstart flow" — says nothing about what it does |
| `consolidation-tick` | poor | No context on when/why to run |
| `scheduler-tick` | poor | No context on when/why to run |
| `discover` | poor | "Two-pass project discovery" is jargon |
| `setup` | partial | `--only` component values unexplained |
| `test` | poor | No explanation of `--compare`/`--output` workflow |
| `trigger` | poor | Doesn't explain how it differs from `test` |
| `init` | ok | |
| `events` | ok | Has examples |
| `help` | ok | Has examples |
| `rate-limits` | ok | Has examples |
| `version` | ok | |
| `web` | poor | "Start the web dashboard" — no detail on what it offers |
| `draft approve` | poor | Just restates the command name |
| `draft cancel` | poor | Just restates the command name |
| `draft retry` | poor | Just restates the command name |
| `draft quick-approve` | poor | No explanation of what "optimal time" means |
| `draft schedule` | partial | Doesn't explain auto-scheduling behavior |
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
