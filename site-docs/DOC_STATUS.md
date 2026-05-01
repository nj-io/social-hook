<!-- last_run_commit: 615a871d519a1f393af7d56c215e2d9e77d3225e -->
<!-- last_run_date: 2026-05-01 -->

# Documentation Status

Tracks coverage of external docs against the codebase. Used by the docs maintenance loop to prioritize work.

## CLI Docstrings (source of truth for auto-generated CLI reference)

| Command | Coverage | Notes |
|---------|----------|-------|
| `quickstart` | ok | Enriched: explains full onboarding flow |
| `consolidation-tick` | ok | Enriched: explains hold processing, modes, cron usage |
| `scheduler-tick` | ok | Enriched: explains posting, deferred promotion, cron |
| `discover` | ok | Enriched: explains two-pass LLM analysis |
| `setup` | ok | `--only` help text lists all valid component values |
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
| `strategy *` | ok | `show` enriched with displayed fields |
| `logs *` | ok | Replaced `system *`; query, tail, clear, health subcommands |
| `target *` | ok | `enable` enriched with re-enable behavior |
| `topics *` | ok | Group help enriched; subcommand docstrings already good |
| `decision *` | ok | `list` and `delete` enriched with decision context |
| `inspect *` | ok | `log`, `pending`, `usage`, `platforms` all enriched with detail and examples |
| `manual *` | ok | `draft`, `consolidate`, `post` enriched with LLM context and examples |
| `draft approve` | ok | Enriched: explains scheduler interaction |
| `draft cancel` | ok | Enriched: explains queue removal |
| `draft retry` | ok | Enriched: explains re-queuing |
| `draft quick-approve` | ok | Enriched: explains combined approve + optimal scheduling |
| `draft schedule` | ok | Enriched: explains auto-scheduling vs explicit --time |
| `draft edit` | ok | Enriched: change history, thread re-split |
| `draft list` | ok | Has examples |
| `draft media-edit` | ok | Enriched: media spec structure explanation |
| `draft media-regen` | ok | Enriched: media spec workflow |
| `draft media-remove` | ok | |
| `draft post-now` | ok | |
| `draft promote` | ok | Has example |
| `draft redraft` | ok | Enriched: Expert agent, LLM op, change history |
| `draft reject` | ok | Enriched: cascading re-draft, voice memory |
| `draft reopen` | ok | Enriched: intro restriction, resulting status |
| `draft show` | ok | |
| `draft unapprove` | ok | Enriched: resulting status, when to use |
| `draft connect` | ok | New: links preview draft to an account |
| `draft unschedule` | ok | Enriched: resulting status, when to use |
| `advisory *` | ok | New group from content vehicles: list, create, complete, dismiss |
| `arc *` | ok | Group help enriched; list, create, complete, abandon |
| `bot *` | ok | start, stop, status |
| `config *` | ok | show, get, set |
| `journey *` | ok | Group help enriched; on, off, status |
| `media *` | ok | gc subcommand |
| `memory *` | ok | list, add, delete, clear |
| `project *` | ok | Group help enriched; register, unregister, list, evaluate-recent, intro, prompt-docs subgroups |
| `snapshot *` | ok | New group: save, restore, reset, list, delete |

## Conceptual Docs (site-docs/concepts/)

| Page | Status | Notes |
|------|--------|-------|
| pipeline.md | stale | Two-stage eval accurate; missing content vehicles (single/thread/article), advisory flow (incl. bot schedule→advisory routing from #78), and content create/suggest paths |
| narrative-arcs.md | complete | Updated: strategy-scoped arcs, `episode_tags` (was `episode_type`) |
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
| CLI docs are fresh (`generate_cli_docs.py` output matches committed) | 2026-05-01 | |
| `mkdocs.yml` nav entries match files in `site-docs/cli/` | 2026-05-01 | |
| OAuth env vars in config.md use OAuth 2.0 names (`X_CLIENT_ID`, not `CONSUMER_KEY`) | 2026-05-01 | |
| `ruff check src/ tests/` passes | 2026-05-01 | |
| `mypy src/social_hook/` has no new errors (only pre-existing library stub issues) | 2026-05-01 | 28 errors, all `import-untyped` or `no-any-return` pre-existing |
| All CLI commands with poor/partial docstrings have been enriched | 2026-05-01 | |
| `pipeline.md` accurately describes the two-stage evaluation flow and targets path | 2026-05-01 | |
| `narrative-arcs.md` uses `episode_tags` (not `episode_type`) and documents strategy-scoped arcs | 2026-05-01 | |
| All interactive CLI commands (e.g., `credentials add`) have documented non-interactive equivalents for agent/CI use | 2026-05-01 | `credentials add --set`, all destructive commands have `--yes`; `setup` wizard → write config.yaml directly |
| All CLI command groups have enriched group-level help text (not just terse labels) | 2026-05-01 | All 24 groups have descriptive help |

## Backlog (waiting_approval)

- [ ] Targets concept page — how accounts, targets, and strategies work
- [ ] Topics concept page — content sources, topic queue, suggestions
- [ ] Routing concept page — how drafts get routed to targets
- [ ] Web dashboard usage guide (#19)
- [ ] Workflow tutorials (#20)
- [ ] examples/ directory (#22)
- [ ] Scheduling deep-dive (how optimal times are calculated, posting windows, rate limits)
- [x] ~~Agent-first CLI equivalents~~ (done — `credentials add --set`, all destructive commands have `--yes`, `setup` bypass via direct config.yaml)
- [x] ~~Enrich docstrings for partial/poor CLI commands~~ (done — 16 commands enriched across inspect, decision, manual, draft, strategy, target)
- [ ] config.md expansion — add sections for rate_limits, identities, content_strategies, platform_credentials, accounts, targets, platform_settings, max_targets, logging/LogBus
- [ ] pipeline.md update — add content vehicles (single/thread/article), advisory flow for non-auto-postable vehicles, content create/suggest paths
- [x] ~~pipeline.md rewrite~~ (done — two-stage evaluation, commit analyzer, batch evaluation, interval gating, per-strategy decisions, target routing)
- [ ] Testing guide — unit tests, E2E test suite, snapshots, VCR cassettes, verification scripts (source: docs/E2E_TESTING.md, docs/CLAUDE.md E2E section)
- [ ] E2E test reference — sections, scenarios, three-dimension protocol, --pause mode, harness helpers (source: docs/E2E_TESTING.md, scripts/e2e/)
