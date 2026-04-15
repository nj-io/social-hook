# Coding Practices

> Implementation-level conventions for writing code in the social-hook codebase. For architecture, process, and tooling conventions, see [CLAUDE.md](CLAUDE.md).

## Changelog

| Date | Change |
|------|--------|
| 2026-04-09 | Added: Advisory approval flow — `check_auto_postable()` + `handle_advisory_approval()` in `vehicle.py`. All approval/scheduling paths (bot buttons, CLI, web) check before status change. `DraftStatus.ADVISORY` is terminal. Advisory page has Upcoming/Action Required grouping with countdown. |
| 2026-04-08 | Updated: Drafting Pipeline — unified `draft(intent)` entry point replaces `draft_for_platforms()`/`draft_for_targets()`, `DraftingIntent` builders in `drafting_intents.py`, vehicle resolution, `_finalize_draft()`. Content Source Resolution uses `intent_from_routed_targets()` + `DraftingIntent.content_source_context`. Added `file_reader.py` to Shared Utilities. |
| 2026-03-29 | Split: `models/__init__.py` into 7 submodules (enums, core, narrative, content, infra, context, _helpers). Direct imports only — no re-exports. Updated Dispatch Patterns and Pipeline Events references. |
| 2026-03-28 | Added: `enum_value()` rule to Boundary Parsing. trigger.py decomposed into 6 sibling modules (trigger_git, trigger_context, trigger_decisions, trigger_side_effects, trigger_batch, trigger_secondary). Updated Evaluation Pipeline section. |
| 2026-03-28 | Added: `oauth_pkce.py` and `dry_run.py` to Shared Utilities table. OAuth PKCE mechanics extracted to generic module. DryRunProxy extracted from llm/dry_run.py. |
| 2026-03-28 | Added: `migrations.py` to Shared Utilities table (SQL migration runner). |
| 2026-03-28 | Added: Pipeline Diagnostics subsection — check registry pattern, writing checks, rules. Added `diagnostics.py` to reusable components. |
| 2026-03-28 | Added: `registry.py` to Shared Utilities table. Added Adapter Registry reusability rules. Platform/media/messaging factories refactored from if/elif chains to registry dispatch. |
| 2026-03-26 | Added: Logging section (entry point init, module loggers, structured context, run correlation, error feed deprecation, reusability rules). Added `logging.py` and `error_feed.py` to Shared Utilities table. |
| 2026-03-24 | Added: Targets config access patterns, `check_unknown_keys` strict parameter for API endpoints. |
| 2026-03-24 | Added: Shared Utilities section, `terminal.py`. Added `<Note>` component to Web API Conventions. |
| 2026-03-21 | Created: defensive programming, migrated CLI/web/handler/reusability conventions from CLAUDE.md |

---

## Defensive Programming

### Boundary Parsing
Use utilities from `src/social_hook/parsing.py` at all system boundaries (DB columns, HTTP headers, user input, LLM output, config files):
- `safe_json_loads(text, context, default)` — never bare `json.loads` on untrusted data
- `safe_int(value, default, context)` — never bare `int()` on external strings
- `enum_value(x)` — extract `.value` from enums or return unchanged. Use instead of inline `_val()` helpers.
- `check_unknown_keys(data, known_keys, section)` — call in every config parser

### Error Handling
- Never `except Exception: pass` or `except Exception: return []`. If you catch broad exceptions, always log with context (`logger.warning(..., exc_info=True)`).
- Prefer specific exceptions. Use the taxonomy in `errors.py` (`ConfigError`, `MalformedResponseError`, `DatabaseError`, etc.).
- At system boundaries (HTTP endpoints, WebSocket handlers, background tasks), catch broad exceptions but log and surface them. Inside business logic, let exceptions propagate.

### LLM Output Validation
Structural errors (missing tool call, invalid schema) fail hard via `ToolExtractionError` / Pydantic `ValidationError` — the evaluation aborts. Semantic errors (invalid topic_id reference, wrong strategy scope) are handled gracefully: log a warning, strip the invalid field, continue processing. Never fail an entire evaluation because the LLM referenced a nonexistent ID.

### Dispatch Patterns
- Every if/elif dispatch chain must have an `else` branch that logs the unhandled case: `logger.warning("Unknown %s: %s", category, value)`.
- For status group checks, import constants from `models.enums` (`TERMINAL_STATUSES`, `PENDING_STATUSES`, `EDITABLE_STATUSES`). Never define inline status sets.

### DryRunContext
`DryRunContext` in `llm/dry_run.py` whitelists read operations (`get_*`). Everything else is treated as a write and skipped in dry-run. When adding new `db.operations` functions, no DryRunContext changes are needed — reads pass through automatically, writes are blocked automatically.

## CLI Design Conventions

Rules for every new CLI command:
- All commands must be usable non-interactively. Destructive operations may prompt
  for confirmation but must accept `--yes` or `--force` to skip. The `setup` wizard
  is the sole exception.
- Use structured output: the global `--json` flag is available via `ctx.obj["json"]`.
  Consistent exit codes: 0 = success, 1 = user error, 2 = system error.
- **Forgiving flag placement.** Every command supporting `--json` must declare it
  as a local option AND merge with the global flag, so both `social-hook --json draft list`
  and `social-hook draft list --json` work. Pattern:
  `json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)`
- Help text must include a concrete usage example (Typer `help=` parameter).
  The help text is the single source of truth — it feeds `--help` for humans,
  `social-hook help --json` for agents, and any future docs site.
- Project resolution pattern: `--project PATH` option defaulting to `os.getcwd()`,
  resolved via `os.path.realpath()` → `ops.get_project_by_path()`.
- Follow existing naming: subcommand groups use nouns (`arc`, `memory`, `project`,
  `draft`), actions use verbs (`create`, `list`, `approve`).
- **Every declared flag must be used** in the function body. No dead flags.
- **Docstrings must match the code.** If it creates drafts, makes LLM calls, or writes to the DB, say so.
- **`--project / -p` always means a filesystem path**, resolved via `_resolve_project()`. Use `--id` when accepting a project ID.
- **Document limits and implicit behaviors.** If there's a max (e.g., 3 active arcs) or omitting a flag triggers different behavior (e.g., auto-scheduling), state it in the help text.
- **`--dry-run` must never write to the DB.** Dry-run commands must be truly read-only.

### Self-Documenting CLI

The CLI is self-documenting — there are no separate reference docs to maintain.

- **Humans**: `social-hook help`, `social-hook help draft`, `social-hook help draft approve`
- **Agents**: `social-hook help --json` (full tree) or `social-hook help draft approve --json` (single command).
  JSON schema: `help` = first-line summary, `description` = full docstring with examples.
- **Docs sites**: build pipeline consumes `social-hook help --json` output

When adding a new command, writing good `help=` text in the Typer decorator is all
that's needed. No generated files, no scripts to run, no docs to update.

## Web API Conventions

**Session isolation:** Each browser tab gets a unique session ID (UUID in `sessionStorage`), sent via `X-Session-Id` header. Events in `web_events` are either broadcast (`session_id = NULL`, visible to all tabs) or scoped (`session_id = <uuid>`, visible only to the originating tab). When adding event-producing endpoints, choose broadcast vs scoped based on audience.

**All LLM calls use background tasks.** Never call an LLM synchronously from any web-facing path — they take 5-60s, exceeding the Next.js proxy timeout. This applies to:
- Direct REST endpoints (`POST /api/decisions/retrigger`, `POST /api/decisions/batch-evaluate`, etc.)
- Bot handler actions that flow through `/api/callback` and `/api/message` (Gatekeeper, Expert, media spec generation)

The universal contract: **any LLM call = background task + stage events.** The backend pattern:
1. Validate inputs and prepare state synchronously in the request handler
2. Call `_run_background_task(type, ref_id, project_id, fn)` — inserts a `running` row in `background_tasks`, launches `fn` in a daemon thread
3. Return `JSONResponse(status_code=202, content={"task_id": ..., "status": "processing"})`
4. Inside `fn`, emit stage events via `ops.emit_task_stage(conn, task_id, stage, label, project_id)` at each step
5. On server restart, `_cleanup_stale_tasks()` marks any `running` tasks as `failed` (threads don't survive restart)

**Async button pattern.** Buttons that trigger background tasks must use `<AsyncButton>` from `web/src/components/async-button.tsx`. This shows a spinner + elapsed time counter ("Evaluating... 12s"). Drive loading state via `isTaskRunning(refId)` from `useBackgroundTasks` — never use manual `useState` for loading, because the 202 response returns instantly and manual state clears before the task finishes. Pattern:
```tsx
const { trackTask, isRunning: isTaskRunning, getTask } = useBackgroundTasks(projectId, onTaskCompleted);
const isLoading = isTaskRunning(refId);
const task = getTask(refId);

<AsyncButton loading={isLoading} startTime={task?.created_at} loadingText="Processing" onClick={async () => {
  const res = await apiCall();
  trackTask(res.task_id, refId, "task_type");
}} disabled={isLoading}>
  Button Label
</AsyncButton>
```
Quick operations (< 2s: save, delete, toggle) do not need `AsyncButton` — simple `disabled:opacity-50` is sufficient.

**Top banner notifications.** Use `<TopBanner>` from `web/src/components/top-banner.tsx` for dismissable top-of-page notifications. Parent controls `visible`/`onDismiss`; optional `onDismissForever` adds an inline permanent dismiss link. See `SlowTaskBanner` for usage.

**Background task tracking (frontend).** Use `useBackgroundTasks(projectId, onTaskCompleted?)` from `web/src/lib/use-background-tasks.ts` to track 202 tasks. Call `trackTask(taskId, refId, type, { timeoutMs })` after the 202 response. The hook restores running tasks on page refresh via `/api/tasks?status=running`, listens for WebSocket `task` events, and fires `onTaskCompleted` when tasks finish. Handle both `completed` and `failed` in the callback. Default client-side timeout: 10 minutes (matching `_STALE_TASK_TIMEOUT_SECONDS`).

**Task stage tracking.** Background tasks can emit named stages via `ctx.db.emit_task_stage(task_id, stage, label, project_id)` (defined in `operations.py`). Route through `ctx.db` for DryRunContext safety. The frontend `useBackgroundTasks` hook picks up `"task"/"stage"` events and updates `task.current_stage`, `task.stage_label`, `task.stage_started_at` in-memory (no DB round-trip). Components read stage info from `getTask(refId)` to show per-stage progress. Any background flow can use this. Pipeline events and task stage events are independent systems — a flow may use either, both, or neither. Emit as explicit separate calls. Do not combine into a helper. Stage names are freeform strings (not an enum). Stage data is in-memory only — lost on page refresh; the task restores as "running" with generic "Processing" text. **Passing task_id to blocking functions:** `_run_background_task` generates `task_id` internally and calls `fn()` with no arguments. To access `task_id` inside the blocking closure, use a mutable holder: `holder = [None]`, capture in closure, assign after `_run_background_task` returns. See `_blocking_batch_evaluate` for the pattern.

**Timestamp format.** SQLite stores `datetime('now')` as UTC without timezone suffix. API responses must append `Z` to timestamps consumed by JavaScript `new Date()` to avoid local-timezone misinterpretation (7+ hour offsets in non-UTC browsers).

**Toast notifications.** Use `useToast().addToast()` from `web/src/lib/toast-context.tsx` for operation feedback. `PipelineToasts` (in `providers.tsx`) handles pipeline/draft/advisory events automatically; use `addToast()` directly for custom notifications.

**Failed task error toasts.** Every `onTaskCompleted` callback must handle `task.status === "failed"` with `addToast(..., { variant: "error", detail: task.error })`. `PipelineToasts` does NOT handle task events — error feedback is the component's responsibility. Never fire callbacks from inside a `setState` updater (React 18 concurrent mode can discard nested state updates).

**Destructive action confirmation.** Never use `window.confirm()` (browser native dialog). Use `<Modal>` from `web/src/components/ui/modal.tsx` with Cancel/Confirm buttons. Pattern: boolean state for visibility (`showConfirm`), loading state for the action (`clearing`), disable Cancel while loading, red Confirm button. See `error-feed.tsx` or `projects/[id]/page.tsx` delete confirmation for reference.

**Inline notes/callouts.** Use `<Note>` from `web/src/components/ui/note.tsx` for contextual messages in settings panels and wizards. Variants: `warning` (amber, default), `info` (blue), `success` (green), `error` (red). Supports children and optional `className`. Example: `<Note variant="info">Ensure callback URL is registered.</Note>`.

## Handler Abstraction

Bot handlers (`buttons.py`, `commands.py`) accept `(InboundMessage/CallbackEvent, MessagingAdapter)`, not raw Telegram dicts. The daemon (`daemon.py`) is the Telegram boundary — it converts raw Telegram dicts to abstract types via `TelegramAdapter.parse_message()`/`parse_callback()`. The FastAPI server (`web/server.py`) constructs the same abstract types from HTTP request bodies. Both use `MessagingAdapter` to send responses.

**LLM calls in bot handlers must use background tasks.** Bot handlers that call LLM agents (Gatekeeper, Expert, Drafter) run through `/api/callback` and `/api/message` on the web. Even though `asyncio.to_thread` moves the work off the event loop, the HTTP response still waits for completion — causing 5-60s blocking. Bot handlers should dispatch LLM work via `_run_background_task` and return immediately. Results arrive via SSE events (the existing WebSocket/gateway system).

## Shared Utilities

Shared utilities live as **top-level modules** in `src/social_hook/` — not in a `utils/` directory. This matches the existing pattern: `parsing.py`, `filesystem.py`, `errors.py`, `constants.py`.

| Module | Purpose | Used by |
|--------|---------|--------|
| `parsing.py` | Boundary parsing (`safe_json_loads`, `safe_int`, `check_unknown_keys`) | Config, DB, HTTP boundaries |
| `filesystem.py` | Paths, ID generation (`get_db_path`, `get_base_path`, `generate_id`) | CLI, scheduler, setup |
| `errors.py` | Exception taxonomy (`ConfigError`, `MalformedResponseError`, etc.) | Everywhere |
| `constants.py` | Project naming (`PROJECT_NAME`, `PROJECT_SLUG`) | CLI, setup |
| `terminal.py` | Interactive terminal (`getch`, `copy_to_clipboard`, `pause_with_url`) | CLI wizard, E2E tests |
| `logging.py` | Unified logging (`setup_logging`, `LogBus`, sinks, `JsonFormatter`) | All entry points |
| `error_feed.py` | System error feed (`ErrorFeed`, `ErrorSeverity`, DB persistence) | Logging DbSink, CLI, Web, Bot |
| `registry.py` | Generic adapter registry (`AdapterRegistry`, register/create/cache) | Platform, media, messaging factories |
| `migrations.py` | SQL migration runner (`apply_sql_migrations`, PRAGMA handling) | `db/schema.py` |
| `oauth_pkce.py` | OAuth 2.0 PKCE utilities (verifier, URL building, callback server) | `setup/oauth.py`, web OAuth endpoints |
| `dry_run.py` | Generic dry-run proxy (`DryRunProxy`, read-pass/write-skip) | `llm/dry_run.py` |
| `file_reader.py` | Token-budgeted file reading (`read_files_within_budget`, path traversal protection) | `drafting.py`, `llm/brief.py`, `llm/prompts.py` |

When adding a new shared utility, add it as a top-level module here — not inside a subsystem directory. If it's only used by one subsystem, it belongs in that subsystem's directory instead.

## Evaluation Pipeline

### Batch Evaluation Pattern

When building any path that evaluates multiple commits together (interval batching, scheduler drain, future plugin triggers), always use `evaluate_batch()`. Never build inline batch evaluation logic — this ensures all pipeline steps are included: stage 1 analysis, stage 2 evaluation, brief update, tag-to-topic matching, topic suggestions, arc activation, held decision absorption, queue actions, routing, drafting, and notifications.

```python
from social_hook.trigger import evaluate_batch  # canonical import (re-exported from trigger_batch.py)
evaluate_batch(ctx=ctx, deferred_commits=deferred, trigger_commit_hash=hash, context=context, evaluator_client=client)
```

The caller builds the `TriggerContext` (from `trigger_context.py`) and passes it in. `evaluate_batch` (in `trigger_batch.py`) handles combining diffs, running both stages, and calling `_run_targets_path`. Batch membership (batch_id) is set inside `_run_targets_path`: deferred decisions in Phase A (cycle creation), trigger decision in Phase E (decision creation). The canonical import path is `from social_hook.trigger import evaluate_batch` — do not import from `trigger_batch` directly in production code.

**Manual batch evaluation** is available via `POST /api/decisions/batch-evaluate` (web) and `social-hook decision batch-evaluate` (CLI). Both pre-mark decisions as `processing`, run `evaluate_batch()` in a background task, and restore original statuses on failure with TOCTOU guard.

### Drafting Pipeline

**Entry point:** All drafting flows through `draft(intent: DraftingIntent, ...) -> list[DraftResult]` in `drafting.py`. Callers construct a `DraftingIntent` via builder functions in `drafting_intents.py` — never build `DraftingIntent` inline. The four builders (`intent_from_routed_targets`, `intent_from_platforms`, `intent_from_decision`, `intent_from_merge`) handle platform resolution, content source resolution, and preview mode detection.

**Vehicle resolution:** `draft()` calls `resolve_vehicle()` before the LLM call. Three-tier fallback: operator choice > evaluator suggestion > drafter decides. The resolved vehicle is passed to `Drafter.create_draft(vehicle=resolved)`.

**Single-platform calls:** `Drafter.create_draft()` with `platform_config` (a `ResolvedPlatformConfig`) and `vehicle`. Tier info is always included — `account_tier or "free"` defaults to free tier, 280 char limit.

**Multi-platform (shared group):** `DraftingIntent` with multiple `PlatformSpec` entries. `Drafter.create_draft()` receives `platform_configs` list of `(platform_name, ResolvedPlatformConfig)` tuples, deduplicated by platform name. Returns `CreateDraftInput` with `variants: list[PlatformVariant]` — one per unique platform, each with vehicle-appropriate instructions. Per-platform intro/identity context goes in the user message (system prompt uses first platform). Targets sharing a platform name receive the same variant.

**Preview drafts:** Two cases per TARGETS_DESIGN.md:
- *Platform preview* (target with platform, no account): inherits tier from `config.platforms`, drafter receives real platform constraints
- *Generic preview* (strategy with no target): `platform_config.name == "preview"`, drafter receives explicit "no platform constraints" guidance

**Post-LLM pipeline:** `_finalize_draft()` handles per-platform scheduling, Draft construction, DB insertion, `materialize_vehicle_artifacts()` (creates `draft_parts` for threads), and event emission.

**Advisory approval flow:** Non-auto-postable vehicles (e.g., articles where `PostCapability.auto_postable=False`) bypass the scheduler entirely. Every approval/scheduling path must check `check_auto_postable(draft)` from `vehicle.py` before changing status. If not auto-postable, call `handle_advisory_approval(conn, draft, config, scheduled_time=...)` which creates an advisory item, sets `status="advisory"` (terminal), and emits events. Pass `scheduled_time` when available (quick-approve, schedule) for the advisory `due_date`; omit for immediate actions (post-now, plain approve). The scheduler's `_post_draft()` has a safety-net check for drafts that bypass the approval-time check. The advisory page groups pending items into "Upcoming" (future `due_date` with countdown) and "Action Required".

**Deleted:** `draft_for_platforms()`, `draft_for_targets()`, `_draft_for_resolved_platforms()`, `_draft_shared_group()`, `_resolve_and_filter_platforms()`, `_pick_lead_platform`, `_adapt_content_for_platform`, `_unthread_content`, `_needs_thread()`, `_parse_thread_tweets()`, `compat.py`.

### Content Source Resolution

The `content_sources.py` registry resolves `ContextSourceSpec` types (brief, commits, topic, topic_commits, operator_suggestion) into text context for the drafter. Resolution happens in `intent_from_routed_targets()` per-strategy, and the pre-resolved dict is stored in `DraftingIntent.content_source_context`, flowing through to `assemble_drafter_prompt()`. When `topic_id` is set but `context_source` is missing, `intent_from_routed_targets` auto-creates a spec with `types=["topic"]`. The drafter receives both the resolved content and previous topic posts (via `get_posts_by_topic_id`).

### Topic Status Lifecycle

Topic status transitions happen at **posting time**, not draft creation:
- `update_topic_hold(conn, topic_id, reason)` — sets status='holding' + hold_reason atomically
- `update_topic_posted(conn, topic_id, status)` — sets status (covered/partial), clears hold_reason, sets last_posted_at

Arc-linked topics get `partial` status; non-arc topics get `covered`. The `arc_id` is stored on the Draft during construction (from `strategy_decision.arc_id`) so the scheduler doesn't need a decision lookup at posting time.

### Pipeline Events

Emit `PipelineStage` constants (`models.enums`) at the **moment** each stage starts — never before gating. Use `ctx.db.emit_data_event` for DryRunContext safety. New stages: add to `PipelineStage` + `PipelineToasts.stageMessages`.

Stages: `DISCOVERING`, `ANALYZING`, `EVALUATING`, `DECIDING`, `DRAFTING`, `PROMOTING`, `QUEUED`.

### Targets Path Phases

`_run_targets_path` runs these phases sequentially. Each phase has clear inputs/outputs. Phases A-K run for both single-commit and batch paths.

A. Cycle creation — `EvaluationCycle` record + batch membership marking (deferred decisions get `batch_id` immediately)
B. Analysis enrichment — cache stage 1 JSON, backfill classification/tags
C. Brief update — LLM call to update project brief
D. Topic matching — tag-to-topic linking + topic suggestions from stage 1
E. Decision creation — validation, hold processing, decision record + trigger batch_id (emits `DECIDING`)
F. Arc activation — create new arcs from evaluator suggestions
G. Held decision absorption — process `consolidate_with` references
H. Queue actions — execute supersede/drop/merge on pending drafts
I. Diagnostics — run diagnostic checks, store on cycle
J. Routing + Drafting — route to targets, create drafts (emits `DRAFTING`)
K. Notification — cycle-level notification

`_run_targets_path` returns `TargetsPathResult(exit_code, cycle_id, decision_id)`. Callers use `.exit_code` for flow control, `.cycle_id` for batch references. `evaluate_batch` still returns `int`.

### Interval Gating

`_run_commit_analyzer_gate()` runs early in `run_trigger` — after config/project load, before context assembly/discovery/LLM setup. Deferred commits parse only the commit message, create a decision, and return. No context, no discovery, no LLM calls.

`_run_commit_analyzer()` resets the counter (called by threshold commits after context is assembled). Stage 1 LLM runs inline in `run_trigger` (single) or `evaluate_batch` (batch). Drain bypasses interval gating; `MANUAL_BYPASSES_INTERVAL` controls manual retrigger (default: respects queue). Lifecycle: `deferred_eval` → `processing` → `deferred_eval` with `batch_id`.

### Pipeline Diagnostics

Diagnostics run after every evaluation cycle. `_run_diagnostics()` in `trigger.py` builds a context dict and calls `diagnostics_registry.run()`. Results are stored as JSON on the `evaluation_cycles.diagnostics` column and surfaced in web UI, CLI, and messaging notifications.

### Draft Diagnostics

Draft diagnostics are computed at **read time** (not stored) because draft state changes through its lifecycle. `draft_diagnostics.py` registers checks on `draft_diagnostics_registry` — a separate `DiagnosticRegistry` instance from the pipeline one. The draft detail API endpoint runs the registry and injects `diagnostics: [...]` into the response. New checks: add a decorated function to `draft_diagnostics.py` — no frontend changes needed.

**Writing a new check:**
```python
from social_hook.diagnostics import Diagnostic, DiagnosticSeverity, diagnostics_registry

@diagnostics_registry.register("my_check_code")
def check_something(ctx: dict) -> list[Diagnostic] | None:
    if ctx.get("some_condition"):
        return [Diagnostic(
            code="my_check_code",
            severity=DiagnosticSeverity.WARNING,
            message="Something is misconfigured",
            suggestion="Fix it in Settings > ...",
            context={"relevant_key": "value"},
        )]
    return None
```

**Rules:**
- Checks are pure functions — no side effects, no DB writes, no LLM calls
- Context dict values must be small/specific metadata, not full config objects
- Each check is isolated via try/except — one bad check never breaks others or the pipeline
- `diagnostics.py` (core registry) has zero project imports — it's reusable (see [REUSABILITY.md](REUSABILITY.md))
- `pipeline_diagnostics.py` (domain checks) is project-specific
- New checks: add decorated function to `pipeline_diagnostics.py` — no other wiring needed

### Settings Scoping

Per-project settings (`content-config.yaml`) must always pass the project path when saving:
```typescript
await updateContentConfigParsed({ context: { ... } }, selectedProjectPath || undefined);
```
The page-level project selector in Settings controls `selectedProjectPath` for all sections. Global settings (Models, API Keys, Channels) use `saveConfig()` which writes to `~/.social-hook/config.yaml` regardless of the selected project.

## Logging

### Entry Point Init
Every process entry point must call `setup_logging(component)` before business logic. This wires the LogBus handler with all configured sinks. Never call `logging.basicConfig()` or create manual `FileHandler`s — `setup_logging()` replaces both.

### Module-Level Loggers
Use `logging.getLogger(__name__)` in all modules. This is the existing pattern — no change needed. The LogBus inherits through Python's logger hierarchy.

### Structured Context
Pass structured data via the `extra` dict:
```python
logger.error("Token refresh failed", extra={"project_id": pid, "draft_id": did})
```
The `JsonFormatter` includes these fields in the JSON output. The `DbSink` stores them in the `context` column.

### Run Correlation
For trigger/scheduler runs, call `set_run_id(generate_id("run"))` after `setup_logging()`. All subsequent log records from any module in that process will include the `run_id`.

### Error Feed Deprecation
`error_feed.emit()` is deprecated for new code. Use `logger.error(...)` instead — the `DbSink` routes WARNING+ to the `system_errors` table automatically. Existing `error_feed.emit()` calls still work but should be migrated over time.

### System Error Retention
The `system_errors` table is pruned automatically: the scheduler deletes entries older than 30 days on each tick. Manual clearing is available via `social-hook logs clear`, `DELETE /api/system/errors`, or the "Clear all" button in the web System tab.

### Reusability Rules
When modifying `logging.py`:
1. Only `constants.CONFIG_DIR_NAME` import allowed (for default log_dir). All other dependencies injected via constructor/function args.
2. No project-specific logic — no references to trigger, drafter, bot, or any domain concept.
3. Update [REUSABILITY.md](REUSABILITY.md) if interfaces change.

## Platform Config Access

Platform config uses dict-based access, not attribute-based:
- `config.platforms.get("x")` — returns `OutputPlatformConfig` or `None`
- `config.platforms["x"].enabled` — access fields on a specific platform
- `for name, pcfg in config.platforms.items()` — iterate all platforms

### Targets Config Access

Targets config follows the same dict-based access pattern:
- `config.accounts.get("product")` — returns `AccountConfig` or `None`
- `config.targets.items()` — iterate all targets
- `config.content_strategies.get("building-public")` — returns `ContentStrategyConfig` or `None`
- `config.platform_credentials` — dict of `PlatformCredentialConfig`
- `config.platform_settings.get("x")` — returns `PlatformSettingsConfig` or `None`

### Strategy Identity

A strategy is valid if it's either a built-in template (`setup/templates.py`) or a user-configured override in `content_strategies`. When validating strategy references (e.g., target → strategy), check both: `config.content_strategies` keys + `STRATEGY_TEMPLATES` IDs. The strategies API (`GET /api/projects/{id}/strategies`) merges both — config overrides take precedence over template defaults.

### Target Naming

Auto-generated target names use `{account}-{strategy}-{destination}` to avoid collisions when multiple targets share an account. Explicit `name` in the request body overrides this.

### Config Write Pattern

**Never read/write raw YAML.** The Config object may contain auto-migrated data not in the file. Read from `_get_config()` / `load_full_config()`, write via `save_config(data, config_path, deep_merge=True)`. When modifying an entry, build the full dict from the Config object — don't patch raw YAML.

### `check_unknown_keys` Strict Parameter

`check_unknown_keys(data, known_keys, section, *, strict=False)` from `parsing.py` validates config and API input keys. Default behavior: logs warnings for unknown keys. When `strict=True` (used in API endpoints), raises `ConfigError` for unknown keys instead of logging — this gives immediate feedback to API callers submitting malformed requests.

## Reusability Rules

### Multi-Provider LLM Layer

When modifying ANY of the 6 core files:
1. **Zero social-hook-specific imports.** Only `ConfigError` from `errors.py` is allowed (easily replaced with a local exception).
2. **No project-specific logic.** Core files must not reference evaluator, drafter, gatekeeper, social media, Telegram, or any domain concept.
3. **Update [REUSABILITY.md](REUSABILITY.md)** if you change interfaces, add parameters, or modify the extraction recipe.
4. New providers: implement `LLMClient.complete()`, add to factory's `create_client()`, add `ModelInfo` entries to catalog.
5. Tool schema conversion lives in the provider client, not in shared code.

### Messaging Platform Layer

When modifying core files (`base.py`, `factory.py`, `telegram.py`):
1. **Zero social-hook imports in `base.py`.** Only stdlib (`abc`, `dataclasses`, `logging`, `typing`). No exceptions.
2. **Only `ConfigError` and `AdapterRegistry` in `factory.py`.** Same pattern as `llm/factory.py` — easily replaced imports.
3. **No project-specific logic.** Core files must not reference bot, drafts, or any domain concept.
4. **Update [REUSABILITY.md](REUSABILITY.md)** if you change interfaces, add types, or modify the abstraction.
5. New platforms: implement `_do_send_message`, `_do_edit_message`, `answer_callback`, `get_capabilities` (and optionally `_do_send_media`). Add a `_create_*()` factory function and `register()` call in `factory.py`. Override `sanitize_text()` and `_is_format_error()` for platform-specific text escaping and format-error retry.
6. Button-to-platform conversion lives in the platform adapter, not in shared code.

### Adapter Registry

When modifying `registry.py`:
1. **Zero social-hook imports.** Only stdlib (`logging`, `typing`). No exceptions.
2. **No project-specific logic.** The registry is domain-agnostic — no references to platforms, media tools, or messaging.
3. **Update [REUSABILITY.md](REUSABILITY.md)** if you change the `AdapterRegistry` interface.

### Adapter Factory Pattern

All adapter factories (platform, media, messaging) use the same pattern:
1. **Per-adapter factory functions** — each platform/tool has its own private `_create_*()` function with lazy imports.
2. **Registry dispatch** — `_ensure_registered()` registers all factories; public API delegates to `_registry.create()`.
3. **No if/elif dispatch on adapter names.** Adding a new adapter = one factory function + one `register()` call.
4. **Backward-compatible public API** — existing function signatures (`create_adapter()`, `get_media_adapter()`, etc.) are unchanged.
