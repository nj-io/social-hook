<!-- last_run_commit: 6688d91b2ee4da630f9dec8dae1d776ae89b5a4c -->
<!-- last_run_date: 2026-03-30 -->

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
| `strategy *` | partial | `show` lacks field descriptions |
| `logs *` | ok | Replaced `system *`; query, tail, clear, health subcommands |
| `target *` | partial | `enable` lacks explanation of re-enable behavior |
| `topics *` | ok | Group help enriched; subcommand docstrings already good |
| `decision *` | partial | `list` and `delete` lack context on what decisions are |
| `inspect *` | poor | `log` and `pending` just restate command names; `usage` and `platforms` lack detail |
| `manual *` | partial | `draft`, `consolidate`, `post` — single-line, no examples, no LLM context |
| `draft approve` | ok | Enriched: explains scheduler interaction |
| `draft cancel` | ok | Enriched: explains queue removal |
| `draft retry` | ok | Enriched: explains re-queuing |
| `draft quick-approve` | ok | Enriched: explains combined approve + optimal scheduling |
| `draft schedule` | ok | Enriched: explains auto-scheduling vs explicit --time |
| `draft edit` | partial | Missing: change history, thread re-sync |
| `draft list` | ok | Has examples |
| `draft media-edit` | partial | Missing: what a media spec is, expected JSON structure |
| `draft media-regen` | partial | Missing: what media spec is |
| `draft media-remove` | ok | |
| `draft post-now` | ok | |
| `draft promote` | ok | Has example |
| `draft redraft` | partial | Missing: what Expert agent is, that this is an LLM op |
| `draft reject` | partial | Missing: cascading re-draft for intros, voice memory storage |
| `draft reopen` | partial | Missing: intro draft restriction, resulting status |
| `draft show` | ok | |
| `draft unapprove` | partial | Missing: resulting status, when to use |
| `draft connect` | ok | New: links preview draft to an account |
| `draft unschedule` | partial | Missing: resulting status, when to use |

## Conceptual Docs (site-docs/concepts/)

| Page | Status | Notes |
|------|--------|-------|
| pipeline.md | stale | Preview mode fixed; still missing: two-stage evaluation (analyzer+evaluator), batch evaluation, interval gating, per-strategy decisions, topic queues, targets vs legacy paths |
| narrative-arcs.md | partial | Arcs now strategy-scoped (`strategy` field); `episode_type` → `episode_tags`; core concepts (debt, lifecycle) still accurate |
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
| config.md | stale | OAuth 2.0 env vars correct; missing sections: rate_limits, identities, content_strategies, platform_credentials, accounts, targets, platform_settings, max_targets, logging/LogBus |
| content-config.md | complete | |
| social-context.md | complete | |

## Getting Started (site-docs/getting-started/)

| Page | Status | Notes |
|------|--------|-------|
| installation.md | complete | Accurate for current quickstart flow; targets workflow addendum in backlog |
| quickstart.md | complete | Preview draft → promote flow still valid; targets onboarding in backlog |

## Recurring Checks

| Check | Last passed | Notes |
|-------|-------------|-------|
| CLI docs are fresh (`generate_cli_docs.py` output matches committed) | 2026-03-30 | |
| `mkdocs.yml` nav entries match files in `site-docs/cli/` | 2026-03-30 | Fixed: `system` → `logs` |
| OAuth env vars in config.md use OAuth 2.0 names (`X_CLIENT_ID`, not `CONSUMER_KEY`) | 2026-03-30 | |
| `ruff check src/ tests/` passes | 2026-03-30 | |
| `mypy src/social_hook/` has no new errors (only pre-existing library stub issues) | 2026-03-30 | 28 errors, all `import-untyped` or pre-existing |

## Backlog (waiting_approval)

- [ ] Targets concept page — how accounts, targets, and strategies work
- [ ] Topics concept page — content sources, topic queue, suggestions
- [ ] Routing concept page — how drafts get routed to targets
- [ ] Web dashboard usage guide (#19)
- [ ] Workflow tutorials (#20)
- [ ] examples/ directory (#22)
- [ ] Scheduling deep-dive (how optimal times are calculated, posting windows, rate limits)
- [ ] Agent-first CLI equivalents — interactive commands like `setup` need non-interactive agent equivalents, then documented
- [ ] Enrich docstrings for partial/poor CLI commands — inspect (2 poor, 2 partial), manual (3 partial), draft (7 partial), decision (2 partial), strategy (1 partial), target (1 partial)
- [ ] config.md expansion — add sections for rate_limits, identities, content_strategies, platform_credentials, accounts, targets, platform_settings, max_targets, logging/LogBus
- [ ] pipeline.md rewrite — two-stage evaluation, commit analyzer, batch evaluation, interval gating, per-strategy decisions, targets vs legacy paths
- [ ] Testing guide — unit tests, E2E test suite, snapshots, VCR cassettes, verification scripts (source: docs/E2E_TESTING.md, docs/CLAUDE.md E2E section)
- [ ] E2E test reference — sections, scenarios, three-dimension protocol, --pause mode, harness helpers (source: docs/E2E_TESTING.md, scripts/e2e/)
