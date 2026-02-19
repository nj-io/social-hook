# Implementation Changelog

Deviations and discoveries from the original multi-provider integration plan.

## 2026-02-15

### CLI client: replaced --json-schema with prompt-based JSON output

The plan specified using `claude -p --json-schema` for structured output from the CLI provider. In practice, `--json-schema` forces the CLI into a multi-turn structured-output validation loop — minimum 3 API round-trips for trivial schemas, 15-20+ for complex ones like LogDecisionInput (6 fields, 4 enums). This caused 300s+ timeouts during E2E testing and 50+ notification sounds per call.

Fix: embed the JSON schema as instructions in the system prompt and parse JSON from the single-turn text response. Added `_extract_json()` helper that handles raw JSON, code-fenced JSON, and JSON embedded in surrounding text. Turns dropped from 15-20+ to exactly 1.

The `validate_claude_cli()` function in setup/validation.py still uses `--json-schema` with a trivial 1-field schema — this completes in seconds and validates that the CLI actually works, so it was left unchanged.

### CLI client: restore real HOME for subprocess auth

The E2E test harness patches `os.environ["HOME"]` to a temp directory for isolation and symlinks `~/.claude/` into it. This wasn't sufficient — Claude Code stores auth credentials outside `~/.claude/` (likely macOS Keychain or another system location). The CLI reported "Not logged in" in the isolated environment.

Fix: use `pwd.getpwuid(os.getuid()).pw_dir` to get the real home directory regardless of env patches, and set `HOME` to this value in the subprocess env. This is resilient to any HOME patching by test harnesses or other callers.

### CLI client: subprocess.run to Popen refactor

The plan specified `subprocess.run()` for CLI calls. Changed to `subprocess.Popen` with `start_new_session=True` to isolate the process group from the terminal (reduces notification sound propagation) and to enable proper `KeyboardInterrupt` handling via `proc.kill()`.

Also added `cwd=tempfile.gettempdir()` to prevent the CLI from scanning the project codebase directory on startup.

### CLI client: verbose tracing

Not in the original plan. Added `verbose` parameter to `ClaudeCliClient` and threaded it through `create_client()` factory and `run_trigger()`. When enabled, logs model name, tool, prompt preview, token counts, cost, and output preview to stderr. Essential for debugging E2E test failures.

### E2E test: provider-parameterized runs

Added `--provider` flag to `e2e_test.py` with `PROVIDER_PRESETS` dict mapping `claude-cli` and `anthropic` to their model configs. All LLM-heavy tests pass `verbose=runner.verbose` to `run_trigger()`.

### Error reporting improvement

When the CLI exits with non-zero and stderr is empty, now includes stdout (truncated to 500 chars) in the error message. This surfaced the "Not logged in" error that was previously invisible.

### Evaluator-to-drafter context flow: `angle`, `include_project_docs`

E2E testing revealed the drafter was producing shallow, changelog-style posts for introductions instead of proper product introductions. Root cause was a 5-part context flow failure:

1. **`angle` field missing from schema.** The evaluator prompt instructed the LLM to provide an `angle` field, but `LogDecisionInput` didn't define it. Pydantic silently stripped it during validation. The evaluator's framing never reached the drafter.

2. **`include_project_docs` field added.** New boolean field on `LogDecisionInput`. The evaluator sets this to `true` when the drafter needs README/CLAUDE.md to write the post (introductions, synthesis, launches, etc.). The drafter prompt assembly includes project docs only when this flag is set or `audience_introduced=false`.

3. **Drafter prompt assembly updated.** `assemble_drafter_prompt()` now includes: `audience_introduced` status, the evaluator's `angle`, project documentation (README/CLAUDE.md) when flagged, and project summary.

4. **Drafter user message updated.** When `audience_introduced=false`, the user message explicitly instructs the drafter to write an introduction. The evaluator's angle is included when present.

5. **Prompt templates updated.** The evaluator prompt now explains when to set `include_project_docs` and how to write rich angles. The drafter prompt now has a dedicated "Introduction Posts" section with guidance on story structure, what to avoid, and examples.

The tech arch spec at line 1679 already called for `[Project documentation subset relevant to commit]` in the drafter context — the implementation had simply never included it.
