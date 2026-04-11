<!-- last_run_commit: 7aeb10f562605b582bfb105f6b95cd812c3494d8 -->
<!-- last_run_date: 2026-04-11 -->

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
| `arc *` | ok | Group help enriched; subcommand docstrings adequate |
| `bot *` | ok | Group help adequate |
| `config *` | ok | Subcommand docstrings adequate (show, get, set) |
| `journey *` | ok | Group help adequate (on, off, status) |
| `media *` | ok | Group help enriched; `gc` has examples |
| `memory *` | ok | Group help enriched; subcommand docstrings adequate |
| `project *` | ok | Group help enriched; subcommand docstrings with examples |
| `snapshot *` | ok | Group help enriched; subcommand docstrings with examples |

## Conceptual Docs (site-docs/concepts/)

| Page | Status | Notes |
|------|--------|-------|
| pipeline.md | complete | Rewritten: two-stage eval (analyzer+evaluator), batch evaluation, interval gating, per-strategy decisions, target routing, evaluation cycles, preview mode |
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
| content-config.md | complete | Added `max_discovery_tokens`, `max_file_size` to context table (2026-04-09) |
| social-context.md | complete | |

## Getting Started (site-docs/getting-started/)

| Page | Status | Notes |
|------|--------|-------|
| installation.md | complete | Fixed: quickstart steps now match code (2026-04-09) |
| quickstart.md | complete | Fixed: quickstart steps now match code (2026-04-09) |

## Recurring Checks

| Check | Last passed | Notes |
|-------|-------------|-------|
| CLI docs are fresh (`generate_cli_docs.py` output matches committed) | 2026-04-11 | Regenerated after subcommand docstring enrichment (8 files) |
| `mkdocs.yml` nav entries match files in `site-docs/cli/` | 2026-04-11 | 23 nav entries match 23 generated files |
| OAuth env vars in config.md use OAuth 2.0 names (`X_CLIENT_ID`, not `CONSUMER_KEY`) | 2026-04-11 | |
| `ruff check src/ tests/` passes | 2026-04-11 | |
| `mypy src/social_hook/` has no new errors (only pre-existing library stub issues) | 2026-04-11 | 28 errors, all `import-untyped` or `no-any-return` pre-existing |
| All CLI commands with poor/partial docstrings have been enriched | 2026-04-11 | 25 subcommands enriched across arc, journey, memory, project, config, media, events, rate-limits |
| `pipeline.md` accurately describes the two-stage evaluation flow and targets path | 2026-04-11 | Fixed preview mode to include OAuth credential check |
| `narrative-arcs.md` uses `episode_tags` (not `episode_type`) and documents strategy-scoped arcs | 2026-04-11 | |
| All interactive CLI commands (e.g., `credentials add`) have documented non-interactive equivalents for agent/CI use | 2026-04-11 | `credentials add --set`, all destructive commands have `--yes`; `setup` wizard → write config.yaml directly |
| Quickstart docs match quickstart code flow | 2026-04-11 | Fixed: `trigger` command now shows required `--commit` and `--repo` args |
| Config docs cover all ContextConfig fields | 2026-04-11 | Added max_discovery_tokens, max_file_size; rate_limits/identities/content_strategies still in backlog |

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
- [x] ~~pipeline.md rewrite~~ (done — two-stage evaluation, commit analyzer, batch evaluation, interval gating, per-strategy decisions, target routing)
- [ ] Testing guide — unit tests, E2E test suite, snapshots, VCR cassettes, verification scripts (source: docs/E2E_TESTING.md, docs/CLAUDE.md E2E section)
- [ ] E2E test reference — sections, scenarios, three-dimension protocol, --pause mode, harness helpers (source: docs/E2E_TESTING.md, scripts/e2e/)

## Changelog

### 2026-04-11

- Enriched 25 CLI subcommand docstrings across 8 files: arc (5), journey (3), memory (3), project (8), config (2), media (1), events (1), rate-limits (1) — terse one-liners replaced with explanatory prose and examples
- Fixed: quickstart.md `social-hook trigger` shown without args — command requires `--commit <hash> --repo <path>`
- Fixed: pipeline.md preview mode only mentioned "no connected targets" — now also documents the OAuth credential check
- Regenerated CLI docs (8 files updated)
- All 11 recurring checks pass. Ruff clean, mypy 28 pre-existing errors
- No new backlog approvals found in PR #71 or PR #75 comments

### 2026-04-10

- Enriched 8 CLI group help texts in `__init__.py` (arc, decision, inspect, manual, media, memory, project, snapshot) — terse one-liners replaced with descriptive help
- Added 8 previously untracked CLI groups to coverage table (arc, bot, config, journey, media, memory, project, snapshot)
- Fixed: quickstart.md section 6 claimed "git hook triggers automatically" unconditionally — now explains both hook and manual `trigger` paths
- Regenerated CLI docs (9 files updated)
- Fixed stale `last_run_commit` (previous value referenced non-existent SHA)
- All 11 recurring checks pass. Ruff clean, mypy 28 pre-existing errors
- No new backlog approvals found in PR #75 or PR #71 comments

### 2026-04-09

- Fixed: quickstart docs claimed "install git post-commit hook" but quickstart code imports commits instead (installation.md, quickstart.md)
- Fixed: added `max_discovery_tokens` (default 60000) and `max_file_size` (default 256000) to content-config.md context table
- CLI docs regenerated — no changes needed (already current)
- Ruff: clean. Mypy: 22 pre-existing errors (down from 28 on 2026-03-31)
- Added 2 new recurring checks: quickstart flow accuracy, ContextConfig field coverage

### 2026-03-31

- Previous maintenance run (see git history for details)
