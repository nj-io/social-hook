# Reusable Components

> Guide for copying the multi-provider LLM layer into other Python projects.
> This document is kept up to date by LLMs via CLAUDE.md instructions.

## Changelog

| Date | Change |
|------|--------|
| 2026-04-08 | Updated: Platform Adapter Layer — `ThreadResult` removed, `PostResult` gains `part_results` field. Added File Reader section (`file_reader.py`). |
| 2026-03-31 | Added Task Stage Tracking section — reusable per-task stage progress via emit_task_stage + useBackgroundTasks. |
| 2026-03-28 | Added Git Commit Parser section (trigger_git.py). Added enum_value() to parsing.py utilities. trigger.py decomposed: 1983 → 1050 lines via 6 sibling modules. |
| 2026-03-28 | Added OAuth 2.0 PKCE Utilities section (oauth_pkce.py). Added DryRunProxy section (dry_run.py). |
| 2026-03-28 | Added SQL Migration Runner section (migrations.py). Added Scheduling Algorithm section (find_optimal_slot in scheduling.py). |
| 2026-03-28 | Added Pipeline Diagnostics section (diagnostics.py). Generic check-registry for structured pipeline health warnings. |
| 2026-03-28 | Added Generic Adapter Registry section (registry.py). Platform, media, and messaging factories refactored to use registry dispatch instead of if/elif chains. |
| 2026-03-26 | Added Unified Logging section (logging.py + error_feed.py). Restructured System Error Feed as standalone subsection with updated fields (component, run_id, on_persist, filter params). |
| 2026-03-24 | Added ContentSource registry (content_sources.py) as reusable component. Updated Platform Adapter Layer with LinkedInAdapter entity parameter. |
| 2026-03-23 | Added System Error Feed section (error_feed.py) as reusable component |
| 2026-03-13 | `MessagingAdapter` refactored to Template Method: `send_message`/`edit_message`/`send_media` are now concrete (handle sanitization + format-error retry). Subclasses implement `_do_send_message`/`_do_edit_message`/`_do_send_media` and optionally override `sanitize_text()`/`_is_format_error()`. `TelegramAdapter._parse_response` fixed to check `{"ok": false}`. `_map_parse_mode` returns `None` for unknown modes. `base.py` now imports `logging` (still stdlib-only). |
| 2026-03-12 | Added `download_file()` method to MessagingAdapter (concrete default returning `None`) |
| 2026-03-05 | LLM layer abstracted: `complete()` signature cleaned (4 usage params removed), `extract_tool_call()` + `ToolExtractionError` moved to `base.py`, `agent.py` added, `cost_cents` added to `NormalizedUsage` |
| 2026-03-04 | Added Platform Adapter Layer section (posting adapters for X, LinkedIn) |
| 2026-02-26 | Added `gateway-context.tsx` and `use-data-events.ts` as reusable frontend modules |
| 2026-02-26 | Added Project Naming Constants section |
| 2026-02-21 | Added Handler Integration Pattern subsection; added `web.py` to Messaging Files to Copy table |
| 2026-02-20 | Added `send_media()` to MessagingAdapter and TelegramAdapter; added media fields to PlatformCapabilities |
| 2026-02-19 | Added Messaging Platform Layer section with factory + Telegram adapter |
| 2026-02-15 | Initial creation |

---

## Multi-Provider LLM Layer

### What It Does
A provider-agnostic abstraction for making LLM API calls with tool calling. Supports Anthropic (direct API), Claude Code CLI (subprocess), OpenAI, OpenRouter, and Ollama — all through a single `LLMClient.complete()` interface that returns normalized responses.

### Files to Copy

Copy these 6 files from `src/social_hook/llm/`:

| File | Purpose | Dependencies |
|------|---------|-------------|
| `base.py` | `LLMClient` ABC, `NormalizedResponse`, `NormalizedToolCall`, `NormalizedUsage`, `extract_tool_call()`, `ToolExtractionError` | None (stdlib only) |
| `catalog.py` | `ModelInfo`, `ProviderInfo`, `ProviderCompat`, static model registry | None |
| `factory.py` | `create_client()`, `parse_provider_model()` | `base.py`, lazy imports to provider clients |
| `claude_cli.py` | `ClaudeCliClient` — uses `claude -p` subprocess with `--output-format stream-json` (NDJSON) | `base.py` |
| `openai_compat.py` | `OpenAICompatClient` — OpenAI/OpenRouter/Ollama | `base.py`, `openai>=1.0.0` |
| `agent.py` | `SingleToolAgent` base class, `call_tool()` helper | `base.py` |

### What to Replace

1. **`ConfigError`** — All files import `from social_hook.errors import ConfigError`. Replace with your own exception class or a simple:
   ```python
   class ConfigError(Exception):
       pass
   ```

2. **Package paths** — Update `from social_hook.llm.X import Y` to your package name.

### Quick Start

```python
from your_package.llm.factory import create_client

# Create a client
client = create_client("claude-cli/sonnet", config)

# Make a call with tool calling
tools = [{"name": "my_tool", "description": "...", "input_schema": {...}}]
response = client.complete(
    messages=[{"role": "user", "content": "..."}],
    tools=tools,
    system="You are a helpful assistant.",
)

# Access normalized response
for block in response.content:
    if block.type == "tool_use":
        print(block.name, block.input)
```

### What NOT to Copy

These files are social-hook-specific and should NOT be copied:
- `client.py` — `ClaudeClient` with Anthropic SDK direct integration and pricing calculation
- `_usage_logger.py` — Usage logging helper (consolidates `log_usage()` for all callers)
- `evaluator.py`, `drafter.py`, `gatekeeper.py`, `expert.py` — Domain-specific role agents
- `schemas.py`, `prompts.py`, `dry_run.py` — Social-hook prompt logic

### Test Coverage

Copy the corresponding test files for the components you use:
- `tests/test_factory.py` — Parser and factory routing
- `tests/test_claude_cli_client.py` — CLI client (mocks subprocess)
- `tests/test_openai_compat_client.py` — OpenAI adapter (mocks OpenAI SDK)
- `tests/test_catalog.py` — Catalog data integrity

## Messaging Platform Layer

### What It Does
A platform-agnostic abstraction for sending messages, editing messages, handling button callbacks, and declaring platform capabilities. Mirrors the LLM layer pattern: ABC with normalized types, provider-specific implementations in separate modules.

### Files to Copy

Copy from `src/social_hook/messaging/`:

| File | Purpose | Dependencies |
|------|---------|-------------|
| `base.py` | `MessagingAdapter` ABC (Template Method: `send_message`/`edit_message`/`send_media` handle sanitization + retry; subclasses implement `_do_*` methods), `Button`, `ButtonRow`, `OutboundMessage`, `SendResult`, `InboundMessage`, `CallbackEvent`, `PlatformCapabilities` | None (stdlib + `logging`) |
| `factory.py` | `create_adapter()` — routes platform name to adapter class | `base.py`, lazy imports to adapters |
| `telegram.py` | `TelegramAdapter` — Telegram Bot API via direct HTTP | `base.py`, `requests` |
| `slack.py` | `SlackAdapter` — Slack Bot stub (raises `NotImplementedError`) | `base.py`, `slack-bolt>=1.18.0` |
| `web.py` | `WebAdapter` — SQLite-backed for web message polling (optional `scope_id` for session isolation) | `base.py`, `sqlite3` (stdlib) |

### What to Replace

1. **`ConfigError`** — `factory.py` imports `from social_hook.errors import ConfigError`. Replace with your own exception class or a simple:
   ```python
   class ConfigError(Exception):
       pass
   ```

2. **Package paths** — Update `from social_hook.messaging.X import Y` to your package name.

### Quick Start

```python
from your_package.messaging.base import (
    Button, ButtonRow, MessagingAdapter, OutboundMessage, PlatformCapabilities, SendResult,
)

# Implement an adapter for your platform
class MyAdapter(MessagingAdapter):
    platform = "my_platform"

    def _do_send_message(self, chat_id, message):
        # Your platform's send logic (text already sanitized by base)
        return SendResult(success=True, message_id="123")

    def _do_edit_message(self, chat_id, message_id, message):
        return SendResult(success=True)

    def answer_callback(self, callback_id, text=""):
        return True

    def get_capabilities(self):
        return PlatformCapabilities(max_message_length=2000)

    # Optional: override for platform-specific text escaping
    def sanitize_text(self, text, parse_mode):
        return text  # No-op default; override for e.g. Markdown escaping

    # Optional: override to detect format errors (triggers plain-text retry)
    def _is_format_error(self, result):
        return False  # No-op default

# Use it — callers always use the public API (send_message, not _do_send_message)
adapter = MyAdapter()
msg = OutboundMessage(
    text="Review this draft",
    buttons=[ButtonRow(buttons=[
        Button(label="Approve", action="approve", payload="draft_1"),
        Button(label="Reject", action="reject", payload="draft_1"),
    ])],
)
result = adapter.send_message("chat_123", msg)
```

### Media Support

`MessagingAdapter.send_media()` is a Template Method: it sanitizes the caption via `sanitize_text()`, delegates to `_do_send_media()`, and retries as plain text if `_is_format_error()` returns True. Adapters override `_do_send_media()` to support media uploads.

**Signature (public — callers use this):**
```python
def send_media(self, chat_id: str, file_path: str, caption: str = "",
               parse_mode: str = "markdown") -> SendResult:
```

**Override (subclasses implement this):**
```python
def _do_send_media(self, chat_id: str, file_path: str, caption: str = "",
                   parse_mode: str = "markdown") -> SendResult:
```

**Behavior:**
- Default `_do_send_media()` returns `SendResult(success=False, error="<platform> does not support media uploads")`.
- `TelegramAdapter` overrides it: uses `sendPhoto` for `.jpg`/`.jpeg`/`.png`/`.gif` files up to 10 MB, falls back to `sendDocument` for other types or oversized files.
- Uses multipart form upload (`requests.post` with `data=` + `files=`), 30s timeout.
- Returns `SendResult(success=False)` for missing files or network errors.

**PlatformCapabilities media fields:**
```python
supports_media: bool = True          # Whether the platform supports media uploads
max_media_per_message: int = 4       # Max media attachments per message
supported_media_types: list[str]     # File extensions (default: ["png", "jpg", "jpeg", "gif"])
```

### File Downloads

`MessagingAdapter` includes a concrete `download_file()` method with a default that returns `None`. Adapters override it to support file downloads by platform-specific ID.

**Signature:**
```python
def download_file(self, file_id: str, dest_dir: str) -> str | None:
```

**Behavior:**
- Default returns `None` (platform doesn't support downloads).
- `TelegramAdapter` overrides: downloads via Bot API `getFile` + HTTPS fetch, saves to `dest_dir/`, returns local path.
- Callers should check `if local_path:` before using the result.

### Handler Integration Pattern

To wire a new platform's inbound messages to existing handlers, use the `InboundMessage`/`CallbackEvent` types paired with a `MessagingAdapter`:

```python
from your_package.messaging.base import InboundMessage, CallbackEvent, MessagingAdapter

# At the platform boundary (e.g., webhook handler, polling loop):
# 1. Parse raw platform data into abstract types
msg = InboundMessage(
    chat_id="123",
    text="/review 42",
    sender_id="user_1",
    sender_name="Alice",
    message_id="msg_1",
    raw=raw_platform_data,  # Original dict for fallback access
)

# 2. Create the platform adapter
adapter: MessagingAdapter = create_adapter("telegram", config)

# 3. Pass both to handlers — handlers never see platform-specific types
handle_command(msg, adapter, config)
```

Handlers accept `(InboundMessage, MessagingAdapter, config)` for text commands or `(CallbackEvent, MessagingAdapter, config)` for button callbacks. They use the adapter to send responses via `adapter.send_message()`, `adapter.edit_message()`, and `adapter.answer_callback()`. This keeps all platform-specific conversion at the boundary (e.g., in a daemon or API server), not inside handler logic.

### What NOT to Copy

- `__init__.py` — Social-hook-specific re-exports (trivial to recreate)

### Test Coverage

Copy the corresponding test files:
- `tests/test_messaging_base.py` — All base types and ABC verification
- `tests/test_messaging_telegram.py` — Telegram adapter (mocks requests.post)
- `tests/test_messaging_factory.py` — Factory routing tests
- `tests/test_messaging_slack.py` — Slack stub tests

## WebSocket Gateway

### What It Does
A protocol-agnostic WebSocket gateway with hub/envelope pattern. Manages connections, channels, and message routing without framework dependencies.

### Files to Copy

Copy from `src/social_hook/messaging/`:

| File | Purpose | Dependencies |
|------|---------|-------------|
| `gateway.py` | `GatewayHub`, `GatewayEnvelope`, `GatewayConnection`, `GatewayTransport` protocol | None (stdlib only) |

### What to Replace

1. **Package paths** — Update `from social_hook.messaging.gateway import ...` to your package name.

### Quick Start

```python
from your_package.messaging.gateway import GatewayHub, GatewayEnvelope

hub = GatewayHub()

# In your WebSocket handler:
conn = await hub.connect(ws, client_id="abc", channels=["web"])

# Broadcast events:
envelope = GatewayEnvelope(type="event", channel="web", payload={"msg": "hello"})
await hub.broadcast(envelope, channel="web")
```

### Reusable Frontend Modules

Copy from `web/src/lib/`:

| File | Purpose | Dependencies |
|------|---------|-------------|
| `gateway-context.tsx` | `GatewayProvider` React context wrapping `GatewayClient`, connection lifecycle, listener registry | `websocket.ts` (your GatewayClient), React |
| `use-data-events.ts` | `useDataEvents` hook — debounced (500ms) entity-filtered data change listener, triggers a callback on matching events | `gateway-context.tsx`, React |

Both files are fully generic with zero project-specific imports. `gateway-context.tsx` provides `GatewayProvider`, `useGateway()`, `send()`, `sendCommand()`, `subscribe()`, `addListener()`, and `removeListener()`. `use-data-events.ts` accepts an entity filter list and optional `projectId` for scoped event handling.

### Test Coverage

- `tests/test_gateway.py` — Hub lifecycle, broadcast, subscribe/unsubscribe, envelope serialization

## Platform Adapter Layer

### What It Does
A platform-agnostic abstraction for posting content (single posts and threads), deleting posts, checking rate limits, and validating credentials. Mirrors the LLM and Messaging layer patterns: ABC with normalized result types, provider-specific implementations in separate modules, factory for routing.

### Files to Copy

Copy from `src/social_hook/adapters/platform/`:

| File | Purpose | Dependencies |
|------|---------|-------------|
| `base.py` | `PlatformAdapter` ABC (`post`, `post_thread`, `delete`, `get_rate_limit_status`, `validate`) | `models.py` (for `PostResult`, `PostCapability`) |
| `factory.py` | `create_adapter()` — routes platform name to adapter class | `base.py`, lazy imports to adapters |
| `x.py` | `XAdapter` — X (Twitter) API v2 posting | `base.py`, `tweepy>=4.0.0` |
| `linkedin.py` | `LinkedInAdapter` — LinkedIn API posting. Accepts `entity` parameter for posting as personal profile vs organization page. | `base.py`, `requests` |

Also copy from `src/social_hook/adapters/`:

| File | Purpose | Dependencies |
|------|---------|-------------|
| `models.py` | `PostResult` dataclass (with `part_results` for threads), `PostCapability`, `MediaMode` | None (stdlib only) |

### What to Replace

1. **`ConfigError`** — `factory.py` imports `from social_hook.errors import ConfigError`. Replace with your own exception class.
2. **Package paths** — Update `from social_hook.adapters.platform.X import Y` to your package name.
3. **Credential access** — `factory.py` reads credentials from `config.env.get(...)`. Adapt to your credential management approach.

### Quick Start

```python
from your_package.adapters.platform.factory import create_adapter

# Create an adapter (factory reads credentials from config)
adapter = create_adapter("x", config)

# Post a single item
result = adapter.post("Hello world!", media_paths=["image.png"])
if result.success:
    print(f"Posted: {result.external_url}")

# Post a thread (returns PostResult with part_results)
result = adapter.post_thread([
    {"content": "Thread 1/3", "media_paths": []},
    {"content": "Thread 2/3", "media_paths": []},
    {"content": "Thread 3/3", "media_paths": []},
])

# LinkedIn: post as an organization page via entity parameter
linkedin_adapter = LinkedInAdapter(access_token="...", entity="urn:li:organization:12345")
result = linkedin_adapter.post("Company update")
```

### What NOT to Copy

- `__init__.py` — Social-hook-specific re-exports (trivial to recreate)

### Test Coverage

Copy the corresponding test files:
- `tests/test_x_adapter.py` — X adapter (mocks tweepy)
- `tests/test_linkedin_adapter.py` — LinkedIn adapter (mocks requests)

## File Reader

### What It Does
Token-budgeted file reading with path traversal protection. Zero external dependencies -- reads a list of file paths within a configurable token budget, with deduplication, extension filtering, and truncation-to-fit. Useful for any system that assembles file content into LLM prompts.

### Files to Copy

Copy from `src/social_hook/`:

| File | Purpose | Dependencies |
|------|---------|-------------|
| `file_reader.py` | `read_files_within_budget()` -- reads files within token budget | None (stdlib only) |

### What to Replace

Nothing -- this module has zero social-hook imports.

### Quick Start

```python
from your_package.file_reader import read_files_within_budget

text, tokens = read_files_within_budget(
    paths=["README.md", "docs/guide.md", "src/main.py"],
    base_dir="/path/to/project",
    max_tokens=10_000,
)
# text: assembled file contents with ### headers
# tokens: approximate tokens used
```

## ContentSource Registry

### What It Does
A domain-agnostic registry class for composable context assembly. Maps named source types to resolver functions that produce context data. The evaluator specifies which sources the drafter needs; the registry resolves each mechanically. Expandable via simple function registration — adding a new source type means adding one resolver, no schema changes.

### Files to Copy

Copy from `src/social_hook/`:

| File | Purpose | Dependencies |
|------|---------|-------------|
| `content_sources.py` | `ContentSourceRegistry`, source type registration, resolver dispatch | None (stdlib only) |

### What to Replace

1. **Source types** — Replace social-hook source types (`brief`, `commits`, `topic`, `operator_suggestion`) with your domain's source types.
2. **Package paths** — Update imports to your package name.

### Quick Start

```python
from your_package.content_sources import ContentSourceRegistry

registry = ContentSourceRegistry()

# Register resolvers
registry.register("brief", lambda ctx: load_project_brief(ctx["project_id"]))
registry.register("commits", lambda ctx: load_commit_context(ctx["commit_hash"]))

# Resolve a composable list of sources
context = registry.resolve(
    sources=["brief", "commits"],
    ctx={"project_id": "proj_123", "commit_hash": "abc123"}
)
```

### Design Notes

- Resolver functions receive a context dict and return assembled data
- Unknown source types are logged and skipped (no crash)
- The registry pattern decouples the evaluator's decision (what context to include) from the routing layer's mechanics (how to assemble it)

---

## Unified Logging

### What It Does
A multi-sink logging pipeline built on Python's stdlib `logging`. Attaches a `LogBus` handler to the application's logger namespace that fans out records to: JSON file logs (with rotation), DB persistence (WARNING+), outbound notifications (ERROR/CRITICAL), and stderr (interactive modes). Existing `logging.getLogger(__name__)` calls automatically flow through all sinks with zero code changes.

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `logging.py` | `LogBus`, `FileSink`, `DbSink`, `NotificationSink`, `ConsoleSink`, `JsonFormatter`, `ComponentLogger`, `ContextFilter`, `setup_logging()`, `set_run_id()` | `constants.py` (for `CONFIG_DIR_NAME` default only) |
| `error_feed.py` | `ErrorFeed`, `ErrorSeverity`, `SystemError` — DB persistence + in-memory ring buffer | None (stdlib: `sqlite3`, `json`, `uuid`, `collections.deque`) |
| `constants.py` | `CONFIG_DIR_NAME` | None |

### What to Replace
1. **`CONFIG_DIR_NAME`** — in `constants.py`, replace with your project's config directory name. Or pass `log_dir` explicitly to `setup_logging()` to skip the import entirely.
2. **Package paths** — update `from social_hook.*` imports.
3. **DB table** — `error_feed.py` expects a `system_errors` table (columns: id, severity, message, context, source, component, run_id, created_at). See the DDL in schema.py or skip DB persistence (`error_feed=None`).

### Quick Start

```python
from your_package.logging import setup_logging, set_run_id
from your_package.error_feed import ErrorFeed

# Basic: file logging only
logger = setup_logging("worker")
logger.info("Started", event="worker_start")

# Full: file + DB + notifications
feed = ErrorFeed(db_path="/path/to/db.sqlite")
logger = setup_logging(
    "worker",
    error_feed=feed,
    notification_sender=lambda sev, msg: print(f"ALERT: {msg}"),
)
set_run_id("run_abc123")  # correlate all logs in this run
logger.error("Token expired", extra={"account": "main"})
# → written to worker.log (JSON), system_errors table, and notification sent
```

### Design Notes
- `setup_logging()` is idempotent — safe to call from multiple entry points; no `db_path` parameter — DbSink gets DB access from the injected `ErrorFeed` instance
- `LogBus` overrides `handle()` not `emit()` to avoid holding the handler lock during sink I/O
- `LogBus` catches per-sink exceptions — one failing sink never breaks others
- `ContextFilter` injects `component` and `run_id` via `threading.local()` into every record
- `FileSink` uses `TimedRotatingFileHandler` (30-day rotation, UTC midnight)
- `DbSink` delegates to `ErrorFeed` which manages its own connections (survives DB locks)
- `NotificationSink` takes a `Callable[[str, str], None]` — no messaging layer dependency
- `NotificationSink` pre-escapes Markdown special chars to avoid Telegram parse failures

### Test Coverage
- `tests/test_logging.py` — LogBus routing, exception isolation, all sinks, ContextFilter, set_run_id, setup_logging idempotency
- `tests/test_error_feed.py` — All severity levels, sender callback, ring buffer, DB persistence, on_persist callback, filter params

## System Error Feed (standalone)

### What It Does
The `ErrorFeed` component can also be used standalone (without the LogBus pipeline) as a severity-leveled error notification system with in-memory ring buffer and optional SQLite persistence. This is the lower-level component that `DbSink` delegates to.

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `error_feed.py` | `ErrorFeed`, `ErrorSeverity`, `SystemError` dataclass, module-level singleton | None (stdlib: `sqlite3`, `json`, `uuid`, `collections.deque`) |

### Quick Start

```python
from your_package.error_feed import ErrorFeed, ErrorSeverity

feed = ErrorFeed(db_path="/path/to/db.sqlite")
feed.set_sender(lambda severity, message: print(f"[{severity}] {message}"))
feed.set_on_persist(lambda error_id, severity, component: print(f"Persisted: {error_id}"))

feed.emit(ErrorSeverity.CRITICAL, "Token refresh failed",
          context={"account": "main"}, source="auth", component="scheduler")

recent = feed.get_recent(limit=10, severity="error", component="scheduler")
status = feed.get_health_status()
```

### Design Notes
- `emit()` accepts `ErrorSeverity` enum or plain string — auto-coerces strings to enum
- `emit()` never raises — catches its own exceptions and logs them
- `set_on_persist(callback)` fires after successful DB write with `(error_id, severity, component)`
- `get_recent()` supports `severity`, `component`, `source` filter params
- `component` and `run_id` fields for correlation with the unified logging pipeline
- Thread-safe `deque` for the in-memory ring buffer (capped at `max_recent`)
- Module-level singleton (`error_feed`) for process-wide use; call `set_db_path()` at startup

### Test Coverage
- `tests/test_error_feed.py` — All severity levels, sender callback, ring buffer, DB persistence, on_persist callback, filter params, component/run_id fields

## Pipeline Diagnostics

### What It Does
A generic check-registry system for structured pipeline health diagnostics. Register pure check functions, run them against a context dict, get structured results with severity, code, message, and actionable suggestions. Designed for post-pipeline diagnostic reporting — "why did this run produce unexpected results?" Each check is isolated (one failure doesn't break others). Results are data (JSON-serializable), not UI — any interface can render them.

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `diagnostics.py` | `DiagnosticSeverity`, `Diagnostic`, `DiagnosticRegistry` (decorator-based registration, per-check exception isolation), module-level singleton | None (stdlib only) |

### What to Replace
Nothing. The module has zero project-specific imports and no package paths to update.

### Quick Start

```python
from your_package.diagnostics import Diagnostic, DiagnosticSeverity, DiagnosticRegistry

registry = DiagnosticRegistry()

@registry.register("missing_config")
def check_missing_config(ctx: dict) -> list[Diagnostic] | None:
    if not ctx.get("config_path"):
        return [Diagnostic(
            code="missing_config",
            severity=DiagnosticSeverity.ERROR,
            message="No config file found",
            suggestion="Create config.yaml in the project root",
            context={},
        )]
    return None

# Run all checks
results = registry.run({"config_path": None})
# results: [Diagnostic(code="missing_config", severity=ERROR, ...)]
```

### Two Flavours

The same `DiagnosticRegistry` supports two usage patterns:

- **Stored (point-in-time):** Run checks after an immutable operation, store results on the entity. Good for evaluation cycles, completed reports, build results. Example: `pipeline_diagnostics.py` → results stored on `evaluation_cycles.diagnostics`.
- **Computed at read time:** Run checks when serving an entity via API, inject results into the response without storing. Good for mutable entities whose state changes (drafts, orders, tickets). Example: `draft_diagnostics.py` → results computed in the draft detail endpoint.

Both use the same `Diagnostic` dataclass and `DiagnosticRegistry`. Create separate registry instances per domain.

### What NOT to Copy
- `pipeline_diagnostics.py` — Social-hook-specific pipeline checks. Your project defines its own.
- `draft_diagnostics.py` — Social-hook-specific draft checks. Your project defines its own.

### Test Coverage
- `tests/test_diagnostics.py` — Registry basics, exception isolation, severity sorting, decorator syntax

---

## Project Naming Constants

### What It Does
Centralizes all branding/naming strings (display name, CLI slug, config directory, DB filename) in a single zero-dependency module. Used by `filesystem.py`, `logging.py`, CLI, bot, web server, and setup wizard for consistent naming.

### Files to Copy
| File | Purpose | Dependencies |
|------|---------|-------------|
| `constants.py` | `PROJECT_NAME`, `PROJECT_SLUG`, `CONFIG_DIR_NAME`, `DB_FILENAME` | None (stdlib only) |

### What to Replace
All values — replace with your own project's branding.

### Integration with Reusable Layers
When copying the LLM or Messaging layers, `constants.py` is NOT required — those layers use `ConfigError` as their only cross-cutting dependency. The reusable layer files (`openai_compat.py`, `slack.py`) use generic dependency error messages (e.g., "openai package required") with no project-specific install hints.

If you also copy `filesystem.py` (which uses `CONFIG_DIR_NAME` and `DB_FILENAME`) or `logging.py` (which uses `CONFIG_DIR_NAME`), you should either copy `constants.py` or inline those values.

## Generic Adapter Registry

### What It Does
A domain-agnostic registry class that maps string names to factory callables with optional metadata and instance caching. Replaces hardcoded if/elif dispatch chains in adapter factories with extensible registration. Used by all three adapter subsystems (platform posting, media generation, messaging) and available for any factory pattern.

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `registry.py` | `AdapterRegistry` — register, create, get_or_create, metadata, caching | None (stdlib only: `logging`, `typing`) |

### What to Replace

1. **Package paths** — Update `from social_hook.registry import AdapterRegistry` to your package name.

### Quick Start

```python
from your_package.registry import AdapterRegistry

# Create a registry for your adapter type
platforms = AdapterRegistry("platform")

# Register adapters with optional metadata
def create_email(*, smtp_host, **_kw):
    return EmailAdapter(smtp_host)

platforms.register("email", create_email, metadata={
    "display_name": "Email",
    "description": "Send via SMTP",
})

# Create instances by name
adapter = platforms.create("email", smtp_host="mail.example.com")

# Caching (for singletons like media adapters)
adapter = platforms.get_or_create("email", smtp_host="mail.example.com")

# Introspection
platforms.names()          # ["email"]
platforms.get_metadata("email")  # {"display_name": "Email", ...}
platforms.all_metadata()   # {"email": {"display_name": "Email", ...}}

# Cache management
platforms.invalidate("email")  # Force re-creation on next get_or_create
platforms.clear_cache()        # Clear all cached instances
```

### Design Notes

- `create()` always returns a fresh instance; `get_or_create()` caches
- Unknown names raise `KeyError` with a message listing available adapters
- Metadata is stored as dicts — the registry imposes no schema
- `get_metadata()` returns a copy to prevent mutation of internal state
- The `kind` constructor parameter customizes error messages (e.g., "Unknown platform adapter" vs "Unknown media adapter")
- Thread-safe for reads; registration is typically done once at module load time via a lazy `_ensure_registered()` pattern

### Integration with Existing Layers

The registry is used internally by the platform adapter factory (`adapters/platform/factory.py`), media adapter registry (`adapters/registry.py`), and messaging factory (`messaging/factory.py`). Each factory defines per-adapter factory functions and registers them lazily. The public API functions (`create_adapter`, `get_media_adapter`, etc.) delegate to the registry.

To add a new platform/media/messaging adapter:
1. Write the adapter class in its own module
2. Write a factory function in the relevant factory module
3. Add one `register()` call at module level

No if/elif chains to modify.

### Test Coverage

- `tests/test_registry.py` — register, create, get_or_create, metadata, caching, invalidation, error messages, backward compatibility

## SQL Migration Runner

### What It Does
A generic SQLite migration runner that reads `.sql` files from a directory, applies them in ascending order by numeric prefix, and tracks applied versions in a `schema_version` table. Handles PRAGMA-containing migrations (required for SQLite table rebuilds) by splitting PRAGMAs from DDL and executing them outside transactions.

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `migrations.py` | `apply_sql_migrations()`, `ensure_version_table()`, `get_current_version()`, `_apply_pragma_migration()` | None (stdlib only: `sqlite3`, `pathlib`, `logging`) |

### What to Replace

Nothing. The module has zero project-specific imports and no package paths to update.

### Quick Start

```python
import sqlite3
from your_package.migrations import apply_sql_migrations, ensure_version_table

conn = sqlite3.connect("app.db")

# First run: create the version tracking table
ensure_version_table(conn)

# Apply all pending migrations from the migrations/ directory
applied = apply_sql_migrations(conn, "migrations/")
print(f"Applied {applied} migration(s)")
```

Migration files use numeric prefixes for ordering:
```
migrations/
  001_create_users.sql
  002_add_email_column.sql
  20260328120000_add_feature.sql    # Timestamp prefixes also work
```

### Design Notes

- `apply_sql_migrations()` returns the count of newly applied migrations
- Only the digits before the first underscore in the filename are used as the version number
- PRAGMA-containing migrations (table rebuilds) are detected automatically and handled correctly
- Idempotent — safe to call on every startup; already-applied migrations are skipped
- Custom `version_table` name supported for projects with multiple independent migration sets
- The version table uses `(version INTEGER PRIMARY KEY, applied_at TEXT, description TEXT)`

### What NOT to Copy

- `db/schema.py` — Social-hook-specific DDL and legacy sequential-to-timestamp bridge. Your project defines its own schema.

### Test Coverage

- `tests/test_migrations.py` — apply in order, skip applied, PRAGMA handling, timestamp prefixes, custom table names, edge cases

## Scheduling Algorithm

### What It Does
A pure function that finds the next optimal time slot given constraints: existing post times, already-scheduled times, daily/weekly limits, minimum gap between posts, preferred days and hours, and timezone handling. No database or domain dependencies — works with any system that needs rate-limited, time-optimized scheduling.

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `scheduling.py` | `find_optimal_slot()` pure function, `ScheduleResult` dataclass | None (stdlib only: `datetime`, `zoneinfo`, `logging`) |

### What to Replace

1. **Package paths** — Update imports to your package name.
2. **Remove DB wrapper** — `calculate_optimal_time()` and `get_scheduling_state()` are social-hook-specific DB wrappers. Copy only `find_optimal_slot()` and `ScheduleResult`.

### Quick Start

```python
from datetime import datetime, timezone
from your_package.scheduling import find_optimal_slot

# Find next slot given existing posts and constraints
result = find_optimal_slot(
    existing_post_times=[datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc)],
    scheduled_times=[],
    tz="America/Los_Angeles",
    posts_today_count=1,
    max_posts_per_day=3,
    min_gap_minutes=30,
    optimal_days=["Tue", "Wed", "Thu"],
    optimal_hours=[9, 12, 17],
    weekly_count=5,
    max_per_week=10,
)

if result.deferred:
    print(f"Deferred: {result.day_reason}")
else:
    print(f"Post at: {result.datetime} ({result.day_reason}, {result.time_reason})")
```

### Design Notes

- Pure function — no side effects, no DB queries, no domain dependencies
- Accepts a `now` parameter for deterministic testing
- Scans up to 7 days out, then falls back to 1 hour from now
- Timezone-aware: optimal hours are interpreted in the specified timezone, results are UTC
- `ScheduleResult.deferred=True` signals the caller to defer (e.g., weekly limit reached)
- Invalid timezone strings fall back to UTC silently

### What NOT to Copy

- `calculate_optimal_time()` — DB-aware wrapper that queries posts and drafts. Your project wraps `find_optimal_slot()` with its own data access.
- `get_scheduling_state()` — Social-hook-specific state snapshot for evaluator context.
- `PlatformSchedulingState`, `ProjectSchedulingState` — Domain-specific dataclasses.

### Test Coverage

- `tests/test_find_optimal_slot.py` — Pure algorithm tests: basic slots, weekly limits, min gap, full days, scheduled conflicts, timezone handling, fallback behavior
- `tests/test_scheduling.py` — DB-integrated tests for `calculate_optimal_time()` (existing)

## OAuth 2.0 PKCE Utilities

### What It Does
Generic OAuth 2.0 PKCE flow utilities: verifier/challenge generation (S256), authorization URL building, code-for-token exchange, and a local HTTP callback server for CLI-based OAuth flows. Platform-agnostic — pass endpoint URLs and scopes as parameters.

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `oauth_pkce.py` | `generate_pkce()`, `build_auth_url()`, `exchange_code()`, `CallbackHandler`, `start_callback_server()`, `OAuthEndpoints` dataclass | `requests` (stdlib otherwise) |

### What to Replace

1. **Package paths** — Update `from social_hook.oauth_pkce import ...` to your package name.

### Quick Start

```python
from your_package.oauth_pkce import (
    OAuthEndpoints, generate_pkce, build_auth_url,
    exchange_code, start_callback_server,
)

endpoints = OAuthEndpoints(
    auth_url="https://example.com/authorize",
    token_url="https://example.com/token",
    scopes="read write",
)

# 1. Generate PKCE
verifier, challenge = generate_pkce()

# 2. Build auth URL
url = build_auth_url(endpoints, client_id="abc", state="random",
                     code_challenge=challenge,
                     redirect_uri="http://localhost:4000/callback")

# 3. Start callback server
server, thread = start_callback_server(4000)

# 4. Open URL in browser, wait for callback...
from your_package.oauth_pkce import CallbackHandler
# After callback: CallbackHandler.code, .state, .error are set

# 5. Exchange code for tokens
resp = exchange_code(endpoints, CallbackHandler.code, verifier,
                     client_id="abc", client_secret="secret",
                     redirect_uri="http://localhost:4000/callback")
tokens = resp.json()
```

### What NOT to Copy

- `setup/oauth.py` — Social-hook-specific platform configs (`OAUTH_PLATFORMS`), token persistence (`_save_tokens`), validation endpoints, and interactive CLI UX. Your project defines its own platform configs and token storage.

### Test Coverage

- `tests/test_oauth_pkce.py` — PKCE generation, challenge verification, URL building, handler state

## Dry-Run Proxy

### What It Does
A generic proxy that wraps a module (or any object with callable attributes), forwarding read operations while silently skipping write operations. Read vs write is determined by function name prefix (default: `get_*` passes through, everything else is skipped). Returns sensible defaults for skipped operations (`insert_*` → `.id`, `update_*` → `False`, etc.).

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `dry_run.py` | `DryRunProxy` class, `_make_noop()` default factory | None (stdlib only: `logging`) |

### What to Replace

1. **Package paths** — Update `from social_hook.dry_run import DryRunProxy` to your package name.

### Quick Start

```python
from your_package.dry_run import DryRunProxy
import your_db_ops

# Wrap your operations module
proxy = DryRunProxy(your_db_ops, first_arg=conn, dry_run=True)

proxy.get_user(42)          # Passes through: your_db_ops.get_user(conn, 42)
proxy.insert_user(user)     # Skipped, returns user.id if available
proxy.update_user(42, name="new")  # Skipped, returns False
proxy.delete_user(42)       # Skipped, returns None

# With dry_run=False, all operations pass through normally
proxy = DryRunProxy(your_db_ops, first_arg=conn, dry_run=False)
proxy.delete_user(42)       # Executes: your_db_ops.delete_user(conn, 42)
```

### Design Notes

- `first_arg` is prepended to every forwarded call — designed for the common pattern where all DB operations take a connection as their first parameter
- `read_prefixes` is configurable: `DryRunProxy(mod, read_prefixes=("get_", "list_", "count_"))`
- Uses `object.__getattribute__` internally to avoid recursion in `__getattr__`
- Subclass for domain-specific behavior (see `llm/dry_run.py:DryRunContext` which adds `trigger_source`)

### What NOT to Copy

- `llm/dry_run.py` — Social-hook-specific subclass that targets `db.operations` and adds `trigger_source` attribute. Your project creates its own thin subclass.

### Test Coverage

- `tests/test_dry_run_proxy.py` — Passthrough, skipping (insert/update/delete/increment/set/reset/supersede), edge cases, custom read prefixes

## Git Commit Parser

### What It Does
Parses git commit metadata (message, diff, stat, timestamps) via subprocess calls. Returns a structured `CommitInfo` dataclass. Handles edge cases: first commit (no parent), detached HEAD, failed git commands.

### Files to Copy

| File | Purpose | Dependencies |
|------|---------|-------------|
| `trigger_git.py` | `parse_commit_info()`, `git_remote_origin()`, `_get_current_branch()` | `CommitInfo` dataclass from `models`, `safe_int` from `parsing.py` |

### What to Replace

1. **Package paths** — Update `from social_hook.models.core import CommitInfo` and `from social_hook.parsing import safe_int` to your package name.
2. **CommitInfo dataclass** — Copy the `CommitInfo` definition from `models/core.py` (a simple dataclass with hash, message, diff, files_changed, insertions, deletions, timestamp, parent_timestamp fields).

### Quick Start

```python
from your_package.trigger_git import parse_commit_info, git_remote_origin

# Parse a commit
info = parse_commit_info("abc1234", "/path/to/repo")
print(f"{info.hash[:8]}: {info.message}")
print(f"Files: {info.files_changed}, +{info.insertions}/-{info.deletions}")

# Get remote origin URL
origin = git_remote_origin("/path/to/repo")
```

### What NOT to Copy

- `trigger.py` — The pipeline orchestrator. Social-hook-specific.
- `trigger_context.py`, `trigger_decisions.py`, `trigger_side_effects.py`, `trigger_batch.py`, `trigger_secondary.py` — All social-hook-specific pipeline modules.

### Test Coverage

- `tests/test_trigger.py` — Integration tests for `parse_commit_info` and `git_remote_origin`

## Task Stage Tracking

### What It Does

Lets any long-running background task emit named stages for frontend progress display (stage label + per-stage timer on AsyncButton).

**Universal principle: any LLM call = background task + stage events.** This applies to pipeline evaluation, drafting, bot handler actions (Gatekeeper, Expert), media generation — any path that calls an LLM agent. By enforcing this universally, the infrastructure supports cost tracking, cancellation, rate limiting, and pipeline visualization without changing individual flows.

### Files

- Backend: `ops.emit_task_stage()` in `db/operations.py` — thin wrapper over `emit_data_event`
- Frontend: `useBackgroundTasks` stage handler in `use-background-tasks.ts`
- Types: `stage`, `stage_label` on `DataChangeEvent`; `current_stage`, `stage_label`, `stage_started_at` on `BackgroundTask`

### To Use in a New Flow

1. Capture `task_id` from `_run_background_task` using a mutable holder (see CODING_PRACTICES)
2. Call `ops.emit_task_stage(conn, task_id, "my_stage", "Doing something", project_id)` at each step
3. Frontend automatically picks it up — `getTask(refId)?.stage_label` for text, `stage_started_at` for timer

### Limitations

- Stage data is in-memory only — lost on page refresh (task shows generic "Processing")
- Stage names are freeform strings, not validated
- Pipeline events (toasts) and task stages are independent — a flow may use either, both, or neither

### What NOT to Copy

Pipeline-specific stage emissions in `trigger.py` — those are wired to `PipelineStage` constants and `TriggerContext.task_id`. Your flow carries `task_id` however it wants (local variable, context object, closure).
