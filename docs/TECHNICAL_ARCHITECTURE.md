# Technical Architecture

> Implementation specifications for Social Hook, a Claude Code hook tool for automated social media content generation. Covers database schemas, state management, and tool-to-SQL mappings.

## Changelog

| Date | Change |
|------|--------|
| 2026-04-08 | Added: Content Vehicles — `vehicle` column on drafts (single/thread/article), `vehicle.py` pipeline module (resolve, validate, materialize, parse, post_by_vehicle), unified `draft(intent)` entry point replacing `draft_for_platforms()`/`draft_for_targets()`, `DraftingIntent` dataclass + 4 builder functions in `drafting_intents.py`, `compat.py` deleted. `ThreadResult` merged into `PostResult` (new `part_results` field). `DraftTweet` renamed to `DraftPart`, `draft_tweets` table renamed to `draft_parts`. `post_format` split into `vehicle` + `reference_type`. `SINGLE_POST` renamed to `SINGLE`, `ARTICLE` capability added (`auto_postable=False`). `PLATFORM_VEHICLE_SUPPORT` replaces `PLATFORM_THREAD_SUPPORT`. Advisory items table + CRUD + CLI/web/API. `file_reader.py` reusable token-budgeted file reader. Non-git project support (`register_project()` no longer requires git, `is_git_repo()` guards). Create Flow (`POST /api/projects/{id}/create-content`, `social-hook content create`). Universal brief system (freeform sections, `generate_brief_from_docs()`, `prompt_docs`). Vehicle in UX: notification headers, `refined_vehicle` on expert tool, evaluator `vehicle` field on `StrategyDecisionInput`. `build_platform_summaries()` includes tier + vehicles. |
| 2026-03-29 | Added: Domain Models Package section — models split into 7 submodules (enums, core, narrative, content, infra, context, _helpers). Dependency DAG and import convention documented. |
| 2026-03-28 | Decomposed: trigger.py split into 6 sibling modules (trigger_git, trigger_context, trigger_decisions, trigger_side_effects, trigger_batch, trigger_secondary). Module map added to Trigger Execution Model section. |
| 2026-03-28 | Refactored: All adapter factories (platform, media, messaging) use generic `AdapterRegistry` from `registry.py` instead of if/elif dispatch chains. New reusable component documented in [REUSABILITY.md](REUSABILITY.md). |
| 2026-03-24 | Updated: Targets system — preview mode (account optional on TargetConfig, `preview_mode` DB column, `draft connect` flow). Resolution helpers (`resolve_target_platform`, `resolve_default_platform`, `is_default_target_preview`). Strategies wired to evaluator at all 5 call sites. Shared-group drafting (single drafter call per strategy group). Removed synthetic "preview" platform references. |
| 2026-03-24 | Added: Targets system architecture — config model (platform_credentials, accounts, targets, content_strategies, platform_settings), two-stage evaluation pipeline, routing layer, ContentSource registry, AdapterRegistry, project brief, content topic queue, evaluation summary, new DB tables (content_topics, content_suggestions, evaluation_cycles, draft_patterns, system_errors, oauth_tokens). |
| 2026-03-24 | Added: Web OAuth 2.0 flow for X — three FastAPI endpoints (`/api/oauth/x/authorize`, `/api/oauth/x/callback`, `/api/oauth/x/status`). Updated X API Authentication section (OAuth 1.0a removed, web UI flow added). Updated Implementations table. |
| 2026-03-13 | Added: `post_now` action — schedule-for-now pattern via `scheduler_tick(draft_id=...)`. Capability registry (`PostCapability`, `MediaMode` frozen dataclasses, `capabilities()` on `PlatformAdapter` ABC). VCR cassette infrastructure for platform E2E tests. |
| 2026-03-13 | Updated: Draft Status Flow — added reverse transitions (unapprove, unschedule, reopen). Intro drafts cannot be reopened (cascade is not reversible). |
| 2026-03-13 | Updated: Bot daemon reliability — zombie-proof `is_pid_alive()` (ps-based state check), SIGKILL fallback in `stop_bot()`, child process reaping in web server (`_bot_proc` module state + `poll()`), `_parse_response` fix for `{"ok": false}` Telegram responses, send failure logging in button handlers (`_send_with_buttons`/`_send_media` helpers), `logging.basicConfig()` in bot foreground path, startup diagnostic logging (DB path, PYTHONPATH). Template Method on `MessagingAdapter`: `send_message`/`edit_message`/`send_media` now handle text sanitization and format-error retry at the base class level via `sanitize_text()` and `_is_format_error()` hooks. |
| 2026-03-12 | Updated: `ClaudeCliClient` — switched from `--output-format json` to `--output-format stream-json` (NDJSON). Text accumulated from `content_block_delta` events to avoid CLI bug #2904 string truncation. |
| 2026-03-12 | Updated: `broadcast_notification()` — added `exclude_chat` parameter for cross-platform terminal action notifications (approve/reject/schedule/cancel). |
| 2026-03-10 | Updated: Media Generation Adapters — added `spec_schema()` classmethod and `preview_text()` method to `MediaAdapter` interface (non-abstract with safe defaults). Added registry helpers: `get_tool_spec_schema()`, `get_blank_template()`, `list_available_tools()` with lazy class imports. Updated implementations table with required spec fields. |
| 2026-03-10 | Added: Pipeline Rate Limits section — daily evaluation cap, minimum gap timer, `deferred_eval` decision type, scheduler drain (individual + batch mode), `trigger_source` field, global scope with UTC day boundary. Added: Merge Queue Action section — `merge_group` and `merge_instruction` on QueueAction, merge execution flow, `_draft_for_resolved_platforms()` two-layer split in drafting.py, synthetic evaluation/commit objects. Updated: Evaluator Rework queue actions table to reflect full merge implementation. |
| 2026-03-10 | Updated: Evaluator context assembly — arcs now show with `[id=...]` and individual post IDs (500 chars each). Post History increased from 80 to 500 chars. Added arc safety net in drafting pipeline (auto-injects `reference_posts` for arc continuations). Added `--setting-sources local` flag to claude-cli provider notes. |
| 2026-03-10 | Added: Decision Rewind — `rewind_decision()` and `get_decision_by_commit()` in operations, `POST /api/decisions/{id}/rewind` endpoint, CLI `decision rewind` command. Trigger-source-agnostic design: DB operation and API use decision_id; CLI accepts both decision ID and commit hash via auto-detection. Auto-snapshot `_pre_rewind` before execution. |
| 2026-03-10 | Updated: Background task resilience — startup cleanup marks orphaned `running` tasks as `failed`; periodic TTL check (10 min) in `_event_bridge_loop` expires hung tasks and emits `data_change` events for live frontend recovery. |
| 2026-03-09 | Added: Cross-post reference interface — `ReferenceType` enum, `PostReference` dataclass, `post_with_reference()` and `supports_reference_type()` on `PlatformAdapter` ABC (concrete with LINK fallback). XAdapter: native QUOTE/REPLY. LinkedInAdapter: native QUOTE (reshare, LinkedIn URN only). Removed `post_raw()`. `reference_posts` column on decisions (migration 017). Updated scheduler posting path to use abstract `post_with_reference()`. |
| 2026-03-09 | Added: Snapshot CLI subsystem (`social-hook snapshot save/restore/reset/list/delete`). E2E test suite file structure (scripts/e2e/ package with section registry). |
| 2026-03-08 | Updated: Arc management — `PUT` endpoint enforces max-3 on resume, arc management API row added to endpoint table. |
| 2026-03-08 | Updated: Mutual exclusion between git hook and Claude Code commit hook (only one active at a time). Renamed Narrative Hook → Claude Code Narrative Hook. |
| 2026-03-08 | Added: Git post-commit hook — `install_git_hook()`, `uninstall_git_hook()`, `check_git_hook_installed()` in `install.py`. Hidden `social-hook git-hook` CLI command (logs to `~/.social-hook/logs/git-hook.log`). `project install-hook`/`uninstall-hook` CLI commands. Shared `register_project()` in `db/operations.py`. Web API: `GET /api/filesystem/browse`, `POST /api/projects/register`, `DELETE /api/projects/{id}`, git hook status/install/uninstall endpoints. `GET /api/projects` includes `git_hook_installed`. Mutual exclusion enforced at install time. Updated Hook Configuration and Trigger Execution Model sections. |
| 2026-03-08 | Added: Historical Commit Importing — `DecisionType.IMPORTED`, `branch` column on decisions (migration 016), `get_recent_decisions_for_llm()` excludes imported, `insert_decisions_batch()`, `get_distinct_branches()`. API: `GET decision-branches`, `GET import-preview`, `POST import-commits`, `branch` query param on `GET decisions`. CLI: `social-hook project import-commits`. Web UI: branch filter dropdown, import modal, imported badge on decisions, stat card excludes imported. New section: [Historical Commit Importing](#historical-commit-importing). |
| 2026-03-08 | Added: Deferred draft status (`DraftStatus.DEFERRED`, CHECK constraint, migration 016). Scheduler auto-promotion (`promote_deferred_drafts()` runs each tick). Scheduling-aware evaluator context (`get_scheduling_state()`, `ProjectSchedulingState`/`PlatformSchedulingState` dataclasses, `## Scheduling State` prompt section). Updated draft state diagram. |
| 2026-03-06 | Updated Pending Reply Flow: _save_angle() now calls Expert agent; _save_rejection_note() saves voice memory. Added draft redraft CLI command. |
| 2026-03-06 | Updated: Draft filtering — `GET /api/drafts` now accepts `project_id`, `decision_id`, `commit` query params. `get_drafts_filtered()` supports all four dimensions. CLI `draft list` gains `--decision` and `--commit` flags. Web drafts page shows active filter chips with dismiss. Project decisions link to filtered draft view. Media error (`last_error`) persisted from `_generate_media()` and displayed in web UI. |
| 2026-03-05 | Added: Decision management — `delete_decision()` cascading delete in operations, `DELETE /api/decisions/{id}` and `POST /api/decisions/{id}/retrigger` endpoints, CLI commands (`decision list/delete/retrigger`), web UI floating action bar integration. Bug fixes: Playwright crash signal handling, thread content stored as readable text (not JSON array), orphaned media cache IDs (`generate_id("media")`), RaySo crash error masking, decisions endpoint enriched with `draft_ids`. |
| 2026-03-12 | Added: Frontend UI components — `<AsyncButton>` / `<ElapsedTime>` / `<Spinner>` for elapsed timer display on async buttons, `<TopBanner>` reusable dismissable top notification, `<SlowTaskBanner>` for claude-cli users. Buttons wired across project page, draft action panel, and settings. |
| 2026-03-05 | Added: Background task system for long-running web API operations. `_run_background_task()` helper, `background_tasks` table (migration 015), `GET /api/tasks` query endpoint. Draft creation and consolidation endpoints return 202 with task_id. Frontend `useBackgroundTasks` hook restores spinners on page refresh via DB query + WebSocket events. |
| 2026-03-05 | Updated: Unified notification routing via `broadcast_notification()` replacing three duplicated send functions. Generalized pending reply state (`PendingReply` dataclass) supporting edit, schedule, angle, and reject-with-note flows. Button removal after action via `edit_message()`. Daemon-aware button stripping (no buttons when daemon not running). Quick Approve added to notification button layout. `emit_data_event` added to all Telegram button handlers. |
| 2026-03-05 | Updated: Media pipeline reorder — `_generate_media()` now runs AFTER first `drafter.create_draft()` using drafter's `media_spec`, not before. Expert `refined_media_spec` enables media refinement on rejection. `media_spec_used` column tracks actual spec used for generation. |
| 2026-03-05 | Added: CI/CD & Release Automation section (GitHub Actions workflows, pre-commit hooks, Release Please, PyPI trusted publishing) |
| 2026-03-05 | Updated: LLM Provider Abstraction — `extract_tool_call()` moved to `base.py`, raises `ToolExtractionError`; `NormalizedUsage` gains `cost_cents`; usage logging removed from provider clients, consolidated in `_usage_logger.py`; `SingleToolAgent` base class added in `agent.py` |
| 2026-03-04 | Added: Evaluator rework — new evaluator output format (commit_analysis + targets + queue_actions), new schema columns (episode_tags, targets, consolidate_with on decisions; is_intro, post_format, reference_post_id on drafts), hold mechanism, queue actions, intro lifecycle, scheduler post format assignment, pending draft context configuration. |
| 2026-02-27 | Added: Shared drafting module (`drafting.py` with `draft_for_platforms()`, `DraftResult`). Updated `POST /api/decisions/{id}/create-draft` to use real LLM drafter (platform optional, returns `draft_ids` array). New endpoints: `GET /api/platforms/enabled`, `POST /api/decisions/consolidate`. New CLI commands: `social-hook manual consolidate`, `social-hook inspect platforms`. Notification gap fix: `post_worthy` decisions with no platform drafts now notify under `all_decisions` mode. |
| 2026-02-27 | Added trigger branch filter: DB column, trigger flow step, API endpoints |
| 2026-02-26 | Added: Pipeline enrichment — Web session isolation (`session_id` column on `web_events`, `X-Session-Id` header, scoped event routing in WebSocket bridge). Gatekeeper context enrichment (recent decisions/posts, lifecycle phase, active arcs, narrative debt, audience state, linked decision passed to `gatekeeper.route()`). Commit decision notifications (`notification_level` config, `_send_decision_notification()` in trigger). Two-pass project discovery (`discovery_files` column schema v11, `discover_project()` in `llm/discovery.py`, `social-hook discover` CLI). Full web draft action parity (`DraftActionPanel` component with all 12 Telegram button actions). Media spec editor component. Arc system activation in trigger (auto-create arcs from evaluator `new_arc_theme`, auto-increment post counts). Editable project summaries in web UI with regenerate. Context settings section. `useSectionNav` hook for deep-linkable settings. Summary management API endpoints. |
| 2026-02-26 | Removed `WebConfig` dataclass and Notifications settings section. Notification routing now uses `channels.web.enabled` (defaults to True via `DEFAULT_CONFIG`). Web card in Channels section is toggleable. Setup wizard writes to `channels.web.enabled`. |
| 2026-02-26 | Added: Inline credentials pattern — `KEY_GROUPS` in `config/env.py` trimmed to cross-cutting keys only (Core, LLM Providers). Feature-specific keys managed inline in their settings sections (Channels, Platforms, Media Generation). |
| 2026-02-26 | Updated web dashboard section: SSE → WebSocket push, added `data_change` event type and `_event_bridge_loop` → `GatewayHub.broadcast()` flow. Replaced SSE endpoint with `/ws` WebSocket endpoint. Added `useDataEvents` auto-refresh description. |
| 2026-02-26 | Added: Channel Configuration section (`ChannelConfig` dataclass, `KNOWN_CHANNELS` constant, channels parsing in config). Refactored `create_bot()` to channel-aware with `_create_telegram_runner()` helper and legacy env-var fallback. New API endpoints: `GET /api/channels/status`, `POST /api/channels/{channel}/test`. Updated Daemon Boundary Pattern section for new signature. Updated Messaging Platform Abstraction with WebAdapter in platform table. |
| 2026-02-25 | Added: Consolidation processing architecture (two modes: re_evaluate, notify_only), batch processing via scheduler tick, lock pattern, ConsolidationConfig. New DB columns on decisions (commit_summary, processed, processed_at, batch_id) via migration 009. New API endpoints for project detail, decisions, posts, usage, arcs. Scheduler notifications now adapter-based (Web + Telegram via `send_notification()`). Updated dashboard architecture with project detail page. |
| 2026-02-25 | Added: Platform-agnostic chat history via `chat_messages` table (schema v8). Replaces WebAdapter-specific `web_events` sniffing — works for Telegram, Web, and future adapters. Added "Live Data" section to gatekeeper prompt so LLM knows System Status is real-time. Handlers now return response text for chat history storage. |
| 2026-02-24 | Added: System snapshot context injection for Gatekeeper. `_build_system_snapshot()` in `commands.py` assembles live DB + config data (projects, drafts, arcs, posts, platforms, scheduling, media tools). `handle_message()` now always opens DB, resolves first active project if no draft context, and passes `system_snapshot` + `project_summary` to `gatekeeper.route()`. New `system_snapshot` parameter threaded through `Gatekeeper.route()` and `assemble_gatekeeper_prompt()`. |
| 2026-02-24 | Added: Gatekeeper text fallback for conversational messages. `query` operation now handles greetings and general questions. `_extract_text_content()` safety net in `gatekeeper.py`. |
| 2026-02-24 | Updated: Media tool guidance defaults moved from Python (`DEFAULT_MEDIA_GUIDANCE`) to `content-config.yaml`. Python constant is now structural-only (empty tool slots). Config split docs updated. |
| 2026-02-24 | Updated: projects table DDL to include `paused` column. Renamed `image_generation` to `media_generation` in config.yaml example and Setup Wizard snippet. Documented config split (config.yaml = infrastructure, content-config.yaml = content guidance). Added new API endpoints: content-config parsed, project pause. |
| 2026-02-21 | Added: Web Dashboard API section (FastAPI server architecture, endpoint categories, security model, WebAdapter integration). |
| 2026-02-21 | Updated: Bot Capabilities section -- replaced Adapter Bridge Pattern with Daemon Boundary Pattern and Handler Abstraction; documented notification helpers cleanup. |
| 2026-02-21 | Added: Platform Configuration section (dynamic registry, OutputPlatformConfig/ResolvedPlatformConfig resolution flow, smart defaults, content filters, WebConfig). |
| 2026-02-21 | Added: Time-window narrative filtering (commit timestamps, `after`/`before` params, `_in_window` flag, timezone handling). Updated Context Assembly code snippet and docs. |
| 2026-02-20 | Added: Development Journey Capture section (PreCompact hook, transcript pipeline, ExtractNarrativeInput schema, JSONL storage, context assembly flow). |
| 2026-02-19 | Added: Bot Capabilities section (draft context threading, edit save flow, substitute handler, expert save-back, adapter bridge). Added Messaging Platform Abstraction section. |
| 2026-02-15 | Updated: LLM Provider Abstraction rewritten for multi-provider support (5 providers, LLMClient ABC, NormalizedResponse, factory pattern). Updated .env, config.yaml, Model Configuration, and Setup Wizard sections for `provider/model-id` format. |
| 2026-02-09 | Updated: X tier character limits table (added `basic` tier, all paid = 25K chars). Thread strategy now narrative-first: format driven by beat count, not char overflow. |
| 2026-02-08 | Updated: Marked First-Time Setup Wizard as implemented (WS4 complete). Media adapter registry code block to match WS3 implementation (get_media_adapter factory). |
| 2026-02-07 | Added: context-notes.md file spec alongside memories.md; Added context note persistence functions to expert_response description |
| 2026-02-06 | Added: Expert Escalation Context Assembly section; Documented major_artifact detection as LLM-driven (Evaluator analyzes commit context) |
| 2026-02-06 | Fixed: Renamed media_suggestion→media_tool in log_decision schema for DB/Guide consistency; Added cancel to route_action operation enum |
| 2026-02-06 | Updated: Runtime Assembly with per-agent context (Evaluator/Drafter/Gatekeeper), including arc context injection for Drafter; Added context configuration; Clarified dry-run mode; Added get_recent_posts_for_context function; Added project summary system; Added compaction section |
| 2026-02-05 | Added: SDK exception handling, tool call response parsing, Pydantic validation sections |
| 2026-02-05 | Added: API field mapping note for usage_log cache token columns |
| 2026-02-04 | Added: Configuration inheritance section (project → global fallback); Updated setup wizard steps for global config creation |
| 2026-02-04 | Added: X API v2 error format, Nano Banana Pro API details; Updated: Per-project config paths to .social-hook/ |
| 2026-02-03 | Added: Setup wizard implementation (Rich + InquirerPy + Typer stack, OAuth flows, validation) |
| 2026-02-03 | Added: Hook configuration, trigger model, scheduler, logging, file system, prompt management, tool schemas, media/platform adapters |
| 2026-02-03 | Added: Interface separation and Telegram message flow diagrams to System Overview |
| 2026-02-03 | Updated: Day 2 Considerations with LLM provider abstraction and Telegram webhook mode |
| 2026-02-03 | Added: Test CLI interface, flags, output format, exit codes to Testing Strategy section |
| 2026-02-03 | Updated: Testing Strategy section to reference REQUIREMENTS.md Functional Testing Strategy (removed outdated mock mention) |
| 2026-02-01 | Fixed: State diagram to show correct approval paths (draft→scheduled vs draft→approved), added missing `updated_at` to arcs table |
| 2026-02-01 | Fixed: Added `cancelled` to status CHECK constraint, updated state diagram, fixed memories.md path, fixed update_thread_tweet example |
| 2026-02-01 | Added: Thread sync rules (draft_tweets as source of truth), memories.md schema, API error taxonomy, fixed arc stagnation SQL |
| 2026-02-01 | Added: idx_draft_tweets_external, supersede_draft(), project registration, timezone docs |
| 2026-02-01 | Added: Platform status values, idx_decisions_arc index |
| 2026-02-01 | Updated: 3 roles with configurable models (Evaluator defaults to Opus) |
| 2026-02-01 | Initial creation: SQLite DDL, tool call mappings, state lifecycles, file system layout |

---

## Table of Contents

1. [System Overview](#system-overview)
2. [File System Layout](#file-system-layout)
3. [Database Schema](#database-schema)
4. [Schema Design Decisions](#schema-design-decisions)
5. [Tool Call Implementation](#tool-call-implementation)
6. [State Lifecycles](#state-lifecycles)
7. [Platform Abstraction](#platform-abstraction)
8. [Error Handling](#error-handling)
9. [Platform API Rate Limiting](#platform-api-rate-limiting)
10. [Hook Configuration](#hook-configuration)
11. [Trigger Execution Model](#trigger-execution-model)
12. [Scheduler Implementation](#scheduler-implementation)
13. [Logging/Observability](#loggingobservability)
14. [File System Details](#file-system-details)
15. [LLM Prompt Management](#llm-prompt-management)
16. [Tool Call Schemas](#tool-call-schemas)
17. [Media Generation Adapters](#media-generation-adapters)
18. [Platform Posting Adapters](#platform-posting-adapters)
19. [Setup Wizard Implementation](#setup-wizard-implementation)
20. [Development Journey Capture](#development-journey-capture)
21. [Consolidation Processing](#consolidation-processing)
22. [Evaluator Rework](#evaluator-rework)
23. [Historical Commit Importing](#historical-commit-importing)
24. [Pipeline Rate Limits](#pipeline-rate-limits)
25. [Merge Queue Action](#merge-queue-action)
26. [Content Vehicles](#content-vehicles)
27. [Day 2 Considerations](#day-2-considerations)

---

## System Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Git Post-Commit Hook                             │
│  ┌─────────────────┐                                                    │
│  │  post-commit    │──── social-hook git-hook ───┐                      │
│  │  (any editor)   │                             │                      │
│  └─────────────────┘                             │                      │
└──────────────────────────────────────────────────│──────────────────────┘
                                                   │
┌──────────────────────────────────────────────────│──────────────────────┐
│                       Claude Code Session        │                       │
│  ┌─────────────────┐                             │                      │
│  │  PostToolUse    │──── git commit detected ────┤                      │
│  │  Hook (Bash)    │                             │                      │
│  └─────────────────┘                             ▼                      │
└─────────────────────────────────────────────────────────────────────────┘
                                                   │ (dedup via UNIQUE)
                                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Central Coordinator                              │
│                                                                          │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │  GATEKEEPER     │    │  EVALUATOR      │    │  DRAFTER/EXPERT │     │
│  │  (default:Haiku)│    │  (default:Opus) │    │  (default:Opus) │     │
│  │                 │    │                 │    │                 │     │
│  │  - Timing       │    │  - Post-worthy? │    │  - Draft content│     │
│  │  - Routing      │    │  - Vehicle hint │    │  - Creative     │     │
│  │  - Simple edits │    │  - Strategy     │    │  - Cross-project│     │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘     │
│           │                      │                      ▲               │
│           └──────────────────────┴──────────────────────│───────────    │
│                                  │                      │               │
│                                  ▼                      │               │
│                    ┌─────────────────────────┐          │               │
│                    │  SQLite Database        │          │               │
│                    │  (~/.social-hook/       │          │               │
│                    │    social-hook.db)      │          │               │
│                    └─────────────────────────┘          │               │
└─────────────────────────────────────────────────────────│───────────────┘
                                   │                      │
           ┌───────────────────────┼──────────────────┐   │
           ▼                       ▼                  ▼   │
┌─────────────────┐    ┌─────────────────┐    ┌──────────┴──────┐
│  Telegram /     │    │    X API        │    │  Media Gen      │
│  Web Dashboard  │    │                 │    │  (Nano Banana)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                      ▲
┌─────────────────────────────────────────────────────│───────────────────┐
│                    Operator (Web UI / CLI)           │                   │
│  ┌─────────────────┐                                │                   │
│  │  Create Content │──── bypasses Evaluator ────────┘                   │
│  │  (web / CLI)    │    (direct to Drafter)                             │
│  └─────────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

**Commit-triggered flow:**
```
1. Hook fires on git commit (git post-commit hook OR Claude Code PostToolUse)
2. Deduplication: DB UNIQUE constraint on (project_id, commit_hash) — second trigger is a no-op
3. Coordinator identifies project from working directory
4. Evaluator assesses: post-worthy? Suggests content vehicle (single/thread/article)
5. If yes, Drafter creates content in the chosen vehicle format (1-pass)
6. Gatekeeper coordinates timing across projects (default: Haiku)
7. Draft sent to Telegram and/or web dashboard for human review
8. Human approves/edits/rejects (Gatekeeper handles, escalates to Expert if needed)
9. Scheduler posts at scheduled time. Articles create advisory items (manual posting).
10. All decisions logged to SQLite
```

**Operator-initiated flow (Create):**
```
1. Operator types idea via web dashboard or CLI (social-hook content create)
2. Drafter creates content directly (no evaluator, no commit)
3. Same approval + posting flow as above (steps 7-10)
```

### Interface Separation

```
+-------------------------------------------------------------+
|                     CLI INTERFACE                            |
|         (humans, hooks, cron - runs commands)               |
+-------------------------------------------------------------+
|  social-hook trigger    |  social-hook bot start            |
|  social-hook git-hook   |  social-hook web                  |
|  social-hook test       |  social-hook advisory             |
|  social-hook project    |  social-hook inspect              |
|  social-hook manual     |  social-hook draft                |
|  social-hook config     |  social-hook memory               |
|  social-hook arc        |  social-hook discover             |
|  social-hook content    |  social-hook setup                |
|  social-hook help --json|  social-hook snapshot             |
|  social-hook scheduler-tick | social-hook consolidation-tick|
+-----------------------------+-------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                   PYTHON APPLICATION                         |
|              (loads config, connects DB)                     |
+-----------------------------+-------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                   CLAUDE API INTERFACE                       |
|         (LLMs invoked via API, not CLI)                     |
+-------------------------------------------------------------+
|  Evaluator prompt + context -> Claude -> decision JSON      |
|  Drafter prompt + context   -> Claude -> draft content      |
|  Gatekeeper prompt + msg    -> Claude -> action/escalate    |
+-------------------------------------------------------------+
```

### Telegram Message Flow

```
+-------------+
|   Human     |
|  (Telegram) |
+------+------+
       | message
       v
+-----------------+
|   GATEKEEPER    |
|  (Haiku)        |
+-----------------+
| Simple?         |
| +-- approve -> OK|
| +-- schedule -> OK
| +-- reject -> OK |
| +-- complex? ----+------+
+-----------------+       |
                          v
                 +-----------------+
                 |     EXPERT      |
                 |    (Opus)       |
                 +-----------------+
                 | - Refine draft  |
                 | - Answer why    |
                 | - Save notes    |
                 +-----------------+
```

### Bot Capabilities

#### Draft Context Threading

When `trigger.py` sends a Telegram notification, it calls `set_chat_draft_context(chat_id, draft_id, project_id)` to record which draft this chat is interacting with. The context is stored in a module-level dict with a 1-hour TTL (`_CONTEXT_TTL_SECONDS = 3600`).

When a free-text message arrives, `handle_message()` always opens a DB connection and builds a system snapshot via `_build_system_snapshot()`. It looks up draft context via `get_chat_draft_context(chat_id)`, and if no project is associated, resolves the first active (non-paused) project. The draft object, project_id, project_summary, and system_snapshot are all passed through to `gatekeeper.route()` and `_handle_expert_escalation()`. This enables context-aware responses — the Gatekeeper can answer questions about system state (drafts, platforms, schedule) and reference the specific draft.

Context is also set by `/review`, button handlers (`btn_approve`, `btn_edit_text`, etc.), and the edit save flow.

#### Pending Reply Flow

Four button actions require a follow-up text reply from the user. They share a generalized pending state via `PendingReply` dataclass in `buttons.py`:

```python
@dataclass
class PendingReply:
    type: str  # "edit_text", "schedule_custom", "edit_angle", "reject_note"
    draft_id: str
    timestamp: float
```

Stored in `_pending_replies: dict[str, PendingReply]` with 5-minute TTL (`_REPLY_TTL_SECONDS = 300`).

**Flow:**
1. User taps a reply-expecting button (e.g., "Change text", "Custom time", "Change angle", "Reject with note")
2. Handler registers `PendingReply` with the appropriate type
3. User replies with text
4. `handle_message()` checks `get_pending_reply(chat_id)` first, before Gatekeeper routing
5. `_handle_pending_reply()` dispatches to the appropriate handler based on `pending.type`:
   - `edit_text` → `_save_edit()`: updates content, creates `DraftChange` audit trail
   - `schedule_custom` → `_save_custom_schedule()`: parses ISO 8601, sets status to "scheduled"
   - `edit_angle` → `_save_angle()`: calls Expert agent to redraft content with new angle, creates DraftChange audit trail, sends review buttons
   - `reject_note` → `_save_rejection_note()`: rejects with note, saves feedback as voice memory via `save_memory()`, cascades `on_intro_rejected()`
6. All handlers call `emit_data_event()` for web dashboard reactivity
7. Pending reply is cleared

If the TTL expires, the message falls through to normal Gatekeeper routing. Invalid input (e.g., bad ISO format for schedule) sends an error and re-sets the pending reply for retry.

#### Substitute Handler

The Gatekeeper can route messages like "use this instead: [new content]" to a `substitute` operation. The handler in `_handle_gatekeeper_direct()`:
1. Extracts the new content from `route.params["content"]`
2. Resolves `draft_id` from params or from `get_chat_draft_context()`
3. Calls `_save_edit()` with `changed_by="gatekeeper"`

#### Expert Save-Back

When the Expert returns `action="refine_draft"` with `refined_content`:
- If a draft exists in context: saves refined content to DB via `update_draft()`, creates `DraftChange` with `changed_by="expert"`, sends the refined content with review buttons
- If no draft in context: shows refined content as a message only (no DB save)
- If `refined_media_spec` is provided: triggers media regeneration with the new spec. The expert can adjust media parameters (e.g., change a mermaid diagram, update code snippet language for ray_so) based on user feedback about the media.
- If `refined_vehicle` is provided: updates `draft.vehicle` via `update_draft()`, calls `materialize_vehicle_artifacts()` to create/delete draft parts for the new vehicle, creates `DraftChange` with `field="vehicle"`. The expert can change a single post to a thread or vice versa.

`_save_angle()` provides a direct path to Expert refinement, bypassing the Gatekeeper. When the user taps "Change angle" and replies with a new angle, `_save_angle()` calls `Expert.handle()` with `escalation_reason="angle_change"` and the user's angle text as `user_message`. It follows the same save-back path as Gatekeeper-routed escalations: updates content + media spec, creates `DraftChange` audit trail, emits `data_change` event. Unlike the Gatekeeper path, it also passes `project_summary` for richer context.

#### Daemon Boundary Pattern

`create_bot()` in `daemon.py` is **channel-aware** — it reads the `channels` config section to determine which messaging channels to start, falling back to legacy env vars when no channels are configured.

```python
def create_bot(config, *, token=None, allowed_chat_ids=None):
    # Channel-aware path: iterate config.channels for enabled entries
    # Legacy fallback: read TELEGRAM_BOT_TOKEN from config.env
    # Returns BotDaemon with one runner per enabled channel
```

Handler wiring is extracted into `_create_telegram_runner()`, which is the **Telegram boundary** — the only place where raw Telegram dicts are converted to abstract types:

```python
def _create_telegram_runner(token, allowed_chat_ids, config):
    adapter = TelegramAdapter(token=token)

    def on_command(message: dict) -> None:
        msg = TelegramAdapter.parse_message(message)
        handle_command(msg, adapter, config)
    # ... on_callback, on_message follow same pattern

    return TelegramRunner(token=token, allowed_chat_ids=allowed_chat_ids, ...)
```

The `TelegramAdapter` is created once and shared across all handler closures. `parse_message()` and `parse_callback()` are static methods on `TelegramAdapter` that convert raw Telegram dicts to `InboundMessage` and `CallbackEvent` respectively.

**Channel resolution order:**
1. If `config.channels` has enabled entries → create runners for each (currently only Telegram produces a runner; Web is handled by FastAPI; Slack is a stub)
2. Else if `token` param provided → legacy single-runner mode
3. Else read `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_CHAT_IDS` from `config.env`
4. If no runners can be created → raise `ConfigError`

#### Handler Abstraction

Handlers in `commands.py` and `buttons.py` accept abstract types instead of raw Telegram dicts:

```
Telegram raw dict  -->  TelegramAdapter.parse_*()  -->  InboundMessage / CallbackEvent
                                                              |
handlers (buttons.py, commands.py) <-- abstract types --------+
                                                              |
Web API JSON body  -->  direct construction          -->  InboundMessage / CallbackEvent
```

Handler signatures:
- `handle_command(msg: InboundMessage, adapter: MessagingAdapter, config)`
- `handle_message(msg: InboundMessage, adapter: MessagingAdapter, config)`
- `handle_callback(event: CallbackEvent, adapter: MessagingAdapter, config)`

This enables any new messaging platform (web dashboard, Discord, Slack) to reuse the same handlers by constructing `InboundMessage`/`CallbackEvent` from its own wire format and providing a `MessagingAdapter` for sending responses.

#### Notification Helpers

`bot/notifications.py` is a pure formatting module with two functions:
- `format_draft_review()` -- formats draft review notification text. Accepts `vehicle` parameter: shows `[X · thread]` or `[X · article]` in the header (single is implicit). Articles are truncated to 500 chars in the notification.
- `get_review_buttons_normalized()` -- returns `list[ButtonRow]` with Quick Approve, Schedule, Edit, Reject buttons

### Model Configuration

Models are configurable per-role using `provider/model-id` format. Defaults optimized for quality:

| Role | Default | Alternative | Trade-off |
|------|---------|-------------|-----------|
| Evaluator | `anthropic/claude-opus-4-5` | `claude-cli/sonnet` | $0 with subscription, ~4-8s latency |
| Drafter/Expert | `anthropic/claude-opus-4-5` | `claude-cli/sonnet` | $0 with subscription, ~4-8s latency |
| Gatekeeper | `anthropic/claude-haiku-4-5` | `claude-cli/haiku` | $0 with subscription, ~4-8s latency |

### Platform Configuration

Platforms are configured as a dynamic registry in `config.yaml`. Each platform is an entry in a `platforms` dict with an `OutputPlatformConfig` dataclass (`config/platforms.py`).

#### Resolution Flow

```
config.yaml "platforms" dict
       │
       ▼
OutputPlatformConfig (raw, may have None fields)
       │
       │  resolve_platform(name, raw, global_scheduling)
       ▼
ResolvedPlatformConfig (all fields populated)
       │
       ├── filter: resolved from priority + platform smart defaults
       ├── frequency: resolved from priority + platform smart defaults
       ├── max_posts_per_day: from frequency preset or scheduling override
       ├── min_gap_minutes: from frequency preset or scheduling override
       └── optimal_days/hours: from scheduling override or global config
```

#### Smart Defaults

| Platform | Priority | Filter | Frequency |
|----------|----------|--------|-----------|
| x | primary | all | high (3/day, 30min gap) |
| x | secondary | notable | moderate (1/day, 2hr gap) |
| linkedin | primary | notable | moderate (1/day, 2hr gap) |
| linkedin | secondary | significant | low (1/day, ~2day gap) |
| _custom | primary | notable | moderate (1/day, 2hr gap) |
| _custom | secondary | significant | low (1/day, ~2day gap) |

#### Content Filters

| Filter | Episode Types |
|--------|--------------|
| all | All `post_worthy` commits |
| notable | milestone, launch, synthesis, demo_proof, before_after, postmortem |
| significant | milestone, launch, synthesis |

When web channel notifications are enabled (`channels.web.enabled`, defaults to True), the system writes notification events to `web_events` table. The `_event_bridge_loop` background task polls this table and pushes new entries to WebSocket clients via `GatewayHub.broadcast()`.

#### ChannelConfig

Channels (messaging platforms you interact *through*) are separate from output platforms (where content gets *published*). Configured in `config.yaml` under the `channels` key.

```python
KNOWN_CHANNELS = {"telegram", "slack", "web"}

@dataclass
class ChannelConfig:
    enabled: bool = False
    allowed_chat_ids: list[str] = field(default_factory=list)
```

The `Config` dataclass includes `channels: dict[str, ChannelConfig]` (default empty dict). Secrets (tokens) stay in `.env` — `ChannelConfig` holds only non-secret settings. `KNOWN_CHANNELS` is the single source of truth, imported by `server.py` for the channels API endpoints.

#### Channels API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/channels/status` | GET | Returns status of all known channels (enabled, credentials_configured, allowed_chat_ids) plus `daemon_running` flag |
| `/api/channels/{channel}/test` | POST | Tests channel connectivity. Telegram: calls `getMe` API. Web: always succeeds. Slack: returns "coming soon". Unknown: 400. Sanitizes errors to never expose tokens. |

The existing `/api/installations/bot_daemon/start` and `/api/installations/bot_daemon/stop` endpoints remain for backward compat — the frontend Channels section reuses these.

The `chat_messages` table stores platform-agnostic conversational history for LLM context assembly. Both Telegram and Web chat messages are stored here, enabling the Gatekeeper to resolve conversational references across all platforms. This is separate from `web_events` (which serves the WebSocket push stream) — two tables, two purposes.

#### Drafting Pipeline

The trigger pipeline builds a `DraftingIntent` and passes it to the unified `draft()` entry point:

```
Evaluator (per-strategy decisions, suggests vehicle)
       │
       ▼
intent_from_routed_targets() / intent_from_platforms()
       │  (builds DraftingIntent with PlatformSpec list)
       ▼
draft(intent)
       │
       ├── resolve_vehicle(evaluator_suggestion, operator_choice, capabilities)
       ├── drafter.create_draft(vehicle=resolved) — single LLM call (or shared-group)
       ├── validate_draft_for_vehicle() — re-call once if invalid + suggested_vehicle
       ├── _generate_media(drafter's media_spec) — once, shared across platforms
       └── _finalize_draft() per platform:
           ├── calculate_optimal_time()
           ├── materialize_vehicle_artifacts() — create draft_parts for threads
           └── insert Draft + emit events
       │
       ▼
broadcast_notification() — routes to all enabled channels
```

The evaluator receives `platform_summaries` as read-only context (e.g., "x (primary, basic tier, 25K chars) — vehicles: Self-contained post, Multi-part narrative") and makes per-strategy decisions. `build_platform_summaries()` includes tier, character limit, and available content vehicles from `PLATFORM_VEHICLE_SUPPORT`.

Media is generated after the drafter call, using the drafter's `media_spec` (tool-specific fields like `{code, language?, title?}` for ray_so or `{diagram}` for mermaid). The drafter call produces both content and the media spec; `_generate_media()` runs once with that spec; all platforms share the generated media. This gives the drafter control over media parameters rather than generating from an empty spec.

#### Shared Drafting Module (`drafting.py`)

The drafting pipeline lives in `src/social_hook/drafting.py` with a single entry point shared by the trigger pipeline, web API, CLI, and create flow.

- **`draft(intent: DraftingIntent, ...) -> list[DraftResult]`** — THE single drafting entry point. Replaces both `draft_for_platforms()` and `draft_for_targets()`. Handles: vehicle resolution via `resolve_vehicle()`, LLM draft creation (single call for one platform, shared-group call for multiple), vehicle validation via `validate_draft_for_vehicle()`, artifact materialization via `materialize_vehicle_artifacts()`, media generation, scheduling, and DB insertion. If `len(intent.platforms) > 1`: shared-group LLM call (multi-variant). If `len(intent.platforms) == 1`: single-platform LLM call.
- **`DraftingIntent`** — Dataclass containing everything the pipeline needs: vehicle preference, angle, reasoning, platforms (`list[PlatformSpec]`), arc/reference enrichment, content source context, and pipeline metadata. Replaces all `SimpleNamespace` evaluations and the `compat.py` shim.
- **`PlatformSpec`** — A single platform target within a `DraftingIntent`: platform name, `ResolvedPlatformConfig`, optional `target_id`, `preview_mode`.
- **`DraftResult`** — Dataclass containing the `Draft` model, `ScheduleResult`, and parsed `thread_parts`.
- **`_finalize_draft()`** — Internal helper extracting ~130 lines of duplicated post-LLM code into one function: scheduling, Draft construction, DB insertion, `materialize_vehicle_artifacts()`, events.
- **`_generate_media()`** — Shared media generation, accepts drafter's `media_spec`.
- **`media_spec_used`** — Each draft records the actual `media_spec` used for generation (stored as JSON in the `media_spec_used` column), enabling a "spec unchanged" guard to skip redundant media regeneration.

**Arc safety net:** When the evaluator sets `arc_id` on a decision but does NOT set `reference_posts`, the drafting pipeline automatically injects the arc's latest published post into `reference_posts`. This ensures arc continuations always get structural links (quote tweets, replies) without relying on the LLM to set both fields.

**Deleted:** `draft_for_platforms()`, `draft_for_targets()`, `_draft_for_resolved_platforms()`, `_draft_shared_group()`, `_resolve_and_filter_platforms()`, `_resolve_target_platform()`, `_needs_thread()`, `_parse_thread_tweets()`, both `_resync_thread_tweets()` implementations, `compat.py` (`make_eval_compat`, `evaluation_from_decision`).

Callers construct a `DraftingIntent` via builder functions in `drafting_intents.py` (see [Content Vehicles](#content-vehicles)) and pass it to `draft()`.

#### WebAdapter

`messaging/web.py` is a SQLite-backed `MessagingAdapter` (reusable core — zero social-hook imports). It writes all outbound messages to the `web_events` table:

```sql
CREATE TABLE web_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type       TEXT NOT NULL,        -- "message", "edit", "callback_ack", "media"
    data       TEXT NOT NULL,        -- JSON: {chat_id, text, buttons, ...}
    session_id TEXT DEFAULT NULL,    -- Per-tab session scoping (NULL = broadcast to all)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_web_events_session ON web_events(session_id);
```

Events older than 7 days are cleaned up automatically (amortized, every 100 writes). The `_event_bridge_loop` background task polls this table and routes events to WebSocket clients: broadcast events (`session_id IS NULL`) go to all connections; scoped events go only to the matching session. The `X-Session-Id` header (set by the frontend `getSessionId()` helper) ensures multiple browser tabs don't interfere with each other.

#### Data Change Events

Mutation points (trigger, scheduler, CLI, bot handlers) call `emit_data_event(conn, entity, action, entity_id, project_id)` to write a `data_change` event to `web_events`. The `_event_bridge_loop` picks these up and pushes them over WebSocket. The frontend `useDataEvents` hook filters by entity type and debounces (500ms) to auto-refresh data pages. Supported entities: `decision`, `draft`, `post`, `project`.

All Telegram button handlers that change draft status (`btn_approve`, `btn_quick_approve`, `btn_reject`, `btn_schedule_optimal`, `btn_cancel`) and reply handlers (`_save_edit`, `_save_custom_schedule`, `_save_angle`, `_save_rejection_note`) now emit `data_change` events, ensuring the web dashboard updates in real time when actions are taken via Telegram.

#### Notification Routing

`broadcast_notification()` in `notifications.py` is the unified entry point for all notification delivery. It replaces the previously duplicated `_send_notifications()` and `_send_decision_notification()` functions from `trigger.py`.

```python
def broadcast_notification(
    config: Config,
    message: OutboundMessage,
    *,
    media: list[str] | None = None,
    dry_run: bool = False,
    chat_context: tuple[str, str] | None = None,  # (draft_id, project_id)
    exclude_chat: str | None = None,  # skip this chat_id to avoid double-notify
) -> None:
```

Channel iteration logic:
- **Web** (enabled by default, disabled via `channels.web.enabled: false`): Creates `WebAdapter` and writes to `web_events` table. Always includes buttons (web handles callbacks directly via API server). Skipped when `exclude_chat` starts with `"web:"` (web tabs refresh via `emit_data_event`).
- **Telegram** (when channel enabled + `TELEGRAM_BOT_TOKEN` + chat IDs configured): Creates `TelegramAdapter` and sends to all allowed chat IDs. **Daemon-aware button stripping:** checks `bot.process.is_running()` — if the daemon is not running, buttons are removed from the message before sending (since there's no daemon to handle callbacks). If `chat_context` is provided, sets draft context for each chat ID. If `exclude_chat` matches a chat_id, that chat is skipped.
- **Telegram env-var fallback:** When `telegram` is not in `config.channels`, checks for `TELEGRAM_BOT_TOKEN` env var. If present, treats as enabled with chat IDs from `TELEGRAM_ALLOWED_CHAT_IDS` (comma-split).
- **Media:** For channels supporting media (`caps.supports_media`), sends each media path after the message.

The backward-compat `send_notification(config, message_str, dry_run)` wrapper delegates to `broadcast_notification()` with a plain `OutboundMessage`.

**Notification gap fix:** When a `post_worthy` decision produces no drafts (e.g., no enabled platforms), a plain decision notification is still sent via `broadcast_notification()` if `notification_level != "drafts_only"`.

#### Button Removal After Action

When a user clicks a state-changing button (Approve, Quick Approve, Reject, Schedule, Cancel), the original notification message's buttons are removed via `edit_message()` to prevent double-actions. The handler calls `_clear_original_buttons(adapter, chat_id, message_id, draft_id, action_label)` which replaces the notification with a concise status line (e.g., "Draft `abc123...` — Approved").

Submenu and prompt buttons (Schedule submenu, Edit submenu, Change text, etc.) do NOT clear the original buttons since they're intermediate steps.

The `message_id` is threaded from `CallbackEvent.message_id` through `handle_callback()` into each handler via `kwargs`.

### Web Dashboard API

`web/server.py` provides a FastAPI application serving the web dashboard. It runs on localhost (default port 8741) and provides four endpoint groups:

#### Endpoint Categories

| Category | Endpoints | Purpose |
|----------|-----------|---------|
| **Bot Interaction** | `POST /api/command`, `/api/callback`, `/api/message` | Construct `InboundMessage`/`CallbackEvent`, call handlers, return new `web_events` |
| **WebSocket** | `/ws` | Real-time push of `web_events` and `data_change` events via `GatewayHub` |
| **Data Queries** | `GET /api/drafts` (params: `status`, `project_id`, `decision_id`, `commit`), `/api/drafts/{id}`, `/api/projects`, `/api/media/{path}` | Read-only DB and file access with composable filters |
| **Settings** | `GET/PUT /api/settings/config`, `/env`, `/social-context`, `/content-config`, `/content-config/parsed`, `POST /validate-key` | Config file management with validation |
| **Projects** | `GET /api/projects`, `GET /api/projects/{id}`, `PUT /api/projects/{id}/pause` | Project listing (includes `git_hook_installed` per project), detail (lifecycle/arcs/stats), pause/unpause |
| **Project Branches** | `GET /api/projects/{id}/branches`, `PUT /api/projects/{id}/trigger-branch` | List local git branches for a project, set trigger branch filter |
| **Project Data** | `GET /api/projects/{id}/decisions` (param: `branch`), `/posts`, `/usage`, `/arcs` | Per-project decision history (filterable by branch), posts, usage analytics, narrative arcs (all statuses) |
| **Arc Management** | `POST /api/projects/{id}/arcs` (body: `{theme, notes?}`), `PUT /api/projects/{id}/arcs/{arc_id}` (body: `{status?, notes?}`) | Create arc (max 3 active enforced), update status/notes. Resume (status=active) enforces max-3 check |
| **Commit Importing** | `GET /api/projects/{id}/decision-branches`, `GET /api/projects/{id}/import-preview` (param: `branch`), `POST /api/projects/{id}/import-commits` (body: `{branch?}`) | List distinct branches on decisions, preview importable commits, import historical commits as `imported` decisions |
| **Drafting** | `POST /api/decisions/{id}/create-draft`, `POST /api/decisions/consolidate` | Decision override drafting (real LLM drafter, optional platform filter). Both return `202 Accepted` with `{task_id, status}` — see [Background Tasks](#background-tasks) |
| **Background Tasks** | `GET /api/tasks` | Query background task status by type/ref_id/project_id/status. Used by frontend to restore spinners on page refresh |
| **Decision Management** | `DELETE /api/decisions/{id}`, `POST /api/decisions/{id}/retrigger`, `POST /api/decisions/{id}/rewind` | Cascading delete, re-evaluate from scratch, rewind to evaluation point (keep decision, delete downstream, auto-snapshot `_pre_rewind`) |
| **Platforms** | `GET /api/platforms/enabled` | Returns all enabled platforms with priority and type |
| **Filesystem** | `GET /api/filesystem/browse` (param: `path`) | Server-side directory browser for project registration folder picker. Restricted to `$HOME` subtree (local-mode only) |
| **Project Registration** | `POST /api/projects/register` (body: `{path}`), `DELETE /api/projects/{id}` | Register project from web UI (shared `register_project()`) and unregister with git hook cleanup |
| **Git Hook Mgmt** | `GET /api/projects/{id}/git-hook/status`, `POST /api/projects/{id}/git-hook/install`, `POST /api/projects/{id}/git-hook/uninstall` | Per-project git post-commit hook status, install, and uninstall |
| **OAuth** | `GET /api/oauth/x/authorize`, `GET /api/oauth/x/callback`, `GET /api/oauth/x/status` | X OAuth 2.0 PKCE flow: initiate authorization, handle callback (exchange code for tokens, save to DB), check connection status + username |
| **Content Creation** | `POST /api/projects/{id}/create-content` | Operator-initiated content: bypasses evaluator, constructs DraftingIntent directly. Returns 202 with task_id |
| **Advisory** | `GET /api/advisory` (params: `project_id`, `status`), `GET /api/advisory/count`, `GET /api/projects/{id}/advisory`, `POST /api/projects/{id}/advisory`, `PUT /api/advisory/{id}`, `DELETE /api/advisory/{id}` | Advisory items CRUD: operator action items for manual tasks (e.g. article posting) |
| **Project Context** | `POST /api/projects/{id}/upload-docs`, `GET/PUT /api/projects/{id}/prompt-docs` | Upload documentation files and manage the prompt_docs inclusion list for project context enrichment |

#### Security Model

- **CORS**: Only `localhost` and `127.0.0.1` origins allowed (regex-based)
- **API key masking**: `GET /api/settings/env` returns keys as `"****abcd"` (last 4 chars)
- **Env key allowlist**: `PUT /api/settings/env` rejects keys not in `KNOWN_KEYS` from `config/env.py`
- **Inline credentials**: Feature-specific API keys are managed in their feature's settings section (Channels, Platforms, Media Generation), not in a centralized API Keys page. `KEY_GROUPS` in `config/env.py` only contains cross-cutting groups (Core, LLM Providers).
- **Value sanitization**: Newlines and control characters stripped from env values
- **Path traversal protection**: `GET /api/media/{path}` resolves and verifies the path is under `media-cache/`
- **Config validation**: `PUT /api/settings/config` uses `save_config()` from `config/yaml.py` (shared with CLI) — runs `validate_config()` before writing
- **Memory endpoints**: `GET/POST/DELETE /api/settings/memories` + `POST /api/settings/memories/clear` — per-project voice memory CRUD

#### WebAdapter Integration

Bot interaction endpoints construct abstract types and call the same handlers as Telegram:

```
Web JSON body  -->  InboundMessage(chat_id="web", text=body.text)  -->  handle_command()
                                                                          |
                                                                          v
                                                                    WebAdapter writes to web_events
                                                                          |
                                                                          v
                                                                    API returns new events as JSON
```

The `_event_bridge_loop` polls `web_events` and pushes new entries to connected WebSocket clients via `GatewayHub.broadcast()`. Data change events (`data_change` type) trigger automatic page refreshes in the frontend via the `useDataEvents` hook.

**LLM calls in bot handlers:** All bot handler LLM calls (Gatekeeper, Expert, media spec) run via `_run_background_task`. The web layer dispatches to background tasks: `/api/message` always returns 202 (Gatekeeper on every message), `/api/callback` returns 202 for LLM actions (`media_gen_spec`), and WebSocket `send_message` sends a deferred ack with `task_id`. Bot handlers accept optional `task_id` for stage tracking (`emit_task_stage`). Telegram daemon calls remain synchronous (no task_id). Results arrive via WebSocket gateway events.

#### Background Tasks

> **Convention:** All LLM calls — whether from REST endpoints or bot handlers — MUST use background tasks. See CODING_PRACTICES §Web API Conventions.

Long-running LLM operations (draft creation, consolidation, spec generation) run in background threads to avoid Next.js proxy timeouts (~30s). The pattern:

1. **API endpoint** validates inputs synchronously, then calls `_run_background_task()` which inserts a row into `background_tasks` (status=`running`), spawns a daemon thread, and returns immediately with `202 Accepted` + `{task_id, status: "processing"}`.
2. **Worker thread** runs the blocking operation. On completion, updates the row (status=`completed`, result=JSON). On failure, sets status=`failed` + error message. Emits `task` data_change events via `emit_data_event()` in both cases.
3. **`on_success` callback** (optional) runs after the task row is marked completed — used for side effects like `notify_draft_review()` which sends Telegram/web notifications for newly created drafts.

**Frontend integration** uses the `useBackgroundTasks` hook (`web/src/lib/use-background-tasks.ts`):
- On page load, queries `GET /api/tasks?project_id=X&status=running` to restore spinners for in-progress tasks (survives page refresh).
- Listens for `task` data_change events via WebSocket to detect completion/failure.
- Fires an `onTaskCompleted` callback so the page can update local state (draft counts, result messages).
- `trackTask(taskId, refId, type)` registers a newly-created task for tracking.

**Database schema** (`background_tasks` table):
```sql
id TEXT PRIMARY KEY, type TEXT, ref_id TEXT, project_id TEXT,
status TEXT ('running'|'completed'|'failed'), result TEXT (JSON), error TEXT,
created_at TEXT, updated_at TEXT
```

The CLI is unaffected — it calls `draft()` directly (synchronous, in-process).

**Startup recovery**: On server start, `_cleanup_stale_tasks()` marks all `running` tasks as `failed` with error "Interrupted by server restart". Since worker threads are daemon threads, they cannot survive a process restart. No data events are emitted (no clients connected yet).

**Periodic TTL expiration**: The `_event_bridge_loop` checks every ~30 seconds for tasks running longer than 10 minutes (`_STALE_TASK_TIMEOUT_SECONDS`). These are marked `failed` with a timeout error and `data_change` events are emitted so connected frontends clear spinners immediately via the existing `useBackgroundTasks` WebSocket listener.

#### Frontend UI Components

**Elapsed timer system** (`web/src/components/async-button.tsx`):
- `<ElapsedTime startTime={iso}>` — self-updating counter ("5s", "1m 23s"). Uses `tabular-nums` to prevent layout shift. Auto-cleans interval on unmount. Returns null for <1s elapsed.
- `<Spinner>` — inline SVG spinner matching the existing codebase pattern.
- `<AsyncButton>` — drop-in button wrapping both. Accepts `loading`, `startTime`, `loadingText`, standard button props.

Buttons using background tasks get their `startTime` from `getTask(refId)?.created_at` (persisted in DB, survives page refresh). Buttons using direct LLM calls track a local `useState` timestamp set on click. Quick operations (save, delete, toggle) do not use timers.

**Top banner** (`web/src/components/top-banner.tsx`):
- Reusable fixed top-center notification with slide-in/fade-out animation.
- Parent-controlled: `visible`, `onDismiss`, `children`. Optional `onDismissForever` renders an inline permanent dismiss link.
- `<SlowTaskBanner>` (`web/src/components/slow-task-banner.tsx`) is a self-contained consumer: checks config for `claude-cli/*` models on mount, listens for `task` data_change events via WebSocket, shows banner after 13s of uninterrupted task runtime. Escalating dismiss persisted in localStorage (`slow-task-banner` key).

---

## File System Layout

### Central Location

```
~/.social-hook/
├── social-hook.db          # SQLite database (all queryable state)
├── .env                    # Credentials (X_API_KEY, TELEGRAM_BOT_TOKEN, etc.)
├── migrations/             # Schema migration files
│   ├── 001_initial.sql
│   └── ...
├── snapshots/              # DB snapshots (social-hook snapshot save/restore)
│   └── {name}.db
├── media-cache/            # Generated media assets (temporary)
│   └── {project_id}/
│       └── {hash}.png
└── narratives/             # Development journey narratives
    └── {project_id}.jsonl
```

#### Snapshot CLI (`social-hook snapshot`)

Manages named DB snapshots at `~/.social-hook/snapshots/`. Implementation: `src/social_hook/cli/snapshot.py`.

- **save**: Copies `social-hook.db` → `snapshots/{name}.db`. Validates name (`^[a-zA-Z0-9_-]+$`, max 64 chars). Prompts if exists (skip with `--yes`).
- **restore**: Backs up current DB as `_pre_restore.db`. Validates snapshot is valid SQLite (integrity check). Copies `snapshots/{name}.db` → `social-hook.db`.
- **reset**: Backs up as `_pre_reset.db`. Deletes DB and creates fresh via `init_database()`.
- **list**: Scans `snapshots/*.db`, excludes `_`-prefixed internal backups. Shows name, size, mtime.
- **delete**: Removes `snapshots/{name}.db` with confirmation.

Internal backups (`_pre_restore.db`, `_pre_reset.db`) are excluded from list output. All destructive commands accept `--yes`/`-y`. All commands support `--json` output.

### Configuration Inheritance

Config files follow a project → global fallback pattern:

```
Lookup order:
┌─────────────────────────────────────────────────────────────┐
│ 1. {repo}/.social-hook/{file}    ← Project-specific         │
│ 2. ~/.social-hook/{file}         ← Global default           │
│ 3. None / {}                     ← Graceful degradation     │
└─────────────────────────────────────────────────────────────┘

Applies to: social-context.md, content-config.yaml
Exception:  memories.md (project-only, no fallback)
```

#### Global Configuration (~/.social-hook/)

```
~/.social-hook/
├── .env                    # API credentials (required)
├── config.yaml             # System config (models, scheduling)
├── social-context.md       # Default voice/style for all projects
├── content-config.yaml     # Default platform/posting settings
├── social-hook.db          # SQLite database
├── logs/                   # Application logs
│   └── git-hook.log        # Git post-commit hook output
├── media-cache/            # Generated images
├── narratives/             # Development journey narratives (JSONL per project)
└── prompts/                # Custom prompts (future)
```

### Config Split

Configuration is split between two files with distinct purposes:

| File | Purpose | Scope |
|------|---------|-------|
| `config.yaml` | Infrastructure: models, scheduling, platforms, media tools (on/off), channels | Global only (`~/.social-hook/config.yaml`) |
| `content-config.yaml` | Content guidance: media tool guidance (use_when, constraints, prompt examples), narrative strategy, context limits | Global + per-project override |

All opinionated media tool guidance (use_when, constraints, prompt_example) lives in `content-config.yaml`, not in Python code. The `DEFAULT_MEDIA_GUIDANCE` constant in `project.py` is structural only — it ensures all 4 tool slots exist but contains no opinionated content. See `docs/templates/content-config.example.yaml` for recommended starting guidance.

The web dashboard exposes both:
- `config.yaml` is edited via structured UI sections (Models, Scheduling, Platforms, Media Generation toggles, Channels)
- `content-config.yaml` can be edited as raw YAML (Settings > Content Config) or via structured UI (Settings > Media Generation per-project guidance). Both use the parsed API (`/api/settings/content-config/parsed`) for structured updates

### Per-Project Configuration ({repo}/.social-hook/)

```
{project_root}/
└── .social-hook/
    ├── social-context.md       # Project-specific voice (overrides global)
    ├── content-config.yaml     # Project-specific settings (overrides global)
    └── memories.md             # Accumulated feedback (project-only)
```

### Credential Requirements

Keys in `~/.social-hook/.env` (required keys depend on chosen providers):

```bash
# LLM providers (at least one required, depending on config)
ANTHROPIC_API_KEY=...      # Required for anthropic/ provider
OPENAI_API_KEY=...         # Required for openai/ provider
OPENROUTER_API_KEY=...     # Required for openrouter/ provider
# claude-cli/ and ollama/ providers need no API keys

X_API_KEY=...              # X (Twitter) API credentials
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_TOKEN_SECRET=...
TELEGRAM_BOT_TOKEN=...     # Telegram bot token
GEMINI_API_KEY=...         # Nano Banana Pro (Google Gemini API)
```

System refuses to start if credentials for configured providers are missing.

---

## Domain Models Package

Models are organized in domain-focused submodules under `src/social_hook/models/`. Import directly from the specific submodule — `__init__.py` is empty (no re-exports).

```
models/
    __init__.py      — Docstring only (package marker)
    _helpers.py      — Shared datetime serialization (_to_iso, _from_iso)
    enums.py         — All enums (DraftStatus, DecisionType, PipelineStage, etc.),
                       status group frozensets (TERMINAL_STATUSES, etc.),
                       helper predicates (is_draftable, is_held)
    core.py          — Project, Decision, Draft, DraftPart, DraftChange, Post, CommitInfo
    narrative.py     — Lifecycle, Arc, NarrativeDebt
    content.py       — ContentTopic, ContentSuggestion, EvaluationCycle, DraftPattern
    infra.py         — OAuthToken, UsageLog, SystemErrorRecord
    context.py       — ProjectContext (TYPE_CHECKING imports for forward refs)
```

**Dependency DAG (zero cycles):**
- `_helpers.py` ← `core.py`, `narrative.py`, `infra.py`
- `enums.py` ← `core.py`, `narrative.py`, `content.py`
- `parsing.py` ← `core.py`, `narrative.py`, `content.py` (external, no reverse dep)
- `core.py`, `narrative.py` ← `context.py` (TYPE_CHECKING only — no runtime dependency)

**Import convention:** `from social_hook.models.core import Project, Decision` — never `from social_hook.models import`.

## Database Schema

### Initialization

```sql
-- Enable WAL mode for concurrent access (multiple worktrees)
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```

### Schema Version Tracking

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);
```

### Projects

```sql
CREATE TABLE IF NOT EXISTS projects (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    repo_path             TEXT NOT NULL,           -- Absolute path to repo/worktree
    repo_origin           TEXT,                    -- Git remote URL (for worktree grouping)
    summary               TEXT,                    -- ~500 token summary for cross-project coordination
    summary_updated_at    TEXT,                    -- ISO 8601 timestamp
    audience_introduced   INTEGER NOT NULL DEFAULT 0,  -- Boolean: has intro arc completed?
    paused                INTEGER NOT NULL DEFAULT 0,  -- Boolean: temporarily stop processing commits
    discovery_files       TEXT DEFAULT NULL,       -- JSON array of files used in two-pass discovery
    trigger_branch        TEXT DEFAULT NULL,        -- Branch filter (NULL = all branches)
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_origin ON projects(repo_origin);
```

### Decisions

```sql
CREATE TABLE IF NOT EXISTS decisions (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id),
    commit_hash   TEXT NOT NULL,
    commit_message TEXT,                          -- Preserves readability if history is rewritten
    decision      TEXT NOT NULL CHECK (decision IN ('post_worthy', 'not_post_worthy', 'consolidate', 'deferred', 'imported')),
    branch        TEXT,                            -- Git branch name at commit time (migration 016)
    reasoning     TEXT NOT NULL,
    angle         TEXT,                           -- Content angle (nullable)
    episode_type  TEXT CHECK (episode_type IN ('decision', 'before_after', 'demo_proof', 'milestone', 'postmortem', 'launch', 'synthesis')),
    post_category TEXT CHECK (post_category IN ('arc', 'opportunistic', 'experiment')),
    arc_id        TEXT REFERENCES arcs(id),       -- Nullable: only if post belongs to an arc
    media_tool    TEXT,                           -- Tool used: 'mermaid', 'nano_banana_pro', 'playwright', 'ray_so'
    platforms     TEXT NOT NULL DEFAULT '{}',     -- JSON object: {"x": "drafted", "linkedin": "skipped:reason"}
    commit_summary TEXT,                          -- Brief summary for consolidation batching (v9)
    processed     INTEGER NOT NULL DEFAULT 0,     -- Whether consolidation processor has handled this (v9)
    processed_at  TEXT,                           -- When consolidation processor handled this (v9)
    batch_id      TEXT,                           -- Consolidation batch ID for grouping (v9)
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(project_id, commit_hash)               -- Prevent duplicate decisions per commit
);

CREATE INDEX IF NOT EXISTS idx_decisions_project_time ON decisions(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_commit ON decisions(project_id, commit_hash);
CREATE INDEX IF NOT EXISTS idx_decisions_arc ON decisions(arc_id) WHERE arc_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_decisions_unprocessed ON decisions(project_id, created_at)
    WHERE decision IN ('consolidate', 'deferred') AND processed = 0;
```

**Platform Status Values:** The `platforms` JSON object tracks per-platform status:
- `drafted` - Draft created for this platform
- `skipped:<reason>` - Not posting (e.g., `skipped:not_significant_milestone`)
- `scheduled` - Scheduled for posting
- `posted` - Successfully posted
- `failed` - Posting failed

### Drafts

```sql
CREATE TABLE IF NOT EXISTS drafts (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    decision_id     TEXT NOT NULL REFERENCES decisions(id),
    platform        TEXT NOT NULL,                -- 'x', 'linkedin', etc.
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'scheduled', 'posted', 'rejected', 'failed', 'superseded', 'cancelled', 'deferred')),
    content         TEXT NOT NULL,                -- Post content text
    media_paths     TEXT NOT NULL DEFAULT '[]',   -- JSON array of file paths
    media_type      TEXT,                         -- Media tool used: 'mermaid', 'ray_so', etc.
    media_spec      TEXT DEFAULT '{}',            -- JSON: tool-specific media spec from drafter
    media_spec_used TEXT,                         -- JSON: actual spec used for generation
    suggested_time  TEXT,                         -- ISO 8601 suggested posting time
    scheduled_time  TEXT,                         -- ISO 8601 confirmed scheduled time
    reasoning       TEXT,                         -- Why this content/angle was chosen
    superseded_by   TEXT REFERENCES drafts(id),   -- FK to replacing draft (audit trail)
    retry_count     INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    is_intro        INTEGER NOT NULL DEFAULT 0,   -- Whether this is an audience introduction draft
    vehicle         TEXT NOT NULL DEFAULT 'single' CHECK (vehicle IN ('single', 'thread', 'article')),
    reference_type  TEXT DEFAULT NULL CHECK (reference_type IN ('quote', 'reply')),
    reference_files TEXT DEFAULT NULL,            -- JSON array of per-draft reference file paths
    reference_post_id TEXT DEFAULT NULL REFERENCES posts(id),
    target_id       TEXT,                         -- Target name (e.g. "lead-timeline")
    evaluation_cycle_id TEXT,                     -- Links to evaluation_cycles
    topic_id        TEXT,                         -- Links to content_topics
    suggestion_id   TEXT,                         -- Links to content_suggestions
    pattern_id      TEXT,                         -- Links to draft_patterns
    preview_mode    INTEGER NOT NULL DEFAULT 0,   -- Draft for accountless target (no posting)
    arc_id          TEXT,                         -- Arc association for arc continuations
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(project_id, status);
CREATE INDEX IF NOT EXISTS idx_drafts_scheduled ON drafts(status, scheduled_time) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_drafts_intro ON drafts(project_id) WHERE is_intro = 1;
CREATE INDEX IF NOT EXISTS idx_drafts_reference_post ON drafts(reference_post_id) WHERE reference_post_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_target ON drafts(target_id) WHERE target_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_topic_id ON drafts(topic_id) WHERE topic_id IS NOT NULL;
```

### Draft Parts (Thread Support)

```sql
CREATE TABLE IF NOT EXISTS draft_parts (
    id          TEXT PRIMARY KEY,
    draft_id    TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,                 -- 0-indexed position in thread
    content     TEXT NOT NULL,                    -- Individual part text
    media_paths TEXT NOT NULL DEFAULT '[]',       -- JSON array of media for this part
    external_id TEXT,                             -- Platform post ID after posting
    posted_at   TEXT,                             -- When this part was posted
    error       TEXT,                             -- Error message if posting failed

    UNIQUE(draft_id, position)
);

CREATE INDEX IF NOT EXISTS idx_draft_parts_draft ON draft_parts(draft_id, position);
CREATE INDEX IF NOT EXISTS idx_draft_parts_external ON draft_parts(external_id) WHERE external_id IS NOT NULL;
```

### Draft Changes (Audit Trail)

```sql
CREATE TABLE IF NOT EXISTS draft_changes (
    id          TEXT PRIMARY KEY,
    draft_id    TEXT NOT NULL REFERENCES drafts(id),
    field       TEXT NOT NULL,                    -- 'content', 'scheduled_time', 'media_paths', etc.
    old_value   TEXT,
    new_value   TEXT,
    changed_by  TEXT NOT NULL CHECK (changed_by IN ('gatekeeper', 'human', 'expert')),
    changed_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_draft_changes_draft ON draft_changes(draft_id, changed_at DESC);
```

### Posts (Published Content)

```sql
CREATE TABLE IF NOT EXISTS posts (
    id           TEXT PRIMARY KEY,
    draft_id     TEXT NOT NULL REFERENCES drafts(id),
    project_id   TEXT NOT NULL REFERENCES projects(id),
    platform     TEXT NOT NULL,
    external_id  TEXT,                            -- Platform's post ID
    external_url TEXT,                            -- URL to the post
    content      TEXT NOT NULL,                   -- Final posted content
    posted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_posts_project_time ON posts(project_id, posted_at DESC);
```

### Lifecycles

```sql
CREATE TABLE IF NOT EXISTS lifecycles (
    project_id            TEXT PRIMARY KEY REFERENCES projects(id),
    phase                 TEXT NOT NULL DEFAULT 'research' CHECK (phase IN ('research', 'build', 'demo', 'launch', 'post_launch')),
    confidence            REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evidence              TEXT NOT NULL DEFAULT '[]',  -- JSON array of evidence strings
    last_strategy_moment  TEXT,                        -- ISO 8601 timestamp
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Arcs (Narrative Threads)

```sql
CREATE TABLE IF NOT EXISTS arcs (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id),
    theme        TEXT NOT NULL,                   -- e.g., "Building the content brain"
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'abandoned')),
    post_count   INTEGER NOT NULL DEFAULT 0,
    last_post_at TEXT,                            -- For stagnation detection
    notes        TEXT,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at     TEXT,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_arcs_project_status ON arcs(project_id, status);
```

### Narrative Debt

```sql
CREATE TABLE IF NOT EXISTS narrative_debt (
    project_id        TEXT PRIMARY KEY REFERENCES projects(id),
    debt_counter      INTEGER NOT NULL DEFAULT 0,
    last_synthesis_at TEXT                        -- ISO 8601 timestamp of last synthesis post
);
```

### Usage Log (Token Tracking)

```sql
CREATE TABLE IF NOT EXISTS usage_log (
    id                    TEXT PRIMARY KEY,
    project_id            TEXT REFERENCES projects(id),  -- Nullable for cross-project operations
    operation_type        TEXT NOT NULL,                 -- 'evaluation', 'draft_creation', 'conversation', 'coordination'
    model                 TEXT NOT NULL,                 -- Short name: 'haiku', 'sonnet', 'opus' (not full model ID)
    input_tokens          INTEGER NOT NULL DEFAULT 0,
    output_tokens         INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens     INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cost_cents            REAL NOT NULL DEFAULT 0.0,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_usage_project_time ON usage_log(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_time ON usage_log(created_at DESC);
```

**API Field Mapping:** The database column names are shortened for readability. Map from API response:

| API Response Field | Database Column |
|--------------------|-----------------|
| `response.usage.input_tokens` | `input_tokens` |
| `response.usage.output_tokens` | `output_tokens` |
| `response.usage.cache_read_input_tokens` | `cache_read_tokens` |
| `response.usage.cache_creation_input_tokens` | `cache_creation_tokens` |

---

## Schema Design Decisions

### JSON vs Normalized

| Field Type | Approach | Rationale |
|------------|----------|-----------|
| Status enums | TEXT with CHECK constraint | SQLite-idiomatic, enforced at DB level |
| Timestamps | TEXT (ISO 8601) | Human-readable, sortable, no timezone issues |
| Simple lists (media_paths, evidence) | JSON array | Rarely queried individually, simplifies schema |
| Complex objects (platforms dict) | JSON object | Flexible structure, platform-specific details vary |

### Timezone Handling

All timestamps in the database are stored in **UTC**:
- `created_at`, `updated_at`, `posted_at`: UTC
- `scheduled_time`, `suggested_time`: UTC

The scheduler converts between UTC and the user's configured timezone (`content-config.yaml` → `platforms.x.scheduling.timezone`) when:
- **Storing**: User says "post at 3pm" → convert to UTC → store
- **Displaying**: Read from DB → convert to local → show in Telegram
- **Executing**: Scheduler compares current UTC time to stored UTC time

### Indexing Strategy

| Index | Purpose | Query Pattern |
|-------|---------|---------------|
| `idx_decisions_project_time` | Recent decisions | `get_recent_decisions(project_id, limit)` |
| `idx_decisions_commit` | Deduplication | Check if commit already processed |
| `idx_drafts_status` | Pending drafts | `get_pending_drafts(project_id)` |
| `idx_drafts_scheduled` | Scheduler pickup | Find drafts ready to post (partial index) |
| `idx_posts_project_time` | Recent posts (scheduling) | `get_recent_posts(project_id, days)` |
| `idx_arcs_project_status` | Active arcs | `get_active_arcs(project_id)` |
| `idx_projects_origin` | Worktree grouping | Find projects with same remote |

### Concurrency (WAL Mode)

```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
```

- **WAL mode**: Enables concurrent reads during writes (important for multiple worktrees)
- **busy_timeout**: Wait up to 5 seconds for locks before failing (handles brief contention)
- Connection should set `PRAGMA foreign_keys = ON` on every open

### Migration Approach

1. `schema_version` table tracks applied migrations
2. Migration files stored in `~/.social-hook/migrations/`
3. Each migration is idempotent (uses `IF NOT EXISTS`)
4. Migrations run at startup if version behind

```python
def apply_migrations(db_path: str, migrations_dir: str):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Get current version
    current = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_version"
    ).fetchone()[0]

    # Apply pending migrations
    for migration_file in sorted(Path(migrations_dir).glob("*.sql")):
        version = int(migration_file.stem.split("_")[0])
        if version > current:
            sql = migration_file.read_text()
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (version, migration_file.stem)
            )

    conn.commit()
```

---

## Tool Call Implementation

### Project Registry

```python
# register_project(repo_path: str, name: str, repo_origin: str) → project_id
# Called when user opts in via Telegram
INSERT INTO projects (id, name, repo_path, repo_origin)
VALUES (?, ?, ?, ?)
RETURNING id;

# Also initialize lifecycle and narrative_debt for new project
INSERT INTO lifecycles (project_id) VALUES (?);
INSERT INTO narrative_debt (project_id) VALUES (?);

# get_project(project_id: str) → Project
SELECT * FROM projects WHERE id = ?;

# get_all_projects() → list[Project]
SELECT * FROM projects ORDER BY created_at DESC;

# get_project_summary(project_id: str) → Optional[str]
# Returns summary text or None. Used for Gatekeeper context injection.
SELECT summary FROM projects WHERE id = ?;

# update_project_summary(project_id: str, summary: str) → bool
# Called by Evaluator when summary is stale. Updates text and timestamp.
UPDATE projects
SET summary = ?, summary_updated_at = datetime('now')
WHERE id = ?;

# get_summary_freshness(project_id: str) → dict
# Returns: { summary_updated_at, commits_since_summary, days_since_summary }
# Used by Evaluator to decide whether to refresh.
SELECT summary_updated_at,
       (SELECT COUNT(*) FROM decisions
        WHERE project_id = ? AND created_at >= COALESCE(p.summary_updated_at, '1970-01-01'))
FROM projects p WHERE id = ?;

# Find projects with same origin (worktree identification)
SELECT * FROM projects WHERE repo_origin = ?;
```

### Decision Log

```python
# log_decision(...) → decision_id
INSERT INTO decisions (
    id, project_id, commit_hash, commit_message, decision, reasoning,
    angle, episode_type, post_category, arc_id, media_tool, platforms
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, json(?))
RETURNING id;

# get_recent_decisions(project_id: str, limit: int = 30) → list[Decision]
SELECT * FROM decisions
WHERE project_id = ?
ORDER BY created_at DESC
LIMIT ?;

# Check for duplicate commit processing
SELECT 1 FROM decisions WHERE project_id = ? AND commit_hash = ?;
```

### Posts & Drafts

```python
# get_recent_posts(project_id: str, days: int = 7) → list[Post]
SELECT * FROM posts
WHERE project_id = ?
  AND posted_at >= datetime('now', '-' || ? || ' days')
ORDER BY posted_at DESC;

# get_recent_posts_for_context(project_id: str, limit: int = 15) → list[Post]
# Use case: Context assembly - last N posts for LLM prompt
SELECT * FROM posts
WHERE project_id = ?
ORDER BY posted_at DESC
LIMIT ?;

# get_recent_posts_all(days: int = 7) → list[Post]
SELECT p.*, pr.name as project_name
FROM posts p
JOIN projects pr ON p.project_id = pr.id
WHERE p.posted_at >= datetime('now', '-' || ? || ' days')
ORDER BY p.posted_at DESC;

# get_pending_drafts(project_id: str) → list[Draft]
SELECT * FROM drafts
WHERE project_id = ?
  AND status IN ('draft', 'approved', 'scheduled')
ORDER BY created_at DESC;

# get_all_pending_drafts() → list[Draft]
SELECT d.*, p.name as project_name
FROM drafts d
JOIN projects p ON d.project_id = p.id
WHERE d.status IN ('draft', 'approved', 'scheduled')
ORDER BY d.created_at DESC;

# save_draft(...) → draft_id
# For single posts:
INSERT INTO drafts (
    id, project_id, decision_id, platform, content,
    media_paths, suggested_time, reasoning
) VALUES (?, ?, ?, ?, ?, json(?), ?, ?)
RETURNING id;

# For threads (content is full text, parts stored separately):
# 1. Insert parent draft with content text
# 2. Insert individual parts
BEGIN TRANSACTION;

INSERT INTO drafts (
    id, project_id, decision_id, platform, content, vehicle,
    media_paths, suggested_time, reasoning
) VALUES (?, ?, ?, ?, ?, 'thread', '[]', ?, ?);

-- For each part in thread:
INSERT INTO draft_parts (id, draft_id, position, content, media_paths)
VALUES (?, ?, ?, ?, json(?));

COMMIT;

# update_draft(draft_id: str, changes: dict) → bool
UPDATE drafts
SET
    status = COALESCE(?, status),
    content = COALESCE(?, content),
    scheduled_time = COALESCE(?, scheduled_time),
    updated_at = datetime('now')
WHERE id = ?;

# Record the change for audit
INSERT INTO draft_changes (id, draft_id, field, old_value, new_value, changed_by)
VALUES (?, ?, ?, ?, ?, ?);

# get_draft_changes(draft_id: str) → list[Change]
SELECT * FROM draft_changes
WHERE draft_id = ?
ORDER BY changed_at DESC;

# Get parts for a thread draft
SELECT * FROM draft_parts
WHERE draft_id = ?
ORDER BY position ASC;

# supersede_draft(old_draft_id: str, new_draft_id: str)
UPDATE drafts
SET status = 'superseded', superseded_by = ?, updated_at = datetime('now')
WHERE id = ?;
```

**Thread Content Storage:** For threads, content is stored in TWO places:
- `drafts.content`: Full text for display/audit (what was planned)
- `draft_parts`: Normalized rows for posting mechanics (authoritative for execution)

**Synchronization Rules:**
- `draft_parts` is the **single source of truth** for posting
- `drafts.content` is a **read-only audit snapshot** of original plan
- All edits (via Gatekeeper/Telegram) MUST update `draft_parts` only
- On read for display, always query `draft_parts` to show current state
- `drafts.content` is never modified after initial creation

```python
# CORRECT: Edit updates draft_parts only
def update_draft_part(draft_id: str, position: int, new_content: str):
    UPDATE draft_parts
    SET content = ?
    WHERE draft_id = ? AND position = ?;
    # Note: Changes are tracked via draft_changes table, not updated_at

# CORRECT: Display reads from draft_parts (current state)
def get_parts_for_display(draft_id: str):
    SELECT position, content, media_paths FROM draft_parts
    WHERE draft_id = ? ORDER BY position;

# drafts.content preserves original for audit trail only
```

### Lifecycle Management

```python
# get_lifecycle(project_id: str) → Lifecycle
SELECT * FROM lifecycles WHERE project_id = ?;

# update_lifecycle(project_id, phase, confidence, evidence)
INSERT INTO lifecycles (project_id, phase, confidence, evidence, updated_at)
VALUES (?, ?, ?, json(?), datetime('now'))
ON CONFLICT(project_id) DO UPDATE SET
    phase = excluded.phase,
    confidence = excluded.confidence,
    evidence = excluded.evidence,
    updated_at = excluded.updated_at;
```

### Arc Management

```python
# create_arc(project_id: str, theme: str) → arc_id
INSERT INTO arcs (id, project_id, theme)
VALUES (?, ?, ?)
RETURNING id;

# update_arc(arc_id, status, post_count, notes)
UPDATE arcs SET
    status = COALESCE(?, status),
    post_count = COALESCE(?, post_count),
    last_post_at = CASE WHEN ? IS NOT NULL THEN datetime('now') ELSE last_post_at END,
    notes = COALESCE(?, notes),
    ended_at = CASE WHEN ? IN ('completed', 'abandoned') THEN datetime('now') ELSE ended_at END,
    updated_at = datetime('now')
WHERE id = ?;

# get_active_arcs(project_id: str) → list[Arc]
SELECT * FROM arcs
WHERE project_id = ? AND status = 'active'
ORDER BY started_at DESC
LIMIT 3;

# get_arc_posts(arc_id: str) → list[Post]
# Use case: Drafter context assembly - previous posts in this arc for narrative continuity
# Traces: decisions (arc_id) → drafts → posts
SELECT p.* FROM posts p
JOIN drafts d ON p.draft_id = d.id
JOIN decisions dec ON d.decision_id = dec.id
WHERE dec.arc_id = ?
ORDER BY p.posted_at DESC;
```

### Narrative Debt

```python
# get_narrative_debt(project_id: str) → int
SELECT debt_counter FROM narrative_debt WHERE project_id = ?;

# increment_narrative_debt(project_id: str) → int
INSERT INTO narrative_debt (project_id, debt_counter)
VALUES (?, 1)
ON CONFLICT(project_id) DO UPDATE SET
    debt_counter = narrative_debt.debt_counter + 1
RETURNING debt_counter;

# reset_narrative_debt(project_id: str)
UPDATE narrative_debt
SET debt_counter = 0, last_synthesis_at = datetime('now')
WHERE project_id = ?;
```

### Strategy Triggers

```python
# check_strategy_triggers(project_id: str) → list[str]
# Returns list of triggered conditions

# Implementation: Multiple queries combined

triggers = []

# 1. Phase transition check
lifecycle = get_lifecycle(project_id)
# (Agent analyzes signals and checks if new phase confidence > 0.7)

# 2. Major artifact detection (LLM-driven)
# The Evaluator analyzes commit context (messages, file paths, tags) to identify
# first demo, deploy, release, or other major artifacts. This is a judgment call
# by the LLM, not pattern matching — the Evaluator sees the full commit context
# and decides whether it represents a significant project milestone.
# (If detected, add "major_artifact" to triggers)

# 3. Arc stagnation (no posts in 14 days)
SELECT id, theme FROM arcs
WHERE project_id = ?
  AND status = 'active'
  AND last_post_at < datetime('now', '-14 days')
# (If results, add "arc_stagnation" to triggers)

# 4. Narrative debt > threshold
SELECT debt_counter FROM narrative_debt WHERE project_id = ?;
# (If > config.strategy.narrative_debt_threshold, add "narrative_debt_high")

# 5. Time since last strategy moment
SELECT last_strategy_moment FROM lifecycles WHERE project_id = ?;
# (If > 7 days ago, add "time_elapsed")

# record_strategy_moment(project_id: str)
UPDATE lifecycles
SET last_strategy_moment = datetime('now')
WHERE project_id = ?;
```

### Onboarding

```python
# get_audience_introduced(project_id: str) → bool
SELECT audience_introduced FROM projects WHERE id = ?;

# set_audience_introduced(project_id: str, value: bool)
UPDATE projects
SET audience_introduced = ?
WHERE id = ?;
```

### memories.md File Format

The `memories.md` file stores human feedback for voice calibration. Located at `{project_root}/.social-hook/memories.md`.

**Schema:**
```markdown
# Voice Memories

| Date | Context | Feedback | Draft ID |
|------|---------|----------|----------|
| 2026-01-30 | Technical architecture | "Too many emojis" | draft-001 |
| 2026-01-31 | Launch announcement | "More energy needed" | draft-002 |
```

**Rules:**
- Maximum 100 entries (oldest removed on overflow)
- Date: YYYY-MM-DD format
- Context: Brief description of content type (e.g., "Technical architecture", "Bug fix", "Launch announcement")
- Feedback: Quoted human feedback text
- Draft ID: Reference to original draft for tracing

**CRUD Functions** (`config/project.py`):
- `save_memory(repo_path, context, feedback, draft_id)` — add entry, FIFO 100 max
- `list_memories(repo_path)` — list all entries, returns `[]` if no file
- `delete_memory(repo_path, index)` — delete by 0-based index
- `clear_memories(repo_path)` — clear all, returns count cleared

**Sanitization**: Pipe characters (`|`) in fields are replaced with Unicode box-drawing vertical (`│`) on write and reversed on read. Newlines are collapsed to spaces.

**Access**: Manageable via CLI (`social-hook memory list/add/delete/clear`) and web UI (project detail page > Voice Memories section). Web API endpoints at `/api/settings/memories`.

### context-notes.md File Format

The `context-notes.md` file stores strategic observations from the Expert agent (e.g., "wait for auth feature before posting about it"). Located at `{project_root}/.social-hook/context-notes.md`.

Distinct from `memories.md` (human feedback for voice calibration), context notes capture strategic guidance for future evaluations.

**Schema:**
```markdown
# Context Notes

| Date | Note | Source |
|------|------|--------|
| 2026-01-30 | Wait for auth feature before posting about security | expert:draft_001 |
| 2026-01-31 | User prefers casual tone for this project | expert:draft_002 |
```

**Rules:**
- Maximum 50 entries (oldest removed on overflow)
- Date: YYYY-MM-DD format
- Note: The context note text
- Source: Origin of the note (e.g., "expert:draft_123")

**Persistence functions:**
```python
def save_context_note(repo_path, note, source):
    """Save a context note from the Expert agent."""

def load_context_notes(repo_path) -> list[dict]:
    """Load context notes from project's context-notes.md."""
```

---

### Usage Tracking

```python
# log_usage(...)
INSERT INTO usage_log (
    id, project_id, operation_type, model,
    input_tokens, output_tokens,
    cache_read_tokens, cache_creation_tokens, cost_cents
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);

# get_usage_summary(days: int = 30)
SELECT
    model,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    SUM(cost_cents) as total_cost_cents
FROM usage_log
WHERE created_at >= datetime('now', '-' || ? || ' days')
GROUP BY model;
```

---

## State Lifecycles

### Draft Status Flow

```
                         ┌──────────────┐
                         │    draft     │ ← Initial state
                         └──────┬───────┘
                                │
       ┌────────────┬───────────┼───────────┬────────────┐
       ▼            ▼           ▼           ▼            ▼
┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│ approved  │ │ scheduled │ │ rejected  │ │superseded │
└─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └───────────┘
      │  ▲          │  ▲          │          (terminal)
      │  │          │  │          │
      │  └──────────┤  └──────────┤
      │  unapprove  │  unschedule │ reopen (non-intro only)
      │             │             ▼
┌─────┴─────┐ ┌─────┴─────────────┐     ┌──────────────┐
▼           ▼ ▼         ▼         ▼     │    draft     │
┌───────┐ ┌───────┐ ┌───────┐ ┌─────────┐ └──────────────┘
│posted │ │failed │ │posted │ │cancelled│───────┘ reopen
└───────┘ └───┬───┘ └───────┘ └─────────┘  (non-intro only)
(immediate)   │     (scheduled)
              │
       (retry with backoff,
        max 3 attempts,
        then alert human)


┌──────────────┐
│   deferred   │ ← Created when scheduling capacity exhausted
└──────┬───────┘
       │ promote_deferred_drafts() runs each scheduler tick
       │
  ┌────┴────┐
  ▼         ▼
┌─────────┐ ┌───────────┐
│scheduled│ │ cancelled │ ← platform disabled/removed
└─────────┘ └───────────┘

Three forward entry paths:
- "Approve Now" → approved → posted/failed (immediate)
- "Approve @ time" → scheduled → posted/failed/cancelled
- Weekly limit hit → deferred → scheduled (auto-promoted) or cancelled

Three reverse entry paths (back to draft):
- approved → draft (unapprove) — undoes approval without cancelling
- scheduled → draft (unschedule) — clears scheduled_time, reverts to draft
- cancelled/rejected → draft (reopen) — not available for intro drafts
  (intro rejection triggers on_intro_rejected cascade which is not reversible)
```

### Thread Posting (Atomic)

```
Start: draft_parts has N parts

For i = 0 to N-1:
    ├── Post part[i]
    ├── If success:
    │   ├── Record external_id in draft_parts[i]
    │   └── Continue to next part
    │
    └── If failure:
        ├── Record error in draft_parts[i]
        ├── Mark parent draft as 'failed'
        ├── Alert human
        └── Stop (don't post remaining parts)

All succeeded:
    ├── Mark parent draft as 'posted'
    └── Record post in posts table
```

### Arc Status

```
    ┌───────────┐
    │  active   │ ← Initial state
    └─────┬─────┘
          │
    ┌─────┴─────┐
    ▼           ▼
┌───────────┐ ┌───────────┐
│ completed │ │ abandoned │
└───────────┘ └───────────┘
```

- **completed**: Natural resolution (story told, feature shipped, etc.)
- **abandoned**: Project pivoted, arc no longer relevant (doesn't increase narrative debt)

### Lifecycle Phase Transitions

```
research ──► build ──► demo ──► launch ──► post_launch
   │           │         │         │           │
   └───────────┴─────────┴─────────┴───────────┘
            (confidence > 0.7 triggers transition)
```

Signals for each phase (from REQUIREMENTS.md):

| Phase | Signals |
|-------|---------|
| research | High file churn, new directories, prototype/ paths, few tests |
| build | Steady feature commits, test coverage growing, architecture stabilizing |
| demo | Demo scripts, UX polish, README updates, fewer breaking changes |
| launch | Release tags, CHANGELOG, deploy automation, version bumps |
| post_launch | Bugfix ratio increasing, perf optimization, iteration on existing |

---

## Platform Abstraction

### Platform Adapter Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

@dataclass
class PostResult:
    success: bool
    external_id: str | None = None
    external_url: str | None = None
    error: str | None = None
    part_results: list["PostResult"] | None = None  # per-part results for threads

class ReferenceType(Enum):
    """Type of cross-post reference."""
    REPLY = "reply"    # Reply to the referenced post
    QUOTE = "quote"    # Quote/reshare the referenced post
    LINK = "link"      # Embed the URL (universal fallback)

@dataclass
class PostReference:
    """Reference to an existing post on a platform."""
    external_id: str        # Platform-specific post ID
    external_url: str       # Public URL for LINK fallback
    reference_type: ReferenceType

class PlatformAdapter(ABC):
    """Abstract interface for social media platforms."""

    @abstractmethod
    def post(self, content: str, media_paths: list[str] | None = None,
             dry_run: bool = False) -> PostResult:
        """Post single content item."""
        pass

    @abstractmethod
    def post_thread(self, tweets: list[dict], dry_run: bool = False) -> PostResult:
        """Post a thread. Each dict has 'content' and 'media_paths'. Returns PostResult with part_results."""
        pass

    @abstractmethod
    def delete(self, external_id: str) -> bool:
        """Delete a post by its platform ID."""
        pass

    @abstractmethod
    def get_rate_limit_status(self) -> dict:
        """Return current rate limit status."""
        pass

    @abstractmethod
    def validate(self) -> tuple[bool, str]:
        """Validate credentials. Returns (success, username_or_error)."""
        pass

    def post_with_reference(self, content: str, reference: PostReference,
                            media_paths: list[str] | None = None,
                            dry_run: bool = False) -> PostResult:
        """Post content with a reference to an existing post.
        Default: LINK fallback (appends URL). Subclasses override for
        platform-native behaviors (quote tweets, reshares, etc.)."""
        if reference.external_url:
            content = f"{content}\n\n{reference.external_url}"
        return self.post(content, media_paths, dry_run)

    def supports_reference_type(self, ref_type: ReferenceType) -> bool:
        """Check if this platform supports a given reference type.
        Default: only LINK. Subclasses override to advertise native support."""
        return ref_type == ReferenceType.LINK
```

### X (Twitter) Implementation Notes

**X API v2 Tweet Creation:**

Endpoint: `POST https://api.x.com/2/tweets`

Request body for reply (thread chaining):
```json
{
  "text": "Tweet content",
  "reply": {
    "in_reply_to_tweet_id": "1346889436626259968"
  },
  "media": {
    "media_ids": ["1146654567674912769"]
  }
}
```

Request body for quote tweet:
```json
{
  "text": "Quote text",
  "quote_tweet_id": "1346889436626259968"
}
```

**Reference Support:**

`XAdapter` supports all three reference types natively:
- **QUOTE**: Uses `quote_tweet_id` field in the tweet creation body
- **REPLY**: Uses `reply.in_reply_to_tweet_id` field
- **LINK**: Appends the URL to the tweet text (universal fallback)

**Thread Posting Logic:**

```python
class XAdapter(PlatformAdapter):
    def post_thread(self, tweets: list[dict]) -> PostResult:
        results = []
        reply_to_id = None

        for tweet in tweets:
            # Build request body
            body = {"text": tweet['content']}

            # Add reply reference for thread chaining
            if reply_to_id:
                body["reply"] = {"in_reply_to_tweet_id": reply_to_id}

            # Add media if present
            if tweet.get('media_ids'):
                body["media"] = {"media_ids": tweet['media_ids']}

            result = self._post_tweet(body)
            results.append(result)

            if not result.success:
                # Atomic failure: stop and return
                return PostResult(
                    success=False,
                    part_results=results,
                    error=f"Tweet {len(results)} failed: {result.error}"
                )

            reply_to_id = result.external_id

        return PostResult(success=True, part_results=results)
```

### LinkedIn Implementation Notes

**Reference Support:**

`LinkedInAdapter` supports QUOTE and LINK reference types:
- **QUOTE**: Native reshare via LinkedIn REST API — only when the referenced post is a LinkedIn URN (`urn:li:share:...`). Cross-platform references fall back to LINK.
- **REPLY**: Not supported (falls back to LINK). LinkedIn Comments API excluded from this iteration.
- **LINK**: Appends the URL to the commentary text (universal fallback)

---

## Error Handling

### API Error Taxonomy

Different API errors require different responses. The system classifies errors and handles them accordingly:

```python
from enum import Enum

class ErrorType(Enum):
    RATE_LIMITED = "rate_limited"      # 429 - retry with backoff
    AUTH_EXPIRED = "auth_expired"      # 401, 403 - alert human, halt
    CONTENT_INVALID = "content_invalid" # 400 with content error - alert human for edit
    DUPLICATE = "duplicate"             # Content already posted - log and skip
    TRANSIENT = "transient"             # 500, 502, 503 - retry immediately
    UNKNOWN = "unknown"                 # Unexpected - log, alert human

def classify_error(response) -> ErrorType:
    """Classify API error for appropriate handling."""
    status = response.status_code
    body = response.json() if response.content else {}

    if status == 429:
        return ErrorType.RATE_LIMITED
    elif status in (401, 403):
        return ErrorType.AUTH_EXPIRED
    elif status == 400:
        # Check for specific content errors
        error_code = body.get('error', {}).get('code', '')
        if error_code in ('duplicate_content', 'status_duplicate'):
            return ErrorType.DUPLICATE
        elif error_code in ('invalid_text', 'text_too_long', 'invalid_media'):
            return ErrorType.CONTENT_INVALID
        return ErrorType.UNKNOWN
    elif status >= 500:
        return ErrorType.TRANSIENT
    else:
        return ErrorType.UNKNOWN

def handle_error(error_type: ErrorType, draft_id: str, context: dict):
    """Handle error based on classification."""
    match error_type:
        case ErrorType.RATE_LIMITED:
            schedule_retry_with_backoff(draft_id)
        case ErrorType.AUTH_EXPIRED:
            mark_draft_failed(draft_id, "auth_expired")
            alert_human("API authentication expired. Please re-authenticate.")
            halt_all_posting()  # Don't attempt more posts until fixed
        case ErrorType.CONTENT_INVALID:
            mark_draft_failed(draft_id, "content_invalid")
            alert_human(f"Content rejected by platform: {context.get('error_detail')}")
        case ErrorType.DUPLICATE:
            mark_draft_posted(draft_id, note="duplicate_skipped")
            log_info(f"Draft {draft_id} skipped - duplicate content")
        case ErrorType.TRANSIENT:
            schedule_immediate_retry(draft_id)
        case ErrorType.UNKNOWN:
            mark_draft_failed(draft_id, "unknown_error")
            alert_human(f"Unexpected error posting draft: {context}")
```

### Anthropic SDK Exception Handling

The Anthropic Python SDK provides typed exceptions with built-in retry - use these for Claude API errors:

```python
# Import from anthropic module (not anthropic.types) for catching exceptions
import anthropic

try:
    response = client.messages.create(...)
except anthropic.AuthenticationError:
    # Invalid API key (401/403)
    halt_all_posting()
    alert_human("API authentication failed")
except anthropic.RateLimitError:
    # 429 - SDK already retried (default 2x with backoff)
    mark_draft_failed(draft_id, "rate_limited_after_retries")
except anthropic.APIStatusError as e:
    # Other API errors
    log_error(f"API error {e.status_code}: {e.response}")
```

**SDK Built-in Retries:**
- Default: 2 automatic retries with exponential backoff
- Retries on: 429, 408, 409, >=500 errors
- Configure: `Anthropic(max_retries=N)` or `client.with_options(max_retries=N)`
- **Note:** Manual backoff logic is NOT needed for Claude API - the SDK handles it automatically

**Note:** The generic `classify_error()` above is for platform APIs (X, LinkedIn). For Claude API, use SDK exceptions.

### Platform-Specific Error Formats

#### X API v2 Error Format

X API v2 returns errors in a different format than the generic example above. The `classify_error()` function in WS1 is a placeholder that must be replaced with platform-specific classifiers in WS3.

**X API v2 error response structure:**

| Field | Purpose |
|-------|---------|
| `type` | URI identifying error type (e.g., `https://api.x.com/2/problems/resource-not-found`) |
| `title` | Short description |
| `detail` | Specific explanation |

**Example error response:**

```json
{
  "title": "Invalid Request",
  "detail": "The 'query' parameter is required.",
  "type": "https://api.x.com/2/problems/invalid-request"
}
```

**Partial success (HTTP 200 with some failures):**

```json
{
  "data": [...],
  "errors": [{"resource_id": "456", "title": "Not Found Error", "type": "..."}]
}
```

**WS3 must implement:**

```python
def classify_x_error(response) -> ErrorType:
    """Classify X API v2 error by parsing type URI."""
    body = response.json() if response.content else {}
    error_type = body.get("type", "")

    if "resource-not-found" in error_type:
        return ErrorType.UNKNOWN
    elif "invalid-request" in error_type:
        return ErrorType.CONTENT_INVALID
    elif "duplicate" in body.get("detail", "").lower():
        return ErrorType.DUPLICATE
    # ... etc
```

**Source:** [X API Response Codes](https://docs.x.com/x-api/fundamentals/response-codes-and-errors)

---

## Platform API Rate Limiting

> This section covers **platform-side** rate limit handling (X API, LinkedIn, etc.) — exponential backoff on 429 responses. For **pipeline-level** evaluation throttling (daily cap, gap timer), see [Pipeline Rate Limits](#pipeline-rate-limits).

### Per-API Limits

| API | Limit Type | Strategy |
|-----|------------|----------|
| Claude API | Tokens/minute | Track usage, queue if approaching limit |
| X API (Free) | 500 tweets/month, 50 tweets/day | Hard cap, queue excess |
| Telegram | 30 msgs/sec | Rarely hit, basic retry |
| Image Gen | Varies by service | Per-service config |

### Rate Limit Response Handling

**Platform-Specific Headers:**

| Platform | Header | Format |
|----------|--------|--------|
| X API | `x-rate-limit-reset` | Unix timestamp (seconds) |
| LinkedIn | `retry-after` | Seconds to wait |
| Generic | `retry-after` | Seconds to wait |

Exponential backoff with jitter is used as the fallback when platform-specific headers are absent. Backoff caps at 1 hour.

---

## Hook Configuration

Two hook types detect git commits. Both call `run_trigger()` with the same arguments.

### Git Post-Commit Hook (Primary)

Installed per-project via `social-hook project install-hook`. This is the recommended trigger for all users — it works with any editor or development environment.

#### Hook Script Template

```sh
# >>> social-hook post-commit hook >>>
# Installed by social-hook. Do not edit this block manually.
if [ "${SOCIAL_HOOK_SKIP:-0}" = "1" ]; then exit 0; fi
if [ -n "$CI" ] || [ -n "$GITHUB_ACTIONS" ] || [ -n "$JENKINS_URL" ] || \
   [ -n "$GITLAB_CI" ] || [ -n "$CIRCLECI" ] || [ -n "$TRAVIS" ]; then exit 0; fi
nohup social-hook git-hook > /dev/null 2>&1 &
# <<< social-hook post-commit hook <<<
```

#### Marker-Based Identification

The hook block is delimited by `# >>> social-hook post-commit hook >>>` and `# <<< social-hook post-commit hook <<<` markers. This enables:
- Safe uninstallation (only removes the marked block)
- Preservation of existing post-commit hooks (appends, doesn't overwrite)
- Detection of already-installed hooks (idempotent install)

#### `core.hooksPath` Support

When git is configured with `core.hooksPath` (used by tools like husky), the installer reads the configured path and installs the hook there instead of `.git/hooks/`.

#### Skip Mechanisms

- `SOCIAL_HOOK_SKIP=1` — environment variable to skip the hook (useful for batch operations)
- CI detection — checks `$CI`, `$GITHUB_ACTIONS`, `$JENKINS_URL`, `$GITLAB_CI`, `$CIRCLECI`, `$TRAVIS`

### Claude Code PostToolUse Hook (Secondary)

Located in `~/.claude/hooks.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": {
          "tool": "Bash",
          "command_pattern": "^git\\s+(commit|merge|rebase|cherry-pick)"
        },
        "action": {
          "type": "exec",
          "command": "social-hook trigger --commit $(git rev-parse HEAD) --repo $(pwd)"
        }
      }
    ]
  }
}
```

### What the Hooks Capture

- Commit hash (from `git rev-parse HEAD`)
- Repository path (from `pwd` or working directory)

### Mutual Exclusion

Only one commit detection method can be active at a time. `install_git_hook()` refuses if the Claude Code commit hook is installed, and `install_hook()` refuses if any project has a git hook installed. This prevents duplicate LLM evaluations from both hooks firing on the same commit. The web UI dims the inactive method and disables its install controls.

The DB UNIQUE constraint on `(project_id, commit_hash)` in the `decisions` table provides defense-in-depth deduplication — if both somehow fire, only the first is evaluated.

### Installation

- **Git hook**: `social-hook project install-hook [PATH]` — also installed automatically during `social-hook project register` (controlled by `--git-hook/--no-git-hook` flag, default: install)
- **Claude Code hook**: `social-hook install-hook` — creates/merges `~/.claude/hooks.json`

---

## Trigger Execution Model

**Architecture: No daemon. One-shot script.**

Two entry points, same pipeline:

```
Git post-commit hook:
  post-commit shell script
    -> social-hook git-hook (background via nohup)
      -> git rev-parse HEAD, pwd
      -> run_trigger(commit_hash, repo_path)
      -> Logs to ~/.social-hook/logs/git-hook.log

Claude Code PostToolUse hook:
  Hook fires (globally, any Claude Code session)
    -> social-hook trigger --commit abc123 --repo /path
      -> run_trigger(commit_hash, repo_path)
```

**Module structure** (decomposed from single file):
```
trigger.py              (~1050 lines) — Orchestrator: run_trigger(), _run_targets_path(), _run_trivial_skip()
trigger_git.py          (~200 lines)  — Git subprocess parsing: parse_commit_info(), git_remote_origin(), is_git_repo(), collect_git_stats()
trigger_context.py      (~120 lines)  — TriggerContext dataclass, build_platform_summaries(), fetch_evaluator_extras()
trigger_decisions.py    (~75 lines)   — Pure decision logic: _determine_overall_decision(), _is_trivial_classification()
trigger_side_effects.py (~220 lines)  — Brief updates, notifications, merge execution
trigger_batch.py        (~265 lines)  — evaluate_batch(), _run_commit_analyzer()
trigger_secondary.py    (~220 lines)  — run_summary_trigger(), run_suggestion_trigger()
vehicle.py              (~250 lines)  — Vehicle pipeline: resolve, validate, materialize, parse, post_by_vehicle
drafting_intents.py     (~280 lines)  — DraftingIntent builders: intent_from_routed_targets/platforms/decision/merge
file_reader.py          (~120 lines)  — Token-budgeted file reading with path traversal protection
```

All symbols are re-exported from `trigger.py` for backward compatibility. The canonical import path is always `from social_hook.trigger import ...`.

Shared `run_trigger()` flow:
```
run_trigger(commit_hash, repo_path)
  -> Script loads config, connects to SQLite
  -> Checks if repo is registered (exit 0 if not)
  -> Checks trigger_branch filter (exit 0 if mismatch)
  -> Rate limit gate (deferred_eval if blocked)
  -> Interval gate (_run_commit_analyzer_gate)
     -> Below threshold: create deferred_eval decision, exit 0 (QUEUED)
     -> At threshold: check for deferred commits
        -> If deferred exist: evaluate_batch() (combined diffs, all stages)
        -> If no deferred: single-commit stage 1 + 2
  -> Stage 1: CommitAnalyzer (classification, tags, topics) — emit ANALYZING
  -> Trivial check: skip trivial commits
  -> Stage 2: Evaluator (per-strategy decisions) — emit EVALUATING
  -> _run_targets_path() — returns TargetsPathResult(exit_code, cycle_id, decision_id):
     A. Cycle creation + batch membership marking
     B. Analysis enrichment
     C. Brief update (LLM)
     D. Topic matching + suggestions
     E. Decision creation — emit DECIDING
     F. Arc activation
     G-H. Queue actions
     I. Diagnostics
     J. Routing + Drafting — emit DRAFTING
     K. Notification
  -> Script exits
```

The `social-hook git-hook` command is hidden from `--help` output — it is only called by the post-commit hook script, not by users directly. It logs all output to `~/.social-hook/logs/git-hook.log` for debugging.

Both triggers fire on all git commits, but only registered projects are evaluated. Unregistered repos exit silently (no error, no API calls, no notifications). If a project has a `trigger_branch` set, only commits on that branch are processed; commits on other branches exit silently.

### Why No Daemon

- Each trigger is independent
- SQLite handles concurrent access (WAL mode)
- No queuing needed
- Simpler architecture

### Concurrent Triggers

- Two commits in quick succession = two parallel script instances
- SQLite WAL mode handles concurrent writes
- Each commit evaluated independently

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (post-worthy, not post-worthy, or unregistered repo) |
| 1 | Configuration error |
| 2 | Database error |
| 3 | LLM API error |
| 4 | Telegram notification failed (non-fatal logged) |

---

## Scheduler Implementation

**Architecture: Cron-based, no daemon.**

### Cron Setup

```bash
*/1 * * * * /usr/local/bin/social-hook scheduler-tick >> ~/.social-hook/logs/scheduler.log 2>&1
```

### scheduler-tick Behavior

```python
def scheduler_tick():
    # 1. Auto-promote deferred drafts (FIFO)
    promote_deferred_drafts(conn, config)

    # 2. Post due drafts
    due = db.query("SELECT * FROM drafts WHERE status='scheduled' AND scheduled_time <= now()")
    for draft in due:
        changes = get_draft_changes(draft.id)
        if changes:
            draft = apply_changes(draft, changes)

        # 3. Dispatch posting via vehicle pipeline
        from social_hook.vehicle import post_by_vehicle
        parts = get_draft_parts(conn, draft.id) if draft.vehicle == "thread" else None
        reference = None
        if draft.reference_post_id and draft.reference_type in ("quote", "reply"):
            ref_post = get_post(conn, draft.reference_post_id)
            ref_type = QUOTE if draft.reference_type == "quote" else REPLY
            if not adapter.supports_reference_type(ref_type):
                ref_type = LINK
            reference = PostReference(ref_post.external_id, ref_post.external_url, ref_type)
        result = post_by_vehicle(adapter, draft, parts, draft.media_paths, reference)

        if result.success:
            update_status(draft.id, 'posted')
            send_notification(config, f"Posted: {result.url}")
        else:
            handle_failure(draft, result.error)
```

#### `promote_deferred_drafts()`

Runs at the start of each scheduler tick, before the due-drafts check. Queries deferred drafts in FIFO order (oldest first) and for each:
- If the draft's platform is disabled or removed from config: cancels the draft
- If scheduling capacity is still exhausted (`calculate_optimal_time()` returns `deferred=True`): skips (remains deferred)
- If a slot is available: promotes to `scheduled` with the calculated optimal time, sends notification

**Timing:** Posts may be up to 60 seconds late (acceptable).

### Adapter-Based Notifications

Scheduler notifications use `send_notification()` from `notifications.py`, which is a backward-compat wrapper around `broadcast_notification()`. It delivers plain text messages to all configured channels. See [Notification Routing](#notification-routing) for the full `broadcast_notification()` channel iteration logic.

### Concurrent Tick Protection

- Lock file: `~/.social-hook/scheduler.lock`
- If lock exists and process alive: skip tick (prevents overlap)
- If lock exists but process dead: remove stale lock, proceed
- Lock released on tick completion or crash

### Failure Handling

- Retry with backoff (max 3 attempts)
- After 3 failures: mark 'failed', alert human
- Human can `/retry <draft-id>`

---

## Logging/Observability

### Log Location

```
~/.social-hook/logs/
  +-- trigger.log      # Trigger runs
  +-- scheduler.log    # Scheduler ticks
  +-- bot.log          # Telegram bot
  +-- api-calls.log    # External API calls
  +-- archive/         # Rotated (30 days)
```

### Log Levels

ERROR, WARN, INFO (default), DEBUG

### Log Format

```json
{
  "timestamp": "2026-02-03T10:30:00Z",
  "level": "INFO",
  "component": "trigger",
  "project_id": "my-project",
  "event": "decision_made",
  "decision": "post_worthy"
}
```

### CLI Access

```bash
social-hook logs                 # Tail all
social-hook logs trigger         # Tail trigger.log
social-hook logs --level error   # Filter errors
```

---

## File System Details

**Central location:** `~/.social-hook/`

```
~/.social-hook/
  +-- config.yaml          # Main configuration
  +-- .env                  # Credentials
  +-- social-hook.db        # SQLite database
  +-- prompts/
  |   +-- evaluator.md      # Evaluator system prompt
  |   +-- drafter.md        # Drafter/Expert system prompt
  |   +-- gatekeeper.md     # Gatekeeper system prompt
  +-- logs/
  |   +-- trigger.log
  |   +-- scheduler.log
  |   +-- bot.log
  |   +-- api-calls.log
  +-- media-cache/          # Generated media (temporary)
  +-- narratives/           # Development journey JSONL files
  |   +-- {project-id}.jsonl
```

### Cron Entry

Added by `social-hook install-scheduler`:

```bash
*/1 * * * * /usr/local/bin/social-hook scheduler-tick >> ~/.social-hook/logs/scheduler.log 2>&1
```

**Installation notes:**
- Appends to existing crontab (preserves user's other jobs)
- Skips if identical entry already present
- macOS: uses standard cron (launchd alternative is Day 2)

### Hook Entry

Added to `~/.claude/hooks.json` - see Hook Configuration section.

---

## LLM Prompt Management

### Prompt Location

`~/.social-hook/prompts/`

| File | Role |
|------|------|
| `evaluator.md` | Evaluator system prompt |
| `drafter.md` | Drafter/Expert system prompt |
| `gatekeeper.md` | Gatekeeper system prompt |

### Prompt Structure

```markdown
# Evaluator System Prompt

You are the Evaluator...

## Inputs
- Commit hash, message, diff
- Project docs, social-context.md
- Recent decisions and posts

## Outputs
Return JSON: { decision, reasoning, episode_type, ... }

## Criteria
[From CONTENT_GENERATION_GUIDE]

## Examples
[Few-shot examples]
```

### Runtime Assembly

Context assembly differs by agent role:

#### Evaluator Context Assembly

The Evaluator receives the richest context to make nuanced post-worthiness decisions:

```
[System prompt: evaluator.md]
---
## Project Context
[social-context.md content]
[Project documentation: README.md, key docs from repo]
---
## Current State
- Lifecycle phase: {phase} (confidence: {0.0-1.0})
- Narrative debt: {counter}
- Audience introduced: {true/false}
- Pending drafts: [{draft summaries for consolidation consideration}]
---
### Active Arcs
- [id=arc_1] {theme} ({post_count} posts, last post {days} ago)
  - {platform} [id=post_abc]: {up to 500 chars of content}... ({age}, {url})
  - {platform} [id=post_def]: {up to 500 chars of content}... ({age}, {url})
- [id=arc_2] {theme} ({post_count} posts, last post {days} ago)
  ...
---
## Recent History
[Last {config.context.recent_decisions} decisions with reasoning]
---
## Post History
[Last {config.context.recent_posts} posts, each showing up to 500 chars of content]
---
## Current Commit
- Hash: {hash}
- Message: {message}
- Diff summary: {files changed, insertions, deletions}
- Full diff: {diff content, truncated if > threshold}
```

#### Drafter/Expert Context Assembly

The Drafter receives evaluation result plus context for content creation:

```
[System prompt: drafter.md]
---
## Project Context
[social-context.md content]
[Project documentation subset relevant to commit]
---
## Evaluation Result
[Decision from Evaluator: post_worthy, episode_type, media_tool, etc.]
---
## Arc Context (if post_category == 'arc')
[Previous posts in this arc for narrative continuity]
[Arc theme, post_count, started_at]
---
## Recent Posts
[Last {config.context.recent_posts} posts for voice consistency and avoiding repetition]
---
## Current Commit
[Same as Evaluator]
```

When the Evaluator marks a post as `post_category: arc`, the Drafter receives arc-specific context: previous posts in that arc (traced via decisions with matching `arc_id` → drafts → posts) plus arc metadata. This enables narrative continuity across arc posts. For `opportunistic` or `experiment` categories, this section is omitted.

#### Expert Escalation Context Assembly

When the Gatekeeper escalates to the Expert, the Expert receives the Drafter's system prompt plus escalation-specific context:

```
[System prompt: drafter.md]
---
## Project Summary
{pre-injected ~500 token summary from projects.summary}
---
## Current Draft
[Draft content, platform, media_spec]
---
## User Message
[Original Telegram message that triggered escalation]
---
## Escalation
Reason: {escalation_reason from Gatekeeper}
Context: {escalation_context from Gatekeeper}
```

The Expert shares `drafter.md` with the Drafter but receives a different context assembly: the existing draft (not a commit), the user's message, and escalation context. The Expert does NOT receive full project documentation or recent history — it operates on the draft + user intent.

#### Gatekeeper Context Assembly

The Gatekeeper receives a system snapshot (live DB + config data), project summary, enriched context parameters, draft context, and the user message:

```
[System prompt: gatekeeper.md]
---
## System Status
- Projects: my-app (active, build phase)
- Pending drafts: 3 (1 draft, 2 approved)
- Active arcs: "Pipeline Architecture" (5 posts)
- Last post: 2h ago on x
- Platforms: x (enabled, free tier)
- Schedule: UTC, Tue/Wed/Thu at 9/12/17, max 3/day
- Media tools: mermaid, ray_so
- Commands: /help, /review, /status, /list, /approve, /reject, /schedule
---
## Project Summary
{pre-injected ~500 token summary from projects.summary}
---
## Recent Decisions
{last 10 decisions with commit hash, decision type, reasoning}
---
## Recent Posts
{last 5 posts with platform, content preview, posted_at}
---
## Active Arcs
{active arc themes with post counts}
---
## Recent Chat
{token-budgeted recent conversation from chat_messages table}
---
## Current Draft
[Draft content, platform, suggested_time]
---
## Linked Decision
[Evaluator decision that created this draft, if available]
---
## User Message
[Telegram message to process]
```

The system snapshot is built by `_build_system_snapshot()` in `commands.py`, which queries the DB for projects, pending drafts, active arcs, recent posts, and lifecycle phase, and reads platform/scheduling/media config. Chat history is built by `_build_chat_history()` from the platform-agnostic `chat_messages` table. This enables the Gatekeeper to answer questions like "how many drafts?" or "what platforms are enabled?" directly from its prompt context, and to resolve conversational references like "how about now?" across all platforms.

**Enriched context parameters** are passed to `gatekeeper.route()` as keyword arguments: `recent_decisions`, `recent_posts`, `lifecycle_phase`, `active_arcs`, `narrative_debt`, `audience_introduced`, `linked_decision`. These are fetched in a single try/except block in `handle_message()`, with all variables defaulting to `None` on failure (graceful degradation). The arcs fetch is shared with `_build_system_snapshot()` to avoid duplicate DB queries.

The project summary is pre-injected (not fetched via tool call) so the Gatekeeper can:
- Understand project context without full documentation
- Make informed decisions about escalation
- Answer decision log queries with context

For decision log queries ("why didn't you post about X?"), the Gatekeeper fetches relevant decisions on-demand from the database and includes them in context.

### Project Summary System

Project summaries provide compressed context (~500 tokens) for the Gatekeeper, enabling it to understand project context without loading full documentation.

#### Summary Content Structure

Inspired by Claude Code's compact format, summaries contain:

```
# Project: {name}

## What It Does
{1-2 sentence description of the project's purpose}

## Current State
- Phase: {lifecycle phase}
- Active arcs: {list of current narrative arcs}
- Recent milestone: {last significant event}

## Key Themes
{3-5 bullet points of recurring topics/patterns from recent posts}

## Audience Context
- Introduced: {yes/no}
- Primary platform: {X/LinkedIn/etc.}
- Voice notes: {key voice characteristics from social-context.md}
```

#### Who Creates Summaries

The **Evaluator** creates and refreshes project summaries as part of its evaluation flow. This happens:
- On first evaluation for a new project (summary is empty)
- When the Evaluator determines the summary is stale (uses judgment)

#### Freshness Indicators

The Evaluator has access to freshness indicators via `get_summary_freshness()`:
- `commits_since_summary`: Number of decisions since last summary update
- `days_since_summary`: Days since last summary update

The Evaluator uses judgment to decide when to refresh, considering:
- Significant project changes (new features, pivots)
- Accumulated decisions that shift project direction
- Time elapsed since last refresh

#### Gatekeeper Context Injection

System snapshot, project summary, and chat history are **pre-injected** into Gatekeeper context (not fetched via tool call):

```
[System prompt: gatekeeper.md]
---
## System Status
{live snapshot from _build_system_snapshot() — projects, drafts, arcs, posts, platforms, scheduling, media tools, commands}
---
## Project Summary
{pre-injected project summary - ~500 tokens}
---
## Recent Chat
{token-budgeted recent conversation from chat_messages table}
---
## Current Draft
[Draft content, platform, suggested_time]
---
## User Message
[Telegram message to process]
```

This allows the Gatekeeper to:
- Answer questions about system state (draft counts, platforms, schedule, arcs)
- Understand project context for decision log queries
- Make informed routing decisions
- Provide contextual responses without escalation to Expert
- Resolve conversational references ("how about now?", "those", "it") from chat history

#### Summary Refresh Flow

```
1. Evaluator receives commit for evaluation
2. Evaluator checks get_summary_freshness()
3. IF summary is stale (Evaluator judgment):
   a. Generate new summary based on current state
   b. Call update_project_summary()
4. Continue with normal evaluation
```

The summary refresh is opportunistic - it happens during evaluation, not as a separate job.

### Context Compaction

When context approaches token limits, the system compacts older data into summaries while preserving recent detail.

#### Compaction Strategy: Rolling Window + Milestone Summaries

From CONTEXT_MEMORY_ANALYSIS.md, the system uses:

1. **Rolling Window**: Keep last N items in full detail
   - Recent 30 decisions (configurable)
   - Recent 15 posts (configurable)
   - Recent 14 days of commits

2. **Milestone Summaries**: Compress older data at natural boundaries
   - After each post: Summarize commits/decisions that led to it
   - Weekly: Create week-in-review summary
   - On release tags: Create release summary

#### Compaction Triggers

| Trigger | Check Frequency | Action |
|---------|-----------------|--------|
| Token threshold (150K) | Before each evaluation | Truncate oldest items |
| Post published | On event | Create post milestone summary |
| Release tagged | On git tag | Create release summary |
| Age threshold (90 days) | Before each evaluation | Move old items to milestone summaries |
| Weekly | Background job (optional) | Create weekly digest |

#### Milestone Summary Storage

Summaries are stored in `milestone_summaries` table:

```sql
CREATE TABLE milestone_summaries (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    milestone_type  TEXT NOT NULL CHECK (milestone_type IN ('post', 'release', 'weekly', 'monthly')),
    summary         TEXT NOT NULL,
    items_covered   TEXT NOT NULL DEFAULT '[]',  -- JSON array of decision IDs
    token_count     INTEGER NOT NULL DEFAULT 0,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

#### Context Assembly with Compacted Data

```python
def assemble_evaluator_context(project_id: str, db) -> dict:
    """Assemble context, using summaries for old data."""
    context = {
        # Recent items (full detail)
        "recent_decisions": db.get_recent_decisions(project_id, limit=30),
        "recent_posts": db.get_recent_posts_for_context(project_id, limit=15),

        # Current state
        "lifecycle": db.get_lifecycle(project_id),
        "active_arcs": db.get_active_arcs(project_id),
        "narrative_debt": db.get_narrative_debt(project_id),

        # Scheduling capacity snapshot
        "scheduling_state": get_scheduling_state(db, project_id, config),

        # Project docs
        "social_context": load_social_context(project_id),
        "project_docs": load_project_docs(project_id),

        # Historical summaries (compressed)
        "milestone_summaries": db.get_milestone_summaries(project_id, since_days=180),
    }

    # Check if real-time compaction needed
    if count_tokens(context) > config.context.max_tokens:
        context = compact_by_truncation(context)

    return context
```

The `scheduling_state` is assembled by `get_scheduling_state()` from `scheduling.py` and injected into the evaluator prompt as a `## Scheduling State` section by `assemble_evaluator_prompt()`. It contains:

| Field | Source | Prompt output |
|-------|--------|---------------|
| `weekly_posts` / `max_per_week` | `COUNT(posts)` last 7 days + `config.scheduling.max_per_week` | "Project weekly limit: N/M posts" |
| `PlatformSchedulingState.posts_today` | `COUNT(posts)` today for platform | "Today: N/M posts" |
| `PlatformSchedulingState.slots_remaining_today` | Calculated from `max_posts_per_day` - today's posts | "Slots remaining: ~N" |
| `PlatformSchedulingState.pending_drafts` | Drafts with status in (`draft`, `approved`, `scheduled`) | "Pending drafts: N" |
| `PlatformSchedulingState.deferred_drafts` | Drafts with `status='deferred'` | "Deferred: N" (shown only if >0) |

#### Compaction is Rare

With 200K token context windows and generous defaults (30 decisions, 15 posts), most projects will never trigger compaction. The system is designed for:
- **Typical case**: Full rolling window, no compaction needed
- **Edge case**: Very active projects or long-running projects hit milestone compaction
- **Rare case**: Real-time truncation only when approaching 150K tokens

### Customization

Users edit prompts directly. Upgrades preserve customizations.

---

## Tool Call Schemas

LLM roles use tool calls (function calling) for structured output.

> **Note:** The `decision` field in Evaluator output (post_worthy, not_post_worthy, etc.) is distinct from draft `status` (draft, approved, scheduled, etc.). Decision = evaluation outcome. Status = draft lifecycle state.

### Evaluator Tool: `log_decision`

```json
{
  "name": "log_decision",
  "description": "Record the evaluation decision for a commit",
  "input_schema": {
    "type": "object",
    "properties": {
      "decision": {
        "type": "string",
        "enum": ["post_worthy", "not_post_worthy", "consolidate", "deferred", "imported"]
      },
      "reasoning": {
        "type": "string",
        "description": "Explanation for the decision"
      },
      "episode_type": {
        "type": "string",
        "enum": ["decision", "before_after", "demo_proof", "milestone", "postmortem", "launch", "synthesis"]
      },
      "post_category": {
        "type": "string",
        "enum": ["arc", "opportunistic", "experiment"]
      },
      "arc_id": {
        "type": "string",
        "description": "ID of active arc, if applicable"
      },
      "media_tool": {
        "type": "string",
        "enum": ["mermaid", "nano_banana_pro", "playwright", "ray_so", "none"]
      }
    },
    "required": ["decision", "reasoning"]
  }
}
```

### Drafter Tool: `create_draft`

```json
{
  "name": "create_draft",
  "description": "Create draft content for social media",
  "input_schema": {
    "type": "object",
    "properties": {
      "content": {
        "type": "string",
        "description": "The post content"
      },
      "platform": {
        "type": "string",
        "enum": ["x", "linkedin"]
      },
      "media_type": {
        "type": "string",
        "enum": ["mermaid", "nano_banana_pro", "playwright", "ray_so", "none"]
      },
      "media_spec": {
        "type": "object",
        "description": "Specification for media generation"
      },
      "vehicle": {
        "type": "string",
        "enum": ["single", "thread", "article"],
        "description": "Content vehicle for this draft"
      },
      "reasoning": {
        "type": "string",
        "description": "Why this angle/content was chosen"
      }
    },
    "required": ["content", "platform", "reasoning"]
  }
}
```

### Gatekeeper Tool: `route_action`

```json
{
  "name": "route_action",
  "description": "Route user message to appropriate handler",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["handle_directly", "escalate_to_expert"]
      },
      "operation": {
        "type": "string",
        "enum": ["approve", "schedule", "reject", "cancel", "substitute", "query"],
        "description": "For handle_directly: which operation"
      },
      "params": {
        "type": "object",
        "description": "Parameters for the operation"
      },
      "escalation_reason": {
        "type": "string",
        "description": "For escalate: why escalating"
      },
      "escalation_context": {
        "type": "string",
        "description": "For escalate: context to pass to expert"
      }
    },
    "required": ["action"]
  }
}
```

#### Conversational Message Handling

The `query` operation handles conversational messages (greetings, status checks, general questions) in addition to system/decision queries. The Gatekeeper prompt instructs the LLM to use `route_action` with `operation: query` and provide a friendly response in `params.answer`.

**Text fallback safety net:** If the LLM responds with plain text instead of using the tool (e.g., for casual messages like "hi"), `gatekeeper.py` catches `MalformedResponseError` and constructs a known-good `RouteActionInput` with the LLM's text extracted as the answer. This ensures the chat never crashes on conversational input. See `_extract_text_content()` in `gatekeeper.py`.

### Expert Tool: `expert_response`

The Expert (Drafter model handling escalations) uses this tool for responses:

```json
{
  "name": "expert_response",
  "description": "Provide expert response to escalated request",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["refine_draft", "answer_question", "save_context_note"]
      },
      "refined_content": {
        "type": "string",
        "description": "For refine_draft: the new draft content"
      },
      "refined_media_spec": {
        "type": "object",
        "description": "For refine_draft: updated media spec to trigger media regeneration (e.g., changed diagram, different code snippet)"
      },
      "refined_vehicle": {
        "type": "string",
        "enum": ["single", "thread", "article"],
        "description": "For refine_draft: change the content vehicle"
      },
      "answer": {
        "type": "string",
        "description": "For answer_question: response to user's question"
      },
      "context_note": {
        "type": "string",
        "description": "For save_context_note: note to save for future evaluations"
      },
      "reasoning": {
        "type": "string",
        "description": "Why this response/refinement"
      }
    },
    "required": ["action", "reasoning"]
  }
}
```

### Tool Call Response Handling

#### Parsing Tool Calls

Parse tool calls from the response content array. `extract_tool_call()` lives in `base.py` (reusable layer) and raises `ToolExtractionError` (a `ValueError` subclass):

```python
def extract_tool_call(response, expected_tool: str | list[str]) -> dict:
    """Extract tool call input from LLM response. Lives in base.py."""
    ...
    raise ToolExtractionError(f"No {expected_tool} tool call in response")
```

Response content can be mixed (text + tool_use blocks), so always filter by `content.type == "tool_use"`.

#### Validation with Pydantic

Validate tool call responses using Pydantic models:

```python
from pydantic import BaseModel, ValidationError
from enum import Enum

class DecisionType(str, Enum):
    post_worthy = "post_worthy"
    not_post_worthy = "not_post_worthy"
    consolidate = "consolidate"
    deferred = "deferred"
    imported = "imported"

class LogDecisionInput(BaseModel):
    decision: DecisionType
    reasoning: str
    episode_type: str | None = None
    post_category: str | None = None
    arc_id: str | None = None
    media_tool: str | None = None

# Usage
try:
    validated = LogDecisionInput(**tool_call.input)
except ValidationError as e:
    raise MalformedResponseError(f"Invalid tool call: {e}")
```

Pydantic provides enum enforcement, required field checking, type coercion, and clear error messages.

---

## Media Generation Adapters

### Interface

```python
class MediaAdapter(ABC):
    def generate(self, spec: dict) -> MediaResult
    def supports(self, media_type: str) -> bool

    @classmethod
    def spec_schema(cls) -> dict:
        """Per-tool spec schema: {"required": {...}, "optional": {...}}."""

    def preview_text(self, spec: dict) -> str:
        """Human-readable preview of what the spec will generate."""
```

`spec_schema()` and `preview_text()` are non-abstract with safe defaults (empty schema, `str(spec)`) for backward compatibility. Each adapter overrides them with tool-specific fields.

### Implementations

| Adapter | Method | Spec Schema (required) |
|---------|--------|----------------------|
| Mermaid | mermaid.ink API or local mmdc | `diagram` |
| Nano Banana Pro | Google Generative AI API | `prompt` |
| Playwright | Browser automation for screenshots | `url` |
| Ray.so | Playwright renders ray.so URL | `code` |

### Registry

```python
MEDIA_ADAPTER_NAMES = ["mermaid", "nano_banana_pro", "playwright", "ray_so"]

def get_media_adapter(name: str, api_key: str = None) -> Optional[MediaAdapter]:
    """Get media adapter by name with lazy initialization."""
    ...

def get_tool_spec_schema(name: str) -> dict:
    """Get the spec schema for a tool (via adapter class, no instantiation)."""
    ...

def get_blank_template(name: str) -> dict:
    """Get a blank template with all required keys set to empty strings."""
    ...

def list_available_tools() -> list[dict]:
    """List all tools with name, display_name, and description."""
    ...
```

The media registry uses `AdapterRegistry` from `registry.py` for dispatch. Each tool has a private factory function registered with metadata (display_name, description). `get_tool_spec_schema()` and `get_blank_template()` use lazy class imports (`_ADAPTER_CLASSES` dict) to access `spec_schema()` without instantiating adapters (avoids requiring API keys at query time). `list_available_tools()` returns metadata from the registry for UI tool pickers.

### NanoBananaAdapter (Image Generation)

Nano Banana Pro is Google's Gemini 3 Pro Image model for professional image generation.

| Name | Model ID | Use Case |
|------|----------|----------|
| Nano Banana | `gemini-2.5-flash-image` | Fast, efficient |
| Nano Banana Pro | `gemini-3-pro-image-preview` | Professional, 4K output |

**API Endpoint:**

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent
```

**Headers:**

```
x-goog-api-key: $GEMINI_API_KEY
Content-Type: application/json
```

**Request Body:**

```json
{
  "contents": [{
    "parts": [{"text": "Image generation prompt"}]
  }],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"]
  }
}
```

**Key Features:**
- Up to 4K resolution output
- Sharp text rendering in images
- Subject consistency (up to 14 image references)

**Required Credential:** `GEMINI_API_KEY` in `~/.social-hook/.env`

**Source:** [Google Gemini Image Generation](https://ai.google.dev/gemini-api/docs/image-generation)

---

## Platform Posting Adapters

Separate from media adapters - these handle posting to social platforms.

**Note:** The authoritative PlatformAdapter ABC and PostResult dataclass are defined in the [Platform Abstraction](#platform-abstraction) section above. This section provides additional implementation guidance.

### Platform Character Limits

| Platform | Tier | Limit | Notes |
|----------|------|-------|-------|
| X | Free | 280 chars | Must use threads for multi-beat content >280 chars |
| X | Basic ($3/mo) | 25,000 chars | Single long-form posts OR threads — drafter chooses |
| X | Premium ($8/mo) | 25,000 chars | Single long-form posts OR threads — drafter chooses |
| X | Premium+ ($40/mo) | 25,000 chars | Single long-form posts OR threads — drafter chooses |
| LinkedIn | — | 3,000 chars | Posts API, no thread support |

**Thread strategy (narrative-first):** Format is driven by narrative structure (episode type, beat count), not character overflow. A postmortem with 4 beats is a thread because it HAS 4 beats, not because it exceeds 280 chars. Paid tiers can express multi-beat content as a single long-form post or a thread — the drafter chooses. Free tier must use threads when content exceeds 280 chars (platform constraint). Thread tweets are always 280 chars/tweet regardless of tier.

### Implementations

| Adapter | API | Auth | Reference Support | Notes |
|---------|-----|------|-------------------|-------|
| XAdapter | X API v2 | OAuth 2.0 PKCE | REPLY, QUOTE, LINK (all native) | Handles threads, media upload |
| LinkedInAdapter | LinkedIn REST API | OAuth 2.0 | QUOTE (reshare, LinkedIn URN only), LINK | HTTPS redirect required |

### X API Authentication

X uses OAuth 2.0 PKCE exclusively (OAuth 1.0a has been dropped).

**OAuth 2.0 PKCE:**
- Scopes: `tweet.read`, `tweet.write`, `users.read`, `media.write`
- Access token: 2 hours, refresh token: 6 months
- Token refresh handled automatically by `adapters/auth.py`

**Token acquisition methods:**
1. CLI script: `scripts/oauth2_setup.py` (localhost callback server)
2. Setup wizard: interactive PKCE flow during onboarding
3. Web UI: Settings > Platforms > X or Wizard > Credentials step

**Web OAuth endpoints** (in `web/server.py`):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/oauth/x/authorize` | GET | Initiates PKCE flow, returns authorization URL for the user to visit |
| `/api/oauth/x/callback` | GET | Handles X redirect, exchanges authorization code for tokens, saves to DB |
| `/api/oauth/x/status` | GET | Checks if tokens exist, returns connected status and username |

The callback URL is `http://localhost:{api_port}/api/oauth/x/callback` (default port 8741). Users must register this URL in the X Developer Portal. The frontend displays a "Connect X Account" button (Settings > Platforms > X and Wizard > Credentials), a connected status indicator, and the callback URL for reference.

### X Media Upload

Endpoint: `POST https://api.x.com/2/media/upload`

| Media Type | Formats | Max Size |
|------------|---------|----------|
| Images | JPG, PNG, GIF, WEBP | 5 MB |
| Animated GIF | GIF | 15 MB |
| Video | MP4 (H.264) | 512 MB |

Per tweet: Up to 4 images, OR 1 GIF, OR 1 video

### Dry-Run Mode

Dry-run mode (`--dry-run` flag) allows testing the full pipeline without side effects:

**What happens:**
- Real LLM API calls are made (costs money, tests actual behavior)
- Platform adapters return simulated success (no posting to X/LinkedIn)
- Telegram notifications are skipped
- Database writes are skipped (no decisions, drafts, or usage records persisted)

**Implementation Pattern (pseudocode):**

The following shows the pattern for dry-run handling. Actual implementation in WS2 will handle ID generation and all write operations.

```python
class DryRunContext:
    """Wraps DB operations, skipping writes during dry-run. (Pseudocode)"""

    def __init__(self, db: Database, dry_run: bool = False):
        self.db = db
        self.dry_run = dry_run

    # Reads work normally - need real historical context
    def get_recent_decisions(self, project_id, limit):
        return self.db.get_recent_decisions(project_id, limit)

    def get_pending_drafts(self, project_id):
        return self.db.get_pending_drafts(project_id)

    # Writes become no-ops in dry-run mode
    def insert_decision(self, decision):
        if self.dry_run:
            return decision.id  # Return ID but don't persist
        return self.db.insert_decision(decision)

    def insert_draft(self, draft):
        if self.dry_run:
            return draft.id
        return self.db.insert_draft(draft)

    def insert_usage(self, usage):
        if self.dry_run:
            return  # Skip usage logging in dry-run
        return self.db.insert_usage(usage)
```

**Output:** Results are written to stdout (or `--output <file>` for golden file comparison). The output shows what *would* have happened without leaving any trace in the database.

---

## Setup Wizard Implementation

Interactive setup via `social-hook setup`. See [REQUIREMENTS.md Setup Wizard](REQUIREMENTS.md#setup-wizard) for user-facing flow.

### Library Stack

| Library | Purpose | Install |
|---------|---------|---------|
| [Rich](https://github.com/Textualize/rich) | Beautiful output (panels, tables, spinners, colors) | `pip install rich` |
| [InquirerPy](https://github.com/kazhala/InquirerPy) | Interactive prompts (selections, confirmations, passwords) | `pip install inquirerpy` |
| [Typer](https://typer.tiangolo.com/) | CLI command structure | `pip install typer[all]` |

Combined install: `pip install rich inquirerpy typer[all]`

### Setup Flow Implementation

```python
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from InquirerPy import inquirer
from InquirerPy.validator import EmptyInputValidator
import typer

console = Console()
app = typer.Typer()

@app.command()
def setup(
    validate: bool = typer.Option(False, "--validate", help="Validate existing config"),
    only: str = typer.Option(None, "--only", help="Reconfigure specific section"),
):
    if validate:
        return validate_all_credentials()

    if only:
        return reconfigure_section(only)

    run_full_setup()

def run_full_setup():
    # Step 1: Welcome
    console.print(Panel.fit(
        "[bold blue]Social Hook Setup[/bold blue]\n"
        "Configure your social media automation",
        border_style="blue"
    ))

    # Step 2: Claude API
    config = {}
    config["anthropic_api_key"] = setup_claude_api()

    # Step 3: Voice & Style (creates global social-context.md)
    setup_voice_style()

    # Step 4: Platform Settings (creates global content-config.yaml)
    setup_platform_settings()

    # Step 5: Model selection
    config["models"] = setup_models()

    # Step 6: Telegram
    config["telegram"] = setup_telegram()

    # Step 7-9: Optional platforms
    if inquirer.confirm("Enable X/Twitter posting?", default=True).execute():
        config["x"] = setup_x_api()

    if inquirer.confirm("Enable LinkedIn posting?", default=False).execute():
        config["linkedin"] = setup_linkedin()

    if inquirer.confirm("Enable media generation?", default=True).execute():
        config["media_gen"] = setup_media_gen()

    # Step 10: Scheduling
    config["scheduling"] = setup_scheduling()

    # Step 11: Summary & save
    display_summary(config)
    if inquirer.confirm("Save configuration?", default=True).execute():
        save_config(config)

        # Install components
        install_hook()
        install_scheduler()
        start_bot(config["telegram"])

        console.print("\n[bold green]Setup complete![/bold green]")
        console.print("Register your first project:")
        console.print("  social-hook register /path/to/repo")
```

### Voice & Style Step Implementation

```python
def setup_voice_style() -> None:
    """Interactive voice/style configuration for global social-context.md."""
    console.print("\n[bold]Voice & Style[/bold]")
    console.print("Define your default voice for all projects.\n")

    # Voice tone selection
    tone = inquirer.select(
        "Voice tone:",
        choices=["Professional", "Casual", "Technical", "Custom"],
    ).execute()

    # Audience input
    audience = inquirer.text(
        "Target audience:",
        default="Developers interested in ",
    ).execute()

    # Topics multi-select
    topics = inquirer.checkbox(
        "Topics you post about:",
        choices=["Open source", "DevOps", "Web development", "AI/ML", "System design"],
    ).execute()

    # Pet peeves
    pet_peeves = inquirer.text(
        "Pet peeves (content to avoid):",
        default="",
    ).execute()

    # Generate and save social-context.md
    content = generate_social_context(tone, audience, topics, pet_peeves)
    (Path.home() / ".social-hook" / "social-context.md").write_text(content, encoding="utf-8")
    console.print("[green]✓[/green] Saved ~/.social-hook/social-context.md")


def setup_platform_settings() -> None:
    """Interactive platform configuration for global content-config.yaml."""
    console.print("\n[bold]Platform Settings[/bold]")
    console.print("Configure default posting preferences.\n")

    # Platform selection
    platforms = inquirer.checkbox(
        "Default platforms:",
        choices=["X/Twitter", "LinkedIn"],
        default=["X/Twitter"],
    ).execute()

    config = {"platforms": {}}

    if "X/Twitter" in platforms:
        tier = inquirer.select(
            "X account tier:",
            choices=["Free", "Premium", "Premium+"],
        ).execute()

        enable_threads = inquirer.confirm("Enable threads?", default=True).execute()
        max_tweets = 5
        if enable_threads:
            max_tweets = int(inquirer.text("Max tweets per thread:", default="5").execute())

        config["platforms"]["x"] = {
            "enabled": True,
            "tier": tier.lower(),
            "threads": {"enabled": enable_threads, "max_tweets": max_tweets},
        }

    # Scheduling defaults
    timezone = inquirer.text("Timezone:", default="America/Los_Angeles").execute()
    max_posts = int(inquirer.text("Max posts per day:", default="3").execute())
    optimal_hours = inquirer.text("Optimal posting hours (comma-separated):", default="9,12,17").execute()

    config["scheduling"] = {
        "timezone": timezone,
        "max_posts_per_day": max_posts,
        "optimal_hours": [int(h.strip()) for h in optimal_hours.split(",")],
    }

    # Save content-config.yaml
    import yaml
    (Path.home() / ".social-hook" / "content-config.yaml").write_text(
        yaml.dump(config, default_flow_style=False), encoding="utf-8"
    )
    console.print("[green]✓[/green] Saved ~/.social-hook/content-config.yaml")
```

### Credential Validation

```python
def validate_credential(name: str, validate_fn: callable) -> bool:
    """Validate a credential with spinner feedback."""
    with console.status(f"[bold green]Validating {name}..."):
        try:
            result = validate_fn()
            console.print(f"[green]✓[/green] {name}: {result}")
            return True
        except Exception as e:
            console.print(f"[red]✗[/red] {name}: {e}")
            return False

def validate_anthropic_key(api_key: str) -> str:
    """Validate Anthropic API key, return model info."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    # Make a minimal API call to verify
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1,
        messages=[{"role": "user", "content": "hi"}]
    )
    return "Connected"

def validate_telegram_bot(token: str) -> str:
    """Validate Telegram bot token, return bot username."""
    import httpx
    response = httpx.get(f"https://api.telegram.org/bot{token}/getMe")
    data = response.json()
    if not data.get("ok"):
        raise ValueError(data.get("description", "Invalid token"))
    return f"@{data['result']['username']}"

def validate_x_api(credentials: dict) -> str:
    """Validate X API credentials, return username."""
    # Use tweepy or httpx with OAuth 1.0a
    # Return @username on success
    pass
```

### Telegram Chat ID Capture

```python
import asyncio
import httpx

async def capture_telegram_chat_id(token: str, timeout: int = 120) -> int:
    """Wait for user to message bot, return their chat ID."""
    console.print("\nSend any message to your bot now...")

    last_update_id = 0
    start_time = asyncio.get_event_loop().time()

    async with httpx.AsyncClient() as client:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError("No message received within timeout")

            response = await client.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 10}
            )
            data = response.json()

            if data.get("result"):
                update = data["result"][0]
                chat_id = update["message"]["chat"]["id"]
                username = update["message"]["from"].get("username", "Unknown")
                console.print(f"[green]✓[/green] Received! Chat ID: {chat_id} (@{username})")
                return chat_id

            await asyncio.sleep(1)
```

### LinkedIn OAuth Flow

**Important:** LinkedIn requires HTTPS redirect URIs. Localhost is NOT allowed.

**Development Options:**
1. Use ngrok or similar tunnel to get an HTTPS URL
2. Use `https://oauth.pstmn.io/v1/callback` for Postman testing
3. Set up a development domain with valid SSL certificate

**Token Lifetimes:**
| Token | Lifetime | Notes |
|-------|----------|-------|
| Access Token | 60 days | Refreshable |
| Refresh Token | 365 days | MDP partners only |

**Required Scopes:** `w_member_social`, `openid`, `profile`

**Posting Endpoint:** `POST https://api.linkedin.com/rest/posts`

**Required Headers:**
```
Authorization: Bearer {access_token}
X-Restli-Protocol-Version: 2.0.0
LinkedIn-Version: 202501
Content-Type: application/json
```

**Get Author URN:**
```
GET https://api.linkedin.com/v2/userinfo
```
Returns `sub` field → construct URN: `urn:li:person:{sub}`

**Post Request Body:**
```json
{
  "author": "urn:li:person:782bbtaQ",
  "commentary": "Post content here",
  "visibility": "PUBLIC",
  "distribution": {
    "feedDistribution": "MAIN_FEED",
    "targetEntities": [],
    "thirdPartyDistributionChannels": []
  },
  "lifecycleState": "PUBLISHED",
  "isReshareDisabledByAuthor": false
}
```

**Response:** Post ID returned in `x-restli-id` header.

**OAuth Flow (with HTTPS redirect):**

```python
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

def setup_linkedin_oauth(client_id: str, client_secret: str, redirect_uri: str) -> dict:
    """Run OAuth flow for LinkedIn, return tokens.

    Note: redirect_uri MUST be HTTPS. Localhost is not allowed.
    For development, use ngrok or similar to get an HTTPS URL.
    """

    AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile w_member_social",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    console.print("Opening browser for LinkedIn authorization...")
    console.print(f"[yellow]Note: Redirect URI must be HTTPS[/yellow]")
    webbrowser.open(auth_url)

    # For local development with ngrok, parse the redirected URL manually
    # or set up a local HTTPS server
    auth_code = console.input("Paste the authorization code from the redirect URL: ")

    if not auth_code:
        raise ValueError("Authorization failed")

    # Exchange code for token
    response = httpx.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    })

    return response.json()
```

### Timezone Auto-Detection

```python
import subprocess
import re

def detect_timezone() -> str:
    """Detect system timezone."""
    try:
        # macOS / Linux
        if (tz_file := Path("/etc/localtime")).is_symlink():
            target = str(tz_file.resolve())
            match = re.search(r"zoneinfo/(.+)$", target)
            if match:
                return match.group(1)

        # Fallback: timedatectl (Linux with systemd)
        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return "UTC"  # Safe default
```

### Component Installation

Setup wizard installs all components automatically after saving configuration.

```python
import json
import subprocess
from pathlib import Path

def install_hook():
    """Install Claude Code PostToolUse hook."""
    console.print("\nInstalling Claude Code hook...")

    hooks_file = Path.home() / ".claude" / "hooks.json"
    hooks_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing hooks or create new
    if hooks_file.exists():
        hooks = json.loads(hooks_file.read_text())
    else:
        hooks = {"hooks": {}}

    # Define our hook
    our_hook = {
        "matcher": {
            "tool": "Bash",
            "command_pattern": "^git\\s+(commit|merge|rebase|cherry-pick)"
        },
        "action": {
            "type": "exec",
            "command": "social-hook trigger --commit $(git rev-parse HEAD) --repo $(pwd)"
        }
    }

    # Add to PostToolUse hooks if not already present
    post_hooks = hooks["hooks"].setdefault("PostToolUse", [])
    if our_hook not in post_hooks:
        post_hooks.append(our_hook)
        hooks_file.write_text(json.dumps(hooks, indent=2))
        console.print("  [green]✓[/green] Hook added to ~/.claude/hooks.json")
    else:
        console.print("  [dim]Hook already installed[/dim]")


def install_scheduler():
    """Install cron job for scheduler tick."""
    console.print("\nInstalling scheduler...")

    cron_entry = "*/1 * * * * /usr/local/bin/social-hook scheduler-tick >> ~/.social-hook/logs/scheduler.log 2>&1"

    # Get current crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current_crontab = result.stdout if result.returncode == 0 else ""

    # Check if already installed
    if "social-hook scheduler-tick" in current_crontab:
        console.print("  [dim]Scheduler already installed[/dim]")
        return

    # Append our entry
    new_crontab = current_crontab.rstrip() + "\n" + cron_entry + "\n"
    subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
    console.print("  [green]✓[/green] Cron job added (runs every minute)")


def start_bot(telegram_config: dict):
    """Start Telegram bot as background daemon."""
    console.print("\nStarting Telegram bot...")

    # Start bot process in background
    subprocess.Popen(
        ["social-hook", "bot", "start", "--daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    # Verify bot is running
    import time
    time.sleep(2)

    result = subprocess.run(
        ["social-hook", "bot", "status"],
        capture_output=True, text=True
    )

    if "running" in result.stdout.lower():
        bot_name = telegram_config.get("bot_username", "Bot")
        console.print(f"  [green]✓[/green] Bot {bot_name} is now running")
    else:
        console.print("  [yellow]![/yellow] Bot may not have started. Run 'social-hook bot start' manually.")
```

### Files Created/Modified

| File | Content |
|------|---------|
| `~/.social-hook/.env` | API keys and secrets (chmod 600) |
| `~/.social-hook/config.yaml` | Model selection, scheduling, platform settings |
| `~/.social-hook/logs/` | Log directory (created) |
| `~/.claude/hooks.json` | Claude Code hook (merged with existing) |
| User's crontab | Scheduler cron entry (appended) |

**.env format:**
```bash
# Claude API (required for anthropic/ provider)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (required for openai/ provider)
OPENAI_API_KEY=sk-...

# OpenRouter (required for openrouter/ provider)
OPENROUTER_API_KEY=sk-or-v1-...

# Ollama (optional, defaults to localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434/v1

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_CHAT_IDS=123456789

# X/Twitter (optional)
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_TOKEN_SECRET=...

# LinkedIn (optional)
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_ACCESS_TOKEN=...

# Image Generation (optional)
GEMINI_API_KEY=...
```

**config.yaml format:**
```yaml
models:
  evaluator: anthropic/claude-opus-4-5    # or claude-cli/sonnet for $0
  drafter: anthropic/claude-opus-4-5      # or claude-cli/sonnet for $0
  gatekeeper: anthropic/claude-haiku-4-5  # or claude-cli/haiku for $0

platforms:
  x:
    enabled: true
    account_tier: free  # free | basic | premium | premium_plus
  linkedin:
    enabled: false

media_generation:
  enabled: true
  tools:
    mermaid: true
    nano_banana_pro: true
    playwright: true
    ray_so: true

scheduling:
  timezone: America/Los_Angeles
  max_posts_per_day: 3
  min_gap_minutes: 30
  optimal_days: [Tue, Wed, Thu]
  optimal_hours: [9, 12, 17]
```

### Context Configuration

Context limits are configurable in `config.yaml`:

```yaml
context:
  # Recent history limits (used in prompt assembly)
  recent_decisions: 30        # Default: 30 (from CONTEXT_MEMORY_ANALYSIS recommendation)
  recent_posts: 15            # Default: 15

  # Compaction thresholds
  max_tokens: 150000          # Trigger compaction when context exceeds this

  # Project docs inclusion
  max_doc_tokens: 10000       # Max tokens for prompt docs in prompts (not discovery)
  max_discovery_tokens: 60000  # Token budget for project discovery file loading
  max_file_size: 256000        # Skip files larger than this during discovery (bytes)
```

**Rationale:** Modern context windows (200K+) allow generous history. The defaults align with CONTEXT_MEMORY_ANALYSIS.md recommendations for "generous rolling window with milestone compaction."

**Truncation Priority (when context exceeds max_tokens):**

Per CONTEXT_MEMORY_ANALYSIS.md recommendations, truncate in this order (lowest priority first):
1. **Commit diff** - Truncate to summary if > threshold
2. **Older decisions** - Keep most recent, drop oldest
3. **Older posts** - Keep most recent, drop oldest
4. **Project docs** - Truncate to max_doc_tokens

Never truncate: System prompt, social-context.md, current state (lifecycle, arcs, debt)

### Security Notes

- `.env` file created with `chmod 600` (owner read/write only)
- Passwords displayed with masking (`•••`) during input
- Tokens validated immediately, never stored if invalid
- No credentials logged or displayed after capture

---

## Development Journey Capture

Captures narrative context from Claude Code development sessions for richer social media content. Opt-in feature that hooks into the `PreCompact` event — triggered when Claude Code is about to compact its context window.

### PreCompact Hook Mechanism

The hook is installed in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "social-hook narrative-capture",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
```

Claude Code pipes JSON to stdin:

```json
{
  "session_id": "abc-123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/Users/neil/dev/project",
  "trigger": "auto"
}
```

The `transcript_path` may be empty due to a known Claude Code bug ([#13668](https://github.com/anthropics/claude-code/issues/13668)). The pipeline falls back to discovering the path from `session_id` + `cwd`:

```
~/.claude/projects/{encoded_cwd}/{session_id}.jsonl
```

Where `encoded_cwd` replaces `/` with `-` (e.g., `/Users/neil/dev/project` becomes `-Users-neil-dev-project`).

### Transcript JSONL Format and Filtering Pipeline

Claude Code transcripts are JSONL files with message types: `user`, `assistant`, `progress`, `system`, `queue-operation`, `file-history-snapshot`, `summary`.

**Pipeline stages:**

```
read_transcript()       → Reads JSONL, keeps only user/assistant messages
    ↓
filter_for_extraction() → Strips tool_use, tool_result, image blocks.
                          Removes isSidechain messages and empty text blocks.
                          Keeps text and thinking blocks only.
    ↓
format_for_prompt()     → Formats as [USER] / [ASSISTANT] / [ASSISTANT THINKING] blocks
    ↓
truncate_to_budget()    → Truncates to 100K chars (~25K tokens), removes oldest first
```

### ExtractNarrativeInput Tool Schema

The LLM extracts structured narrative elements via a tool call with 8 required fields:

```json
{
  "name": "extract_narrative",
  "description": "Extract narrative elements from a development session transcript",
  "input_schema": {
    "type": "object",
    "properties": {
      "summary":              { "type": "string",  "description": "2-3 sentence session summary" },
      "key_decisions":        { "type": "array", "items": {"type": "string"}, "description": "Decisions made and their reasoning" },
      "rejected_approaches":  { "type": "array", "items": {"type": "string"}, "description": "Approaches tried and abandoned" },
      "aha_moments":          { "type": "array", "items": {"type": "string"}, "description": "Surprising insights discovered" },
      "challenges":           { "type": "array", "items": {"type": "string"}, "description": "Difficulties encountered" },
      "narrative_arc":        { "type": "string",  "description": "The session story as a narrative arc" },
      "relevant_for_social":  { "type": "boolean", "description": "Whether this session has social-media-worthy content" },
      "social_hooks":         { "type": "array", "items": {"type": "string"}, "description": "Potential post angles for social media" }
    },
    "required": ["summary", "key_decisions", "rejected_approaches", "aha_moments", "challenges", "narrative_arc", "relevant_for_social", "social_hooks"]
  }
}
```

### Storage Format

Narratives are stored as append-only JSONL at `~/.social-hook/narratives/{project-id}.jsonl`. Each line:

```json
{
  "timestamp": "2026-02-20T14:30:00+00:00",
  "session_id": "abc-123",
  "trigger": "auto",
  "summary": "...",
  "key_decisions": ["..."],
  "rejected_approaches": ["..."],
  "aha_moments": ["..."],
  "challenges": ["..."],
  "narrative_arc": "...",
  "relevant_for_social": true,
  "social_hooks": ["..."]
}
```

**Deduplication:** When loading, entries are deduplicated by `session_id` (keeps latest per session), since long sessions can trigger multiple compactions.

**Cleanup:** Entries older than 90 days are removed via `cleanup_old_narratives()`, which rewrites the file without old entries.

### Context Assembly

When narratives exist for a project, the evaluator and drafter receive a `## Development Narrative` section in their prompts. Assembly in [prompts.py](../src/social_hook/llm/prompts.py):

```python
if project_context.session_narratives:
    sections.append("\n---\n## Development Narrative")
    for n in project_context.session_narratives[:5]:  # Budget: ~2000 tokens
        in_window = n.get("_in_window", True)
        label = "" if in_window else " (earlier context)"
        sections.append(f"\n### Session: {n.get('summary', 'No summary')}{label}")
        if n.get('key_decisions'):
            sections.append("**Key decisions:** " + "; ".join(n['key_decisions'][:3]))
        if n.get('rejected_approaches'):
            sections.append("**Rejected approaches:** " + "; ".join(n['rejected_approaches'][:3]))
        if n.get('aha_moments'):
            sections.append("**Insights:** " + "; ".join(n['aha_moments'][:3]))
        if n.get('social_hooks'):
            sections.append("**Post angles:** " + "; ".join(n['social_hooks'][:3]))
```

`session_narratives` are loaded by `assemble_evaluator_context()` via `load_recent_narratives(project_id, limit=5, after=parent_timestamp, before=commit_timestamp)`, which returns up to 5 recent narratives where `relevant_for_social=True`.

**Time-window filtering:** When commit timestamps are available (extracted via `git log --format=%aI` in `parse_commit_info()`), narratives are split into *in-window* (`after < ts <= before`, exclusive lower/inclusive upper) and *out-of-window*. In-window entries are returned first, then remaining slots filled from older entries. Each entry carries an `_in_window: bool` flag. The `_render_narrative_sections()` helper appends `(earlier context)` to out-of-window session headings so the LLM can distinguish primary vs extended context.

**Timezone handling:** Narrative timestamps are always UTC (written by `datetime.now(timezone.utc)`). Git author dates include the local timezone offset (e.g. `+07:00`). All comparisons use `datetime.fromisoformat()` which produces timezone-aware objects, making cross-timezone comparison correct. The existing lexicographic sort on narrative timestamps (used for ordering within each group) remains valid because all narrative timestamps share the `+00:00` offset.

### narrative-capture Pipeline

Full pipeline executed by the hidden `social-hook narrative-capture` command:

1. Read JSON from stdin (session_id, transcript_path, cwd, trigger)
2. Load config, check `journey_capture.enabled`
3. Init database, look up project by cwd (then by git remote origin)
4. Skip if project not registered or paused
5. Resolve model (`journey_capture.model` or fall back to `models.evaluator`); reject Haiku
6. Resolve transcript path (with fallback for empty path bug)
7. Read transcript → filter → format → truncate to 100K chars
8. Create LLM client via factory, run `NarrativeExtractor.extract()`
9. Save narrative to JSONL via `save_narrative()`
10. Run `cleanup_old_narratives()` to prune entries older than 90 days
11. Exit 0 always (never disrupt the user's Claude Code session)

### Configuration

```yaml
# ~/.social-hook/config.yaml
journey_capture:
  enabled: false        # Default off (opt-in)
  model: null           # null = use evaluator model
```

The `JourneyCaptureConfig` dataclass in [config/yaml.py](../src/social_hook/config/yaml.py):

```python
@dataclass
class JourneyCaptureConfig:
    enabled: bool = False
    model: Optional[str] = None  # None = use evaluator model
```

When `model` is set, it must use `provider/model-id` format and is validated by `parse_provider_model()`.

---

## Consolidation Processing

When the Evaluator marks a commit as `consolidate` or `deferred`, the decision is stored with `processed = 0`. The consolidation processor runs during `scheduler-tick` and batches these unprocessed decisions per project.

### Architecture

```
scheduler-tick
    │
    ├── Promote deferred drafts (FIFO auto-promotion)
    │
    ├── Post due drafts (existing)
    │
    └── Consolidation processing
            │
            ├── Query unprocessed decisions (consolidate/deferred, processed=0)
            │   grouped by project_id, limited by batch_size
            │
            ├── For each project batch:
            │   ├── Mode: re_evaluate
            │   │   └── Send batch to Evaluator with full context
            │   │       (commit_summary for each decision + recent project context)
            │   │       → Evaluator decides: post_worthy (trigger draft) or skip
            │   │
            │   └── Mode: notify_only
            │       └── Send notification summarizing accumulated decisions
            │           via send_notification() (Web + Telegram)
            │
            └── Mark decisions as processed (processed=1, processed_at, batch_id)
```

### Configuration

```yaml
# In ~/.social-hook/config.yaml
consolidation:
  enabled: false           # Default off — opt-in
  mode: notify_only        # "re_evaluate" or "notify_only"
  batch_size: 20           # Max decisions per project per tick
```

### Two Modes

| Mode | Behavior | When to Use |
|------|----------|-------------|
| `re_evaluate` | Batched decisions are sent back to the Evaluator with accumulated context (commit summaries, project state). The Evaluator decides if the batch is now post-worthy as a combined narrative. | Active projects where consolidation decisions should eventually become posts |
| `notify_only` | A summary notification is sent to the user listing the accumulated decisions and their commit summaries. No LLM calls. | Projects where you want manual control over consolidated content |

### Database Fields (Migration 009)

| Column | Type | Purpose |
|--------|------|---------|
| `commit_summary` | TEXT | Brief 1-2 sentence summary from Evaluator, used for consolidation batching context |
| `processed` | INTEGER (0/1) | Whether the consolidation processor has handled this decision |
| `processed_at` | TEXT (ISO 8601) | When consolidation processing occurred |
| `batch_id` | TEXT | Groups decisions processed in the same batch |

Existing `consolidate`/`deferred` decisions are marked `processed = 1` by the migration to avoid reprocessing historical data.

### Phase 2: Auto-Consolidation

Time-window-based draft grouping runs as a safety net during scheduler ticks. When multiple pending drafts for the same project fall within a configurable time window, they are automatically consolidated.

```yaml
# In ~/.social-hook/config.yaml
consolidation:
  auto_consolidate_drafts: true    # Enable time-window grouping (default: true)
  consolidate_approved: false      # Include approved drafts (default: false)
  time_window_hours: 4.0           # Grouping window size (default: 4.0)
  time_window_max_drafts: 3        # Max drafts before auto-consolidation triggers (default: 3)
```

### Lock Pattern

Consolidation processing inherits the scheduler's existing lock pattern:
- Lock file: `~/.social-hook/scheduler.lock`
- Consolidation runs within the same tick as draft posting
- No separate lock needed — the scheduler lock prevents concurrent ticks

---

## Platform Adapter Factory

The `adapters/platform/factory.py` module extracts adapter creation from the scheduler, providing a centralized factory for platform posting adapters.

### Architecture

```python
# src/social_hook/adapters/platform/factory.py
def create_adapter(platform: str, config) -> PlatformAdapter:
    """Create a platform adapter by name.
    Routes platform name to adapter class with lazy imports.
    Extracts credentials from config.env.
    """
```

| Platform | Adapter | Credentials |
|----------|---------|-------------|
| `x` | `XAdapter` | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` |
| `linkedin` | `LinkedInAdapter` | `LINKEDIN_ACCESS_TOKEN` |

The factory uses lazy imports to avoid requiring all platform dependencies at import time. Unknown platform names raise `ConfigError`.

---

## Evaluator Rework

The evaluator rework introduces a structured output format with per-target actions, hold mechanisms, and queue management.

### New Evaluator Output Format

The evaluator produces a structured response with three sections:

```json
{
  "commit_analysis": {
    "summary": "Brief commit description",
    "episode_tags": ["milestone", "demo_proof"],
    "reasoning": "Why this decision was made"
  },
  "targets": {
    "default": {
      "action": "draft",
      "reason": "Significant feature milestone",
      "arc_id": "arc_123",
      "new_arc_theme": null,
      "consolidate_with": []
    }
  },
  "queue_actions": [
    {"action": "supersede", "draft_id": "draft_abc", "reason": "Replaced by this commit"}
  ]
}
```

### New Schema Columns

**Decisions table (migration 012 + 017):**

| Column | Type | Purpose |
|--------|------|---------|
| `episode_tags` | TEXT (JSON array) | Multiple episode types per commit (replaces single `episode_type`) |
| `targets` | TEXT (JSON object) | Per-target action decisions |
| `consolidate_with` | TEXT (JSON array) | IDs of held decisions to absorb |
| `reference_posts` | TEXT (JSON array) | IDs of previous posts to reference (migration 017) |

**Drafts table (migration 012):**

| Column | Type | Purpose |
|--------|------|---------|
| `is_intro` | INTEGER (0/1) | Whether this is an audience introduction draft |
| `vehicle` | TEXT | Content vehicle type: single, thread, article (decided pre-drafting) |
| `reference_type` | TEXT | Cross-post reference: quote or reply (narrowed from old `post_format`) |
| `reference_files` | TEXT (JSON array) | Per-draft reference file paths for context enrichment |
| `reference_post_id` | TEXT | Links to a reference post (for quote/reply reference types) |

### Hold Mechanism

Decisions with action `hold`, `consolidate`, or `deferred` are stored as held decisions. They accumulate until:
- A draftable commit absorbs them (via `consolidate_with`)
- The consolidation processor handles them in a batch
- The hold limit (`max_hold_count`, default 5) is reached — new holds forced to `skip`

> **Terminology:** "Deferred" in this section refers to a **deferred decision** — the evaluator deferring judgment on a commit. This is distinct from a **deferred draft** (`DraftStatus.DEFERRED`), which is a draft created when scheduling capacity is exhausted (`max_per_week` limit hit). Deferred drafts are auto-promoted by `promote_deferred_drafts()` when slots open up.

### Queue Actions

The evaluator can manage existing drafts during evaluation:

| Action | Effect | Use Case |
|--------|--------|----------|
| `supersede` | Sets draft status to `superseded` | New commit replaces pending draft |
| `drop` | Sets draft status to `cancelled` with reason in `last_error` | Draft no longer relevant |
| `merge` | Groups drafts via `merge_group`, creates consolidated replacement via drafter, marks originals as `superseded` | Combine related pending drafts into a stronger single post |

Merge actions use `merge_group` (string label grouping drafts into consolidation units) and `merge_instruction` (creative direction for the drafter). See [Merge Queue Action](#merge-queue-action) for full execution details.

### Intro Lifecycle

Projects track `audience_introduced` (boolean on `projects` table). When `False`:
1. First draftable decision creates an intro draft (`is_intro=True` on the draft)
2. `audience_introduced` flips to `True` on intro draft creation
3. If the intro draft is rejected, cascade re-draft: `audience_introduced` resets to `False`, triggering a new intro draft on next evaluation

### Vehicle Resolution and Reference Type Assignment

Vehicle (`single`, `thread`, `article`) is resolved **before drafting** via `resolve_vehicle()` in `vehicle.py` — not at scheduling time. The three-tier fallback is: operator choice > evaluator suggestion > drafter decides. The resolved vehicle is stored on the draft's `vehicle` column.

Reference type (`quote`, `reply`) is orthogonal to vehicle and is assigned for arc continuations: the scheduler looks up the most recent posted draft for the same arc and platform. The first arc continuation uses `quote`; subsequent ones use `reply`. The scheduler calls `post_by_vehicle()` which handles reference wrapping for any vehicle, with automatic fallback: if the adapter does not support the chosen `ReferenceType`, it falls back to `LINK`.

`assign_post_format()` has been deleted. The old 4-value `post_format` column (single/thread/quote/reply) has been split into two orthogonal columns: `vehicle` (content shape) and `reference_type` (cross-post linkage).

### Post Now Action

`post_now` uses the schedule-for-now pattern: sets draft to `status="scheduled"` with `scheduled_time=now(UTC)`, then calls `scheduler_tick(draft_id=<id>)` inline. The `draft_id` parameter on `scheduler_tick()`:
- Uses a per-draft lock path (`post_now_{draft_id}.lock`) to avoid contention with the cron-based tick
- Skips `promote_deferred_drafts()` and `_drain_deferred_evaluations()`
- Fetches the target draft directly instead of `get_due_drafts()`
- Uses the same `_post_draft()`, retry, and notification logic as the cron tick

Available via: bot (`btn_post_now`), CLI (`social-hook draft post-now`), web UI (`ActionButton` in draft panel).

### Capability Registry

`PostCapability` and `MediaMode` are frozen dataclasses in `adapters/models.py`. `PostCapability` has fields: `name: str`, `media_modes: tuple[MediaMode, ...]`, `description: str = ""`, `auto_postable: bool = True`. Each `PlatformAdapter` implements `capabilities()` returning its supported capabilities and media modes. Module-level constants (`SINGLE`, `THREAD`, `ARTICLE`, `QUOTE`, `REPLY`, `RESHARE`, `SINGLE_IMAGE`, `MULTI_IMAGE`, `GIF`, `VIDEO`) provide reusable building blocks. `ARTICLE` has `auto_postable=False` — articles create advisory items instead of being posted.

`PLATFORM_VEHICLE_SUPPORT` in `config/platforms.py` maps platform names to their supported vehicle capabilities (replaces the old `PLATFORM_THREAD_SUPPORT`):

| Platform | Vehicles |
|----------|----------|
| x | SINGLE, THREAD, ARTICLE |
| linkedin | SINGLE, ARTICLE |

Used by: `build_platform_summaries()` for evaluator context, `validate_draft_for_vehicle()`, `materialize_vehicle_artifacts()`, Section U E2E tests.

### Pending Draft Context Configuration

New context config fields control how pending drafts appear in evaluator prompts:

```yaml
context:
  pending_draft_detail: full_content   # full_content or summary
  arc_context_chars: 500               # Max chars of arc context per draft
  pending_drafts_cap: 10               # Max pending drafts in context
  max_hold_count: 5                    # Max held decisions before forcing skip
```

---

## Historical Commit Importing

Projects installed mid-development have no decision history for prior commits. Historical commit importing backfills the decisions table so the full project timeline is visible.

### Import Operation

The import process reads git log for a project's repository, identifies commits that have no corresponding decision row, and inserts them in batch as `decision='imported'` entries via `insert_decisions_batch()`. Each imported decision records:

- `commit_hash`, `commit_message` — from git log
- `branch` — the branch specified during import (defaults to project's `trigger_branch` if set, otherwise all branches)
- `decision = 'imported'` — distinguishes from evaluator-created decisions
- `reasoning` — static string indicating the commit was historically imported
- `platforms = '{}'` — no platform actions taken

The `branch` column (added in migration 016) is populated on all imported decisions and is also available for evaluator-created decisions going forward.

### Branch Filtering

Decisions can be filtered by branch at all layers:

| Layer | Mechanism |
|-------|-----------|
| **Database** | `get_distinct_branches(project_id)` returns all unique branch values across decisions |
| **API** | `GET /api/projects/{id}/decisions?branch=develop` filters server-side. `GET /api/projects/{id}/decision-branches` returns available branches |
| **Web UI** | Branch filter dropdown on the decisions table. The project's `trigger_branch` (if set) is shown with an "(active)" suffix. Selecting a branch filters the decision list. |

### Evaluator Safety

Imported decisions are excluded from LLM context to avoid polluting evaluator and gatekeeper reasoning. `get_recent_decisions_for_llm(project_id)` explicitly filters out `decision='imported'` rows, ensuring only real evaluator decisions inform future evaluations.

### Web UI Integration

| Component | Behavior |
|-----------|----------|
| **Decision badge** | Imported decisions display a distinct "imported" badge/chip |
| **Stat cards** | Dashboard stat cards exclude imported decisions from counts (only real evaluator decisions counted) |
| **Import modal** | Accessible from the project detail page. Shows a preview of importable commits (via `GET import-preview`), allows branch selection, and triggers the import (via `POST import-commits`) |
| **Branch filter dropdown** | Appears above the decisions table when multiple branches exist. Lists all branches from `decision-branches` endpoint. The project's `trigger_branch` is annotated "(active)" |

### Import Preview & CLI

Before importing, users can preview what would be imported:

- **API**: `GET /api/projects/{id}/import-preview?branch=main` returns commits not yet in the decisions table
- **CLI**: `social-hook project import-commits --branch main` (add `--json` for machine-readable output, `--id` to specify project)

The CLI command calls the same `insert_decisions_batch()` function used by the API endpoint.

---

## Pipeline Rate Limits

Pipeline rate limits throttle evaluator LLM calls at the trigger entry point. This is distinct from [platform API rate limiting](#platform-api-rate-limiting) which handles 429 responses from downstream posting APIs.

### Config

New top-level section in `config.yaml`:

```yaml
rate_limits:
  max_evaluations_per_day: 15
  min_evaluation_gap_minutes: 10
  batch_throttled: false
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_evaluations_per_day` | int | 15 | Hard cap on auto-triggered evaluator LLM calls per calendar day (UTC). Manual evaluations are not gated but are tracked. |
| `min_evaluation_gap_minutes` | int | 10 | Minimum minutes between evaluator runs. Timer resets from the last completed evaluation. |
| `batch_throttled` | bool | false | When `true`, queued `deferred_eval` triggers are combined into a single evaluator call. When `false`, each is evaluated individually as slots open. |

### Rate Limit Gate

The gate runs at the top of `run_trigger()`, after config load and DB init but before any LLM call:

```
1. Trigger arrives (any source)
2. Is trigger_source "manual" or "drain"? → skip gate, proceed
3. Count today's auto evaluations (UTC calendar day) → >= max? → record deferred_eval, stop
4. Get last auto evaluation timestamp → gap not elapsed? → record deferred_eval, stop
5. Proceed with evaluation as normal
```

Implementation: `rate_limits.py:check_rate_limit()` returns a `RateLimitResult` (allowed/blocked with reason). The gate in `trigger.py` calls this before any LLM work.

### `trigger_source` Field

New column on `decisions` and `usage_log` tables. Tracks how the evaluation was initiated:

| Value | Meaning | Gated? |
|-------|---------|--------|
| `"commit"` | Auto-triggered by git commit hook | Yes |
| `"manual"` | User-initiated (CLI retrigger, web create-draft) | No (bypass) |
| `"drain"` | Scheduler drain of deferred evaluations | No (already checked) |

Extensible for future plugin triggers (e.g. `"plugin:hn-scanner"`).

### `deferred_eval` Decision Type

When the rate limit gate blocks a trigger, a `deferred_eval` decision is recorded:

- `decision = 'deferred_eval'` (new `DecisionType` enum value)
- `commit_hash` — the trigger's commit
- `reasoning` — why deferred (e.g. "Daily limit reached: 15/15" or "Gap not elapsed: 4m remaining")
- `trigger_source` — always `"commit"` (manual triggers bypass the gate)
- No LLM output fields (`angle`, `episode_type`, etc. are NULL)

Visible in CLI (`social-hook decision list` shows deferred badge), web dashboard (deferred_eval badge on decision cards), and the rate-limits status display.

### Scheduler Drain

Deferred evaluations are drained by the scheduler (single mechanism, no piggyback drain in `run_trigger()` to avoid race conditions):

1. `scheduler_tick()` checks for pending `deferred_eval` decisions when the gap timer has elapsed
2. For each deferred decision: calls `check_rate_limit()` — if blocked, stops draining
3. Deletes the `deferred_eval` decision (frees the UNIQUE constraint on `(project_id, commit_hash)`)
4. Calls `run_trigger()` with `trigger_source="drain"` (bypasses the gate)
5. The fresh `run_trigger()` produces a real decision (draft/hold/skip)

**Batch mode** (`batch_throttled: true`): All deferred decisions for the project are collected, deleted, and combined into a single synthetic `CommitInfo` (combined commit summaries in the message field). One evaluator call covers the batch.

**Individual mode** (`batch_throttled: false`): Each deferred decision is evaluated individually, one per available rate limit slot per scheduler tick.

### Scope

- **Global, not per-project.** The daily cap and gap timer span all projects. A user with 3 active projects pushing 5 commits each exhausts a 15/day cap quickly. Intentional for v1 — provides a hard cost ceiling.
- **UTC calendar day.** The "per day" count uses midnight-to-midnight UTC. The user's configured `scheduling.timezone` affects draft scheduling times but NOT the rate limit day boundary.
- **Paused projects.** Deferred evaluations from paused projects are skipped during drain (project.paused check in `run_trigger()`).

### Interface Parity

| Interface | Implementation |
|-----------|---------------|
| **CLI** | `social-hook rate-limits` — shows today's usage, remaining slots, gap timer, deferred count. Supports `--json`. |
| **Web dashboard** | `RateLimitCard` on home page (clickable to settings). `RateLimitsSection` in settings with editable fields. `deferred_eval` badge on decision cards. |
| **API** | `GET /api/rate-limits/status` — returns current counts, limits, gap timer, deferred eval count. |

---

## Merge Queue Action

The merge queue action allows the evaluator to consolidate multiple pending drafts into replacement drafts via the drafter. The evaluator groups drafts thematically using `merge_group` labels and provides creative direction via `merge_instruction`.

### Schema: `merge_group` and `merge_instruction`

Two optional fields on `QueueAction`:

```python
class QueueAction(BaseModel):
    action: Literal["supersede", "merge", "drop"]
    draft_id: str
    reason: str
    merge_group: str | None = None       # groups drafts into consolidation units
    merge_instruction: str | None = None  # creative direction for the drafter
```

`merge_group` is a string label (e.g. `"A"`, `"B"`) scoping merge actions into consolidation units. All merge actions sharing a `merge_group` within the same target key are processed together. The label is only meaningful within its target key — no cross-target collision.

`merge_instruction` is the evaluator's editorial direction to the drafter. Only the first action in a merge group needs it; if multiple provide it, the first non-null one is used.

### Execution Flow

After the evaluator returns, before the current commit's own drafting:

```
1. Collect all merge actions from queue_actions, grouped by merge_group
2. For each merge group:
   a. Load referenced drafts and their parent decisions from DB
   b. Validate: drafts exist, are in "draft" status, belong to this project
   c. Sub-group by platform (safety net for cross-platform merge groups)
   d. For each platform sub-group (skip if <2 drafts):
      i.   Resolve platform config
      ii.  Build synthetic evaluation (merge_instruction → angle, episode_type=None)
      iii. Build DraftingIntent via intent_from_merge(), call draft() (bypasses content filter)
      iv.  Insert replacement draft, link to most recent decision
      v.   Mark original drafts as "superseded"
      vi.  Emit data_change events
3. Proceed with current commit's evaluation/drafting as normal
```

Implementation: `_execute_merge_groups()` in `trigger.py`.

### Drafter Context for Merge

The drafter receives merge context through existing fields — no modifications to `Drafter.create_draft()` or `assemble_drafter_prompt()`:

| Merge concept | Mapped to field | How drafter sees it |
|---|---|---|
| Creative direction | `intent.angle` | User message: "Angle: Combine into a single developer experience narrative..." |
| Original draft text | `commit.diff` | System prompt: "### Diff" section (truncated to 8000 chars) |
| Source commit info | `commit.message` | User message: "Commit: merge-abc123 - Merge of N drafts: ..." |

### `drafting.py` Unified Entry Point

The drafting pipeline has a single public entry point: `draft(intent: DraftingIntent, ...) -> list[DraftResult]`. The old two-layer split (`draft_for_platforms()` → `_resolve_and_filter_platforms()` → `_draft_for_resolved_platforms()`) has been replaced. Platform resolution and content filtering are now the responsibility of `DraftingIntent` builder functions in `drafting_intents.py`. Merge execution uses `intent_from_merge()` to construct the intent, then calls `draft()` directly.

### Synthetic Objects

Merge execution builds a `DraftingIntent` via `intent_from_merge()` and synthetic commit objects to carry context through the drafting pipeline:

- **`intent_from_merge()`**: `merge_instruction` maps to `intent.angle`. Decision angles are combined as fallback. `episode_type` is `None` — avoids coupling to a field being deprecated by the targets design in favor of `episode_tags`.
- **Synthetic `CommitInfo`**: original draft contents concatenated into `diff` field. Commit message describes the merge source (e.g. "Merge of 3 drafts: draft_1, draft_2, draft_3").

---

## Targets System Architecture

> Multi-account, multi-destination content flows with per-target content strategies. See [TARGETS_DESIGN](research/TARGETS_DESIGN.md) for the full specification.

### Config Model

The config model extends with five new top-level sections:

```yaml
platform_credentials:    # Static app credentials (client_id, client_secret)
  x-main:
    platform: x
    client_id: ${X_CLIENT_ID}
    client_secret: ${X_CLIENT_SECRET}

accounts:                # Authenticated presences on platforms
  product:
    platform: x
    app: x-main          # references platform_credentials
    tier: basic
    identity: acme

targets:                 # Atomic pipeline units
  main-timeline:
    account: product     # references accounts entry
    primary: true
    destination: timeline
    strategy: product-news
    frequency: moderate
    scheduling:
      max_posts_per_day: 2
      min_gap_minutes: 120

  x-preview:             # Preview mode — no account, real platform constraints
    platform: x          # direct platform name (required when account is empty)
    primary: true
    strategy: building-public

content_strategies:      # Named content approaches
  building-public:
    audience: "Fellow developers"
    voice: "Transparent, reflective"
    angle: "Behind the scenes"
    post_when: "Interesting technical decisions"
    avoid: "Polished marketing speak"

platform_settings:       # Per-platform cross-account settings
  x:
    cross_account_gap_minutes: 30
```

Config models are defined in `config/` — `PlatformCredentialConfig`, `AccountConfig`, `TargetConfig`, `ContentStrategyConfig`, `PlatformSettingsConfig`.

`TargetConfig.account` is optional (default `""`). When empty, `TargetConfig.platform` identifies the platform directly — the target is in **preview mode**. Validation requires that at least one of `account` or `platform` is non-empty.

**Resolution helpers** (in `config/targets.py`):

| Helper | Signature | Purpose |
|--------|-----------|---------|
| `resolve_target_platform(target, config)` | `(TargetConfig, Config) -> str` | Returns the platform name — from the account's platform if account is set, or from `target.platform` directly. |
| `resolve_default_platform(config)` | `(Config) -> str` | Primary target's platform > first target's platform > `"x"`. Used by content operations when no specific target is in scope. |
| `is_default_target_preview(config)` | `(Config) -> bool` | True if the primary (or first) target has no account connected. Used to set `preview_mode` on drafts from content operations and topic drafting. |

### Preview Mode

Preview is a target state (no connected account), not a platform. All drafts use real platform constraints (character limits, thread support, media formats).

**Database:** The `preview_mode` column on `drafts` (migration `20260324093540_add_draft_preview_mode.sql`) tracks whether a draft was created for an accountless target. Existing `platform = 'preview'` drafts are migrated to `preview_mode = 1`.

**Draft model:** `Draft.preview_mode: bool = False` — serialized as `1`/`0` in DB, included in `to_dict()`/`from_dict()`/`to_row()`.

**Posting guards:** All posting paths check `draft.preview_mode` (not `draft.platform == "preview"`). Preview-mode drafts cannot be approved, scheduled, or posted.

**Connect flow (`draft connect`):** Links an OAuth account to a preview-mode target:
1. Validates that the account's platform matches the draft's platform
2. Clears `preview_mode` on the draft via `clear_draft_preview_mode(conn, draft_id)`
3. Persists the target-to-account link via `save_config()` with `deep_merge=True`

Available via CLI (`social-hook draft connect <id> --account <name>`), web API (`POST /api/drafts/{id}/connect`), and bot ("Connect Account" button).

### Two-Stage Evaluation Pipeline

```
Stage 1: Commit Analysis
  Input:  commit diff, project brief, file summaries
  Output: commit classification (trivial/routine/notable/significant),
          freeform tags, updated project brief, rich commit analysis

              │ (if non-trivial)
              ▼

Stage 2: Strategy Evaluation
  Input:  commit analysis, strategy definitions, topic queue,
          per-strategy posting state, arc state
  Output: per-strategy decisions (skip/draft/hold),
          context_source per decision, queue actions
```

Stage 1 runs on every commit (configurable interval). Stage 2 is trigger-agnostic — fires from commits, time-based checks, topic maturity, operator suggestions, or plugins. Evaluates per **strategy**, not per target. 15 targets with 5 strategies = 5 LLM decisions.

**Strategy wiring:** All 5 call sites pass `strategies=config.content_strategies` to the evaluator:

| Call site | File |
|-----------|------|
| Main trigger pipeline | `trigger.py` |
| Consolidation processing | `consolidation.py` |
| Scheduler (time-based) | `scheduler.py` |
| Topic maturity | `topics.py` |
| Operator suggestions | `suggestions.py` |

### Target Routing Layer (`routing.py`)

Maps strategy decisions to targets. Fully deterministic, no LLM. Unit-testable.

1. Look up the target's strategy's decision
2. Check scheduling slots, per-account gap, cross-account platform gap
3. Check dependent targets (`source` set) — skip if source didn't fire
4. Apply queue health management (supersede/merge/drop)
5. Determine draft sharing groups (same strategy + same decision)
6. Output: per-target action, draft sharing groups, posting order

When a target has an empty `account`, routing constructs a synthetic `AccountConfig(platform=target.platform)` so the target can route to drafting. The platform is resolved via `resolve_target_platform()`.

### Shared-Group Drafting (`drafting.py`)

When multiple targets share a strategy group, `draft()` receives a `DraftingIntent` with multiple `PlatformSpec` entries. Instead of making one LLM call per platform, this mode:

1. **Picks the most constrained platform** (lowest `max_length`) as the "lead" — ensures adaptation only expands content (safe), never truncates (lossy).
2. **Calls the drafter once** for the lead platform.
3. **Adapts the lead draft** for each remaining platform:
   - Threaded lead (X) to non-thread target (LinkedIn): joins part texts with paragraph breaks, strips thread markers.
   - Single lead to thread-capable target: passes through as-is.
   - Applies per-platform character limits via `ResolvedPlatformConfig.max_length`.
   - Generates media once from the lead draft, shared across all platforms.
   - Each platform gets its own scheduling via `calculate_optimal_time()`.
4. **Each platform gets its own `Draft` row** with its own scheduling and `preview_mode` state.

When `shared_group=False` (default, backward compat), the current per-platform loop is unchanged.

### ContentSource Registry (`content_sources.py`)

The evaluator specifies what context the drafter needs via `context_source` — a composable list:

| Source Type | What it provides |
|-------------|-----------------|
| `brief` | Project brief sections |
| `commits` | Contributing commit files, git history |
| `topic` | Topic description from content topic queue |
| `operator_suggestion` | Operator-queued content idea |
| `positioning` | Value props, competitive angles (step 3) |

Each source type maps to a resolver function. Adding a new source type means adding one resolver — no schema changes.

### Adapter Registry (`AdapterRegistry`)

Process-scoped adapter caching — one instance per account, reused across scheduler ticks:

```python
class AdapterRegistry:
    _adapters: dict[str, PlatformAdapter] = {}

    def get(self, account_name, account, env) -> PlatformAdapter:
        if account_name not in self._adapters:
            self._adapters[account_name] = _create_adapter(account, env)
        return self._adapters[account_name]
```

Rate limit state and token state persist between ticks. All targets on the same account share one adapter instance.

### Project Brief (`llm/brief.py`)

Replaces the project summary. ~3-5K tokens, structured:

```
## Project Brief
### What It Does (user perspective)
### Key Capabilities
### Technical Architecture (system perspective)
### Current State
```

Seeded by discovery, incrementally updated by the commit analysis stage. Operator-editable. Stored in DB (same storage as current summary). "What It Does" and "Key Capabilities" seed brand-primary topics.

### Content Topic Queue (`topics.py`)

Persistent, user-reorderable queue of topics per strategy.

### New Database Tables

```sql
CREATE TABLE content_topics (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id),
    strategy       TEXT NOT NULL,
    topic          TEXT NOT NULL,
    description    TEXT,
    priority_rank  INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'uncovered'
                   CHECK (status IN ('uncovered','holding','partial','covered')),
    commit_count   INTEGER NOT NULL DEFAULT 0,
    last_commit_at TEXT,
    last_posted_at TEXT,
    created_by     TEXT NOT NULL DEFAULT 'discovery',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE content_suggestions (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    idea        TEXT NOT NULL,
    strategy    TEXT,
    source      TEXT NOT NULL DEFAULT 'operator',
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','evaluated','drafted','dismissed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE evaluation_cycles (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id),
    trigger_type TEXT NOT NULL,
    trigger_data TEXT,
    outcomes     TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE draft_patterns (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL REFERENCES projects(id),
    pattern_name     TEXT NOT NULL,
    description      TEXT,
    example_draft_id TEXT REFERENCES drafts(id),
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE system_errors (
    id         TEXT PRIMARY KEY,
    severity   TEXT NOT NULL CHECK (severity IN ('info','warning','error','critical')),
    message    TEXT NOT NULL,
    context    TEXT DEFAULT '{}',
    source     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE oauth_tokens (
    account_name   TEXT PRIMARY KEY,
    access_token   TEXT NOT NULL,
    refresh_token  TEXT NOT NULL,
    expires_at     TEXT,
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/projects/{id}/topics` | GET | List content topics for project, grouped by strategy |
| `/api/projects/{id}/topics` | POST | Add a content topic |
| `/api/projects/{id}/topics/{topic_id}` | PUT | Update topic (priority, status, description) |
| `/api/projects/{id}/suggestions` | GET/POST | List/create operator content suggestions |
| `/api/projects/{id}/evaluation-cycles` | GET | List evaluation cycles with per-strategy outcomes |
| `/api/projects/{id}/brief` | GET/PUT | View/edit project brief |

---

## Content Vehicles

Content vehicles define the shape of a draft: `single` (self-contained post), `thread` (multi-part narrative), or `article` (long-form structured content). Vehicle replaces the old `format_hint` concept with a first-class pipeline stage.

### Vehicle Pipeline (`vehicle.py`)

`src/social_hook/vehicle.py` is a domain module providing six functions that form the vehicle stage:

| Function | Purpose |
|----------|---------|
| `resolve_vehicle(evaluator_suggestion, operator_choice, capabilities)` | Three-tier fallback: operator > evaluator > None (drafter decides). Validates against platform capabilities. |
| `validate_draft_for_vehicle(content, vehicle, platform, char_limit)` | Pure function. Hard platform constraints only. Returns `VehicleValidation(valid, violation, suggested_vehicle)`. |
| `materialize_vehicle_artifacts(draft_id, vehicle, platform, content, capabilities, db)` | Creates/deletes draft parts. Deletes existing parts first (handles vehicle changes), then creates new parts for threads via `parse_thread_parts()`. |
| `parse_thread_parts(content, platform, thread_min=4)` | Platform-aware thread parsing: numbered format (`1/ ...`), `---` separators, or double-newline paragraphs. |
| `post_by_vehicle(adapter, draft, parts, media_paths, reference, dry_run, db)` | Posting orchestrator. Safety-net warning for non-auto-postable vehicles that reach the scheduler. Handles reference wrapping for any vehicle, thread part-result tracking. |
| `check_auto_postable(draft)` | Returns True if draft's vehicle is auto-postable on its platform. Uses `PLATFORM_VEHICLE_SUPPORT` — no adapter needed. |
| `handle_advisory_approval(conn, draft, config, scheduled_time)` | Creates advisory item, sets draft status to `advisory` (terminal), emits events. Called by all approval/scheduling paths when `check_auto_postable()` returns False. |
| `create_draft_advisory(draft, conn, config, dry_run, due_date)` | Low-level advisory item creation: inserts `AdvisoryItem`, emits `advisory/created` event, sends broadcast notification. |
| `_update_part_results(db, parts, part_results)` | Internal helper: updates `draft_parts` rows with `external_id`/`posted_at` after posting. |

### DraftingIntent Builders (`drafting_intents.py`)

`src/social_hook/drafting_intents.py` provides four builder functions that construct `DraftingIntent` from different entry points:

| Builder | Used by | Notes |
|---------|---------|-------|
| `intent_from_routed_targets(routed, decision_id, evaluation, config, conn)` | Commit trigger (targets), suggestion eval, topic maturity, consolidation | Groups by `draft_group`, resolves content sources per strategy, detects preview targets |
| `intent_from_platforms(evaluation, decision_id, config)` | Commit trigger (no targets), summary trigger | Builds from `config.platforms` when no targets configured |
| `intent_from_decision(decision, config, conn, target_platform)` | Web Create Draft, Telegram redraft, CLI redraft, intro lifecycle | Sets `include_project_docs=True` |
| `intent_from_merge(drafts, decisions, merge_instruction, config, platform)` | Merge execution in `trigger_side_effects.py` | Combines merge instruction + decision angles |

### Advisory Items

Advisory items are operator action items for tasks the system cannot automate (e.g., posting articles to X's article editor, setting up a LinkedIn newsletter). Stored in the `advisory_items` table.

**Database schema:**

| Column | Type | Purpose |
|--------|------|---------|
| `id` | TEXT PK | Unique identifier |
| `project_id` | TEXT FK | Links to projects |
| `category` | TEXT | `platform_presence`, `product_infrastructure`, `content_asset`, `code_change`, `external_action`, `outreach` |
| `title` | TEXT | Short description |
| `description` | TEXT | Detailed instructions |
| `status` | TEXT | `pending`, `completed`, `dismissed` |
| `urgency` | TEXT | `blocking`, `normal` |
| `created_by` | TEXT | Origin: `system`, `evaluator`, `operator` |
| `linked_entity_type` / `linked_entity_id` | TEXT | Optional link to a draft, decision, etc. |

**Integration:** Non-auto-postable vehicles (e.g., articles where `PostCapability.auto_postable=False`) are intercepted at **approval time**, not posting time. Every approval/scheduling path (bot buttons, CLI commands, web endpoints) checks `check_auto_postable(draft)` before changing status. If False, `handle_advisory_approval()` creates the advisory item immediately and sets `status="advisory"` (terminal) — the draft never enters the scheduler. The scheduler's `_post_draft()` has a safety-net check for drafts that bypass the approval-time check. Advisory items with `due_date` (from quick-approve/schedule) appear in the "Upcoming" section of the advisory page with a countdown timer. Advisory items are surfaced via CLI (`social-hook advisory list/complete/dismiss`), web UI (dedicated advisory page with Upcoming/Action Required grouping), and notifications.

### File Reader (`file_reader.py`)

`src/social_hook/file_reader.py` is a reusable module (zero social-hook imports) for token-budgeted file reading:

- `read_files_within_budget(paths, base_dir, max_tokens, extensions, count_fn)` -- Reads files within a token budget. Features: path traversal protection via `resolve().is_relative_to()`, deduplication by resolved path, skips binary files by extension, truncates last file to fit budget.
- Used by: `draft()` for per-draft `reference_files`, `generate_brief_from_docs()` for non-git project briefs, `assemble_drafter_prompt()` for `prompt_docs`.

### Non-Git Project Support

`register_project()` in `db/operations.py` no longer requires a git repository. If `is_git_repo(path)` returns `False`:
- `repo_origin` is set to `None` (no worktree grouping)
- No git hook is installed
- Git operations throughout the pipeline are guarded with `is_git_repo()` checks

`collect_git_stats()` in `trigger_git.py` returns git-derived metrics (commit count, contributor count, branch count) for git projects and `None` for non-git directories. Used by brief generation to provide project statistics.

Non-git projects use the Create Flow for content creation (no commit trigger) and `generate_brief_from_docs()` to build their brief from uploaded `prompt_docs` instead of git history.

### Create Flow

Operator-initiated content creation that bypasses the evaluator entirely.

**Entry points:**
- Web: `POST /api/projects/{id}/create-content` (body: `{idea, vehicle?, files?, platform?}`)
- CLI: `social-hook content create --idea "..." [--vehicle thread] [--files guide.md]`

**Flow:** Constructs a `DraftingIntent` directly with operator-provided fields (idea to angle, optional vehicle, optional reference files). Calls `draft()` -- same pipeline as commit-triggered drafts from vehicle resolution onward. Returns 202 with task_id (web) or blocks until complete (CLI).

### Universal Brief System

The project brief system is freeform (not hardcoded to 4 software-project sections). Key changes:

- **Freeform sections:** Brief sections are discovered organically by the commit analyzer, not constrained to a fixed template.
- **Brief update gate:** Uses `brief_update.sections_to_update` and `brief_update.new_facts` from the commit analyzer output, replacing the old `episode_tags`-based gate.
- **`generate_brief_from_docs()`** in `llm/brief.py`: Generates a brief from `prompt_docs` files for non-git projects (uses `read_files_within_budget()` to load docs within token budget).
- **`prompt_docs`**: Operator-manageable file inclusion list stored per-project in DB. Files in this list are loaded into drafter context. Manageable via CLI (`social-hook project prompt-docs`) and web API (`GET/PUT /api/projects/{id}/prompt-docs`).

---

## Day 2 Considerations

The following items are deferred but should inform current architecture:

### Rate Limit State Persistence

**Current**: Rate limit state is in-memory, resets on restart.

**Future**: Persist to database for cross-session backoff resumption.

```sql
-- Future table
CREATE TABLE rate_limit_state (
    api_name      TEXT PRIMARY KEY,
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_attempt  TEXT,
    backoff_until TEXT
);
```

### Telegram Conversation Persistence

**Current**: Using Telegram-native threading (reply chains).

**Future**: May need to persist conversation history for:
- Context restoration after bot restart
- Analytics on conversation patterns
- Training data collection

### Engagement Metrics

**Current**: Not tracking post performance.

**Future**: Track likes, retweets, replies for:
- Learning what content resonates
- Informing future content decisions
- Analytics dashboard

```sql
-- Future table
CREATE TABLE post_metrics (
    post_id      TEXT PRIMARY KEY REFERENCES posts(id),
    likes        INTEGER DEFAULT 0,
    retweets     INTEGER DEFAULT 0,
    replies      INTEGER DEFAULT 0,
    impressions  INTEGER DEFAULT 0,
    fetched_at   TEXT NOT NULL
);
```

### First-Time Setup Wizard (Implemented)

**Status**: Implemented in WS4 via `social-hook setup`.

Interactive setup flow using Rich + InquirerPy + Typer:
- Model selection with QuickStart/Advanced paths
- Provider auto-detection (Claude CLI, Ollama)
- API credential configuration (only keys needed for chosen providers)
- Voice/style questionnaire
- Platform connection (X, LinkedIn, media generation)
- Scheduling preferences
- Component installation (Claude Code hook, cron scheduler, Telegram bot)

### LLM Provider Abstraction

The system supports multiple LLM providers via an abstract `LLMClient` interface.

#### Architecture

```
Evaluator/Expert → Drafter → Gatekeeper
        ↓              ↓          ↓
        └──────────────┼──────────┘
                       ↓
              LLMClient.complete()  (base.py)
              Returns NormalizedResponse
                       ↓
    ┌──────────┬──────────────┬─────────────┐
    │          │              │             │
 ClaudeClient ClaudeCliClient OpenAICompat  (future)
 Anthropic SDK  subprocess   OpenAI/Router
                             /Ollama
```

#### Normalized Response

All providers return `NormalizedResponse`:
- `content`: list of `NormalizedToolCall` (type="tool_use", name, input)
- `usage`: `NormalizedUsage` (input_tokens, output_tokens, cache tokens, cost_cents)
- `raw`: Original provider response for debugging

This maps directly to `extract_tool_call()` in `base.py` — role agent code is unchanged.

#### Factory

`create_client("provider/model-id", config) -> LLMClient`

Parses the provider prefix, validates credentials, and returns the appropriate client. Lazy imports prevent circular dependencies.

#### Provider Details

| Provider | Client Class | Auth | Notes |
|----------|-------------|------|-------|
| `anthropic` | `ClaudeClient` | `ANTHROPIC_API_KEY` | Supports caching, direct SDK |
| `claude-cli` | `ClaudeCliClient` | Subscription | subprocess, ~4-8s latency. Uses `--output-format stream-json` (NDJSON) to avoid string truncation in CLI bug #2904. Uses `--setting-sources local` to skip MCP server init (~7s faster, ~5000 fewer tokens). Text accumulated from `content_block_delta` events; usage from `result` event. Minimum Claude Code version: 2.1.79 (fixes `claude -p` subprocess hang when spawned without explicit stdin). |
| `openai` | `OpenAICompatClient` | `OPENAI_API_KEY` | Schema conversion |
| `openrouter` | `OpenAICompatClient` | `OPENROUTER_API_KEY` | Same client, different base_url |
| `ollama` | `OpenAICompatClient` | None | Local, auto-discoverable |

#### Model Catalog

`catalog.py` provides rich metadata per model: display names, costs, context window size, capability flags. Used by the setup wizard for model selection UI.

### Messaging Platform Abstraction

The system supports multiple messaging platforms via an abstract `MessagingAdapter` interface in `src/social_hook/messaging/`. Mirrors the LLM layer pattern exactly.

#### Architecture

```
Bot Daemon / Trigger / FastAPI
        |
        v
  MessagingAdapter.send_message()  (base.py)
  Returns SendResult
        |
  ┌─────┼──────────────┐
  |     |               |
TelegramAdapter  WebAdapter   SlackAdapter (stub)
Direct HTTP      SQLite       slack-bolt
```

#### Normalized Types

All adapters use shared types from `base.py`:
- `OutboundMessage`: text + parse_mode + buttons (list of `ButtonRow`)
- `SendResult`: success + message_id + error + raw
- `InboundMessage`: chat_id + text + sender info
- `CallbackEvent`: chat_id + callback_id + action + payload
- `Button` / `ButtonRow`: Platform-agnostic button layout
- `PlatformCapabilities`: Declares what each platform supports

#### Factory

`create_adapter("telegram", config) -> MessagingAdapter`

Routes platform name to the appropriate adapter class. Lazy imports prevent circular dependencies. Only `ConfigError` imported from social_hook.

#### Platform Details

| Platform | Adapter Class | Auth | Status |
|----------|--------------|------|--------|
| `telegram` | `TelegramAdapter` | `TELEGRAM_BOT_TOKEN` | Full implementation |
| `web` | `WebAdapter` | None (built-in) | Full implementation (SQLite-backed) |
| `slack` | `SlackAdapter` | `SLACK_BOT_TOKEN` | Stub (raises `NotImplementedError`) |

#### Slack Stub

The Slack adapter (`messaging/slack.py`) is a stub that:
- Requires `slack-bolt` package (`pip install social-hook[slack]`)
- Raises `ConfigError` on init if `slack-bolt` is not installed
- Returns real `PlatformCapabilities` (40K char limit, no HTML, 75-char buttons)
- Raises `NotImplementedError` on all send/edit/callback methods
- See [ROADMAP.md](ROADMAP.md) for full Slack implementation status

### Telegram Webhook Mode

**Current**: Long-polling (bot continuously polls for updates).

**Future**: For cloud deployment, switch to webhook mode.

```yaml
telegram:
  mode: "polling"    # Day 1
  # mode: "webhook"  # Day 2
  # webhook_url: "https://your-app.com/telegram"
```

### Testing Strategy

**Status**: Decided. See [REQUIREMENTS.md Functional Testing Strategy](REQUIREMENTS.md#functional-testing-strategy).

**Summary**:
- Functional testing with real integrations (no mocks)
- Dry-run mode for full pipeline execution without posting
- Human evaluation for LLM output quality
- Real repos as test data (this repo first, then user projects, then public GitHub repos)

**CLI interface:**
```bash
# Test a specific commit
social-hook test --repo /path/to/repo --commit <hash>

# Test a range of commits
social-hook test --repo /path/to/repo --from <hash> --to <hash>

# Test most recent N commits
social-hook test --repo /path/to/repo --last 5
```

**Flags:**
| Flag | Purpose |
|------|---------|
| `--dry-run` | Default behavior - no posting, no Telegram |
| `--verbose` | Show full evaluation reasoning |
| `--output <path>` | Save outputs to file (for golden file comparison) |
| `--compare <path>` | Diff against previous golden output |

**Output format:**
```
Commit: abc123 "Add user authentication"
Phase detected: build (confidence: 0.72)
Decision: post_worthy
Episode type: milestone
Draft:
---
Authentication is live. Sessions, tokens, the works.
Here's how it fits together: [diagram suggestion]
---
Media: mermaid (architecture diagram)
Scheduled: Tuesday 9:00 AM
```

**Exit codes:**
- `0`: All commits processed successfully
- `1`: System error (API failure, missing config)
- No exit code for "bad" LLM output - that requires human judgment

---

## Appendix: ID Generation

Use UUIDs for all primary keys:

```python
import uuid

def generate_id() -> str:
    return str(uuid.uuid4())
```

Or prefixed IDs for readability:

```python
def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

# Examples:
# draft_a1b2c3d4e5f6
# decision_f6e5d4c3b2a1
# arc_123456789abc
```

---

## CI/CD & Release Automation

### GitHub Actions Workflows

Three workflows in `.github/workflows/`:

**`ci.yml`** — Runs on every push/PR to `main`:
- **lint**: `ruff check` + `ruff format --check` on `src/` and `tests/`
- **typecheck**: `mypy src/social_hook/`
- **test**: `pytest tests/ -q` across Python 3.10, 3.11, 3.12

**`release-please.yml`** — Runs on push to `main`:
- Uses `googleapis/release-please-action@v4`
- Reads `release-please-config.json` (release type, changelog sections) and `.release-please-manifest.json` (current version)
- Opens/updates a Release PR with version bump in `pyproject.toml` + `__init__.py` and auto-generated CHANGELOG.md
- Merging the Release PR creates a git tag and GitHub Release

**`publish.yml`** — Runs on GitHub Release `published` event:
- Builds wheel + sdist via `python -m build`
- Publishes to PyPI via trusted publishing (`pypa/gh-action-pypi-publish@release/v1`)
- No API tokens needed — uses OIDC identity from the `pypi` GitHub environment

### Pre-Commit Hooks

`.pre-commit-config.yaml` runs two hook sets:

1. **ruff** (pre-commit stage): lint with `--fix` + format
2. **conventional-pre-commit** (commit-msg stage): validates commit messages match conventional commit format

Installed via:
```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

### Release Flow

```
commit → pre-commit hooks → push to main → CI checks
                                         → Release Please updates PR
merge Release PR → git tag + GitHub Release → publish.yml → PyPI
```
