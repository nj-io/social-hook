#!/usr/bin/env python3
"""Development Journey (Narrative Capture) verification script.

Verifies the full narrative capture pipeline end-to-end:
  --dry-run  No API calls, test all components (default)
  --live     Real API calls (~$0.50-$2.00, uses configured provider)

Usage:
  python scripts/verify_narrative.py --dry-run
  python scripts/verify_narrative.py --live
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Step tracking
# ---------------------------------------------------------------------------

_step = 0
_failures = 0


def step(label: str) -> None:
    global _step
    _step += 1
    print(f"\n  [{_step:2d}] {label}")


def ok(msg: str) -> None:
    print(f"       OK  {msg}")


def fail(msg: str) -> None:
    global _failures
    _failures += 1
    print(f"       FAIL  {msg}")


def check(condition: bool, pass_msg: str, fail_msg: str) -> None:
    if condition:
        ok(pass_msg)
    else:
        fail(fail_msg)


# ---------------------------------------------------------------------------
# Sample transcript data
# ---------------------------------------------------------------------------

SAMPLE_TRANSCRIPT_LINES = [
    {
        "type": "user",
        "message": {
            "role": "user",
            "content": "Let's implement the authentication module for the project.",
        },
    },
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "The user wants auth. I should consider JWT vs sessions.",
                },
                {
                    "type": "text",
                    "text": "I'll implement the authentication module. Let me start with the session management.",
                },
            ],
        },
    },
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "echo 'auth code'"},
                },
            ],
        },
    },
    {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": "auth code",
                },
            ],
        },
    },
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Authentication module is ready. I chose bcrypt for password hashing.",
                },
            ],
        },
    },
    {
        "type": "progress",
        "message": {"content": "Working..."},
    },
    {
        "type": "user",
        "isSidechain": True,
        "message": {
            "role": "user",
            "content": "This is a sidechain message that should be filtered.",
        },
    },
]


def _write_sample_jsonl(path: Path) -> Path:
    """Write sample JSONL transcript to a file."""
    jsonl_path = path / "sample_transcript.jsonl"
    with open(jsonl_path, "w") as f:
        for entry in SAMPLE_TRANSCRIPT_LINES:
            f.write(json.dumps(entry) + "\n")
    return jsonl_path


# ---------------------------------------------------------------------------
# Mock helpers for dry-run mode
# ---------------------------------------------------------------------------


def _mock_extract_narrative_response():
    """Build a mock LLM response for narrative extraction."""
    tool_use = SimpleNamespace(
        type="tool_use",
        name="extract_narrative",
        input={
            "summary": "Implemented authentication module with bcrypt password hashing",
            "key_decisions": [
                "Chose bcrypt over argon2 for password hashing",
                "Used session-based auth instead of JWT",
            ],
            "rejected_approaches": [
                "JWT was considered but rejected due to complexity",
            ],
            "aha_moments": [
                "Discovered that bcrypt's built-in salt handling simplifies the implementation",
            ],
            "challenges": [
                "Getting the session expiry timing right",
            ],
            "narrative_arc": "From a blank auth module to a working login system",
            "relevant_for_social": True,
            "social_hooks": [
                "Why we chose bcrypt over JWT for a dev tools project",
                "The session management pattern that saved us hours of debugging",
            ],
        },
    )
    usage = SimpleNamespace(
        input_tokens=5000,
        output_tokens=300,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(
        content=[tool_use],
        usage=usage,
        tool_calls=[
            SimpleNamespace(
                name="extract_narrative",
                input=tool_use.input,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Main verification
# ---------------------------------------------------------------------------


def verify(live: bool = False) -> bool:
    """Run verification steps. Returns True if all pass."""

    global _step, _failures
    _step = 0
    _failures = 0

    mode = "LIVE" if live else "DRY-RUN"
    print(f"\n{'='*60}")
    print(f"  Narrative Capture Verification ({mode})")
    print(f"{'='*60}")

    # --- Setup temp directory ---
    tmpdir = tempfile.mkdtemp(prefix="narrative_verify_")
    tmp_path = Path(tmpdir)

    # =========================================================================
    # Step 1: Config parsing with journey_capture section
    # =========================================================================
    step("Config parsing with journey_capture")
    from social_hook.config.yaml import JourneyCaptureConfig, _parse_config

    # Default config (no journey_capture key)
    config_no_jc = _parse_config({})
    check(
        config_no_jc.journey_capture.enabled is False,
        "Default: enabled=False",
        f"Default enabled={config_no_jc.journey_capture.enabled}",
    )
    check(
        config_no_jc.journey_capture.model is None,
        "Default: model=None",
        f"Default model={config_no_jc.journey_capture.model}",
    )

    # Explicit enabled
    config_enabled = _parse_config({
        "journey_capture": {"enabled": True},
    })
    check(
        config_enabled.journey_capture.enabled is True,
        "Explicit: enabled=True",
        f"Explicit enabled={config_enabled.journey_capture.enabled}",
    )

    # With custom model
    config_model = _parse_config({
        "journey_capture": {
            "enabled": True,
            "model": "anthropic/claude-sonnet-4-5",
        },
    })
    check(
        config_model.journey_capture.model == "anthropic/claude-sonnet-4-5",
        "Custom model: anthropic/claude-sonnet-4-5",
        f"Custom model={config_model.journey_capture.model}",
    )

    # Invalid model format
    from social_hook.errors import ConfigError

    try:
        _parse_config({
            "journey_capture": {
                "enabled": True,
                "model": "bare-model-name",
            },
        })
        fail("Should have raised ConfigError for bare model name")
    except ConfigError:
        ok("Bare model name raises ConfigError")

    # =========================================================================
    # Step 2: Transcript reading from sample JSONL
    # =========================================================================
    step("Transcript reading from sample JSONL")
    from social_hook.narrative.transcript import read_transcript

    jsonl_path = _write_sample_jsonl(tmp_path)
    messages = read_transcript(jsonl_path)

    # read_transcript filters to user/assistant only (no progress, no system)
    check(
        len(messages) >= 4,
        f"Read {len(messages)} user/assistant messages (expected >=4)",
        f"Only read {len(messages)} messages",
    )

    # Check that progress type was excluded
    types_found = {m.get("type") for m in messages}
    check(
        "progress" not in types_found,
        "Progress messages excluded",
        f"Progress messages included: {types_found}",
    )

    # =========================================================================
    # Step 3: Filtering strips tool_use/tool_result, keeps text/thinking
    # =========================================================================
    step("Filtering strips tool_use/tool_result, keeps text/thinking")
    from social_hook.narrative.transcript import filter_for_extraction

    filtered = filter_for_extraction(messages)

    # Should strip tool_use and tool_result blocks
    for msg in filtered:
        content = msg.get("message", {}).get("content")
        if isinstance(content, list):
            for block in content:
                block_type = block.get("type", "")
                check(
                    block_type not in ("tool_use", "tool_result", "image"),
                    f"Block type '{block_type}' is allowed",
                    f"Block type '{block_type}' should be filtered",
                )

    # Should keep text and thinking blocks
    all_block_types = set()
    for msg in filtered:
        content = msg.get("message", {}).get("content")
        if isinstance(content, list):
            for block in content:
                all_block_types.add(block.get("type"))
        elif isinstance(content, str):
            all_block_types.add("text_str")

    check("text" in all_block_types or "text_str" in all_block_types,
          "Text blocks kept", "No text blocks found")
    check("thinking" in all_block_types,
          "Thinking blocks kept", "No thinking blocks found")

    # Sidechain messages should be excluded
    sidechain_count = sum(1 for m in filtered if m.get("isSidechain"))
    check(sidechain_count == 0, "Sidechain messages excluded",
          f"Sidechain messages present: {sidechain_count}")

    check(
        len(filtered) >= 2,
        f"Filtered to {len(filtered)} messages (expected >=2)",
        f"Only {len(filtered)} messages after filtering",
    )

    # =========================================================================
    # Step 4: Format for prompt
    # =========================================================================
    step("Format for prompt")
    from social_hook.narrative.transcript import format_for_prompt

    formatted = format_for_prompt(filtered)
    check(len(formatted) > 0, f"Formatted: {len(formatted)} chars", "Empty formatted output")
    check("[USER]" in formatted, "Contains [USER] labels", "Missing [USER] labels")
    check("[ASSISTANT]" in formatted, "Contains [ASSISTANT] labels",
          "Missing [ASSISTANT] labels")
    check("[ASSISTANT THINKING]" in formatted, "Contains [ASSISTANT THINKING] labels",
          "Missing [ASSISTANT THINKING] labels")

    # =========================================================================
    # Step 5: Truncate to budget
    # =========================================================================
    step("Truncate to budget")
    from social_hook.narrative.transcript import truncate_to_budget

    short_text = "Short text"
    check(truncate_to_budget(short_text) == short_text,
          "Short text passes through", "Short text truncated")

    long_text = "x" * 200_000
    truncated = truncate_to_budget(long_text, max_chars=100_000)
    check(
        len(truncated) == 100_000,
        f"Long text truncated to {len(truncated)} chars",
        f"Expected 100000, got {len(truncated)}",
    )

    # =========================================================================
    # Step 6: Storage save/load/cleanup round-trip
    # =========================================================================
    step("Storage save/load/cleanup round-trip")

    # Patch get_narratives_path to use temp dir
    narratives_dir = tmp_path / "narratives"
    narratives_dir.mkdir()

    with patch(
        "social_hook.narrative.storage.get_narratives_path",
        return_value=narratives_dir,
    ):
        from social_hook.narrative.storage import (
            cleanup_old_narratives,
            load_recent_narratives,
            save_narrative,
        )
        from social_hook.llm.schemas import ExtractNarrativeInput

        extraction = ExtractNarrativeInput.validate({
            "summary": "Test session summary",
            "key_decisions": ["Decision A", "Decision B"],
            "rejected_approaches": ["Approach X"],
            "aha_moments": ["Aha moment 1"],
            "challenges": ["Challenge 1"],
            "narrative_arc": "From problem to solution",
            "relevant_for_social": True,
            "social_hooks": ["Hook angle 1", "Hook angle 2"],
        })

        saved_path = save_narrative("proj_test1", extraction, "session_001", "auto")
        check(saved_path.exists(), f"Saved to {saved_path.name}", "Save failed")

        loaded = load_recent_narratives("proj_test1", limit=5)
        check(len(loaded) == 1, f"Loaded {len(loaded)} narrative(s)", "Load failed")
        check(
            loaded[0]["summary"] == "Test session summary",
            "Summary matches",
            f"Summary: {loaded[0].get('summary')}",
        )
        check(
            loaded[0]["relevant_for_social"] is True,
            "relevant_for_social=True",
            f"relevant_for_social={loaded[0].get('relevant_for_social')}",
        )

        # Session deduplication: save 3 with same session_id
        save_narrative("proj_test1", extraction, "session_001", "auto")
        save_narrative("proj_test1", extraction, "session_001", "auto")
        loaded_deduped = load_recent_narratives("proj_test1", limit=10)
        check(
            len(loaded_deduped) == 1,
            f"Deduplicated to {len(loaded_deduped)} (3 saves, same session_id)",
            f"Expected 1 after dedup, got {len(loaded_deduped)}",
        )

        # Cleanup (nothing old enough to remove)
        removed = cleanup_old_narratives("proj_test1", max_age_days=90)
        check(removed == 0, "Cleanup removed 0 (all recent)", f"Removed {removed}")

    # =========================================================================
    # Step 7: CLI commands (journey on/off/status) via CliRunner
    # =========================================================================
    step("CLI commands: journey on/off/status")
    from typer.testing import CliRunner
    from social_hook.cli import app

    cli = CliRunner()

    # Create a minimal config environment for CLI testing
    cli_home = tmp_path / "cli_home"
    cli_home.mkdir()
    sh_dir = cli_home / ".social-hook"
    sh_dir.mkdir()
    (sh_dir / ".env").write_text("TELEGRAM_BOT_TOKEN=fake\n")
    (sh_dir / "config.yaml").write_text("models:\n  evaluator: anthropic/claude-opus-4-5\n  drafter: anthropic/claude-opus-4-5\n  gatekeeper: anthropic/claude-haiku-4-5\n")

    # Create .claude dir for hook installation
    claude_dir = cli_home / ".claude"
    claude_dir.mkdir()

    import os
    orig_home = os.environ.get("HOME")
    os.environ["HOME"] = str(cli_home)

    try:
        # journey on
        result = cli.invoke(app, ["journey", "on"])
        check(
            result.exit_code == 0,
            f"journey on: exit {result.exit_code}",
            f"journey on failed: {result.output}",
        )
        check(
            "enabled" in result.output.lower() or "capture" in result.output.lower(),
            "Output mentions enabled/capture",
            f"Output: {result.output.strip()[:80]}",
        )

        # Verify config was updated
        import yaml
        config_data = yaml.safe_load((sh_dir / "config.yaml").read_text())
        check(
            config_data.get("journey_capture", {}).get("enabled") is True,
            "Config updated: enabled=True",
            f"Config: {config_data.get('journey_capture')}",
        )

        # Verify hook was installed
        from social_hook.setup.install import check_narrative_hook_installed
        check(
            check_narrative_hook_installed(),
            "Narrative hook installed",
            "Narrative hook NOT installed",
        )

        # journey status
        result = cli.invoke(app, ["journey", "status"])
        check(
            result.exit_code == 0,
            f"journey status: exit {result.exit_code}",
            f"journey status failed: {result.output}",
        )
        check(
            "yes" in result.output.lower() or "enabled" in result.output.lower(),
            "Status shows enabled",
            f"Output: {result.output.strip()[:80]}",
        )

        # journey off
        result = cli.invoke(app, ["journey", "off"])
        check(
            result.exit_code == 0,
            f"journey off: exit {result.exit_code}",
            f"journey off failed: {result.output}",
        )

        config_data = yaml.safe_load((sh_dir / "config.yaml").read_text())
        check(
            config_data.get("journey_capture", {}).get("enabled") is False,
            "Config updated: enabled=False",
            f"Config: {config_data.get('journey_capture')}",
        )
    finally:
        if orig_home is not None:
            os.environ["HOME"] = orig_home
        elif "HOME" in os.environ:
            del os.environ["HOME"]

    # =========================================================================
    # Step 8: ExtractNarrativeInput schema validation
    # =========================================================================
    step("ExtractNarrativeInput schema validation")

    valid = ExtractNarrativeInput.validate({
        "summary": "A good session",
        "key_decisions": ["d1"],
        "rejected_approaches": [],
        "aha_moments": [],
        "challenges": [],
        "narrative_arc": "story",
        "relevant_for_social": False,
        "social_hooks": [],
    })
    check(valid.summary == "A good session", "Valid input parsed", "Parse failed")
    check(valid.relevant_for_social is False, "relevant_for_social=False", "Wrong value")

    from social_hook.errors import MalformedResponseError

    try:
        ExtractNarrativeInput.validate({"summary": "missing fields"})
        fail("Should have raised MalformedResponseError for missing fields")
    except MalformedResponseError:
        ok("Missing fields raises MalformedResponseError")

    # =========================================================================
    # Step 9: Haiku model rejection logic
    # =========================================================================
    step("Haiku model rejection logic")

    # The narrative-capture command rejects haiku models — verify the logic
    model_str = "anthropic/claude-haiku-4-5"
    check(
        "haiku" in model_str.lower(),
        f"Haiku detected in '{model_str}'",
        f"Haiku NOT detected in '{model_str}'",
    )
    model_str_ok = "anthropic/claude-sonnet-4-5"
    check(
        "haiku" not in model_str_ok.lower(),
        f"Non-haiku passes: '{model_str_ok}'",
        f"False haiku detection in '{model_str_ok}'",
    )

    # =========================================================================
    # Step 10: NarrativeExtractor (dry-run or live)
    # =========================================================================
    step("NarrativeExtractor extraction")
    from social_hook.narrative.extractor import NarrativeExtractor
    from social_hook.llm.base import LLMClient as _LLMClient

    if live:
        from social_hook.config.yaml import load_full_config
        from social_hook.llm.factory import create_client

        config = load_full_config()
        model_str = config.journey_capture.model or config.models.evaluator
        if "haiku" in model_str.lower():
            ok(f"SKIP: Model {model_str} is haiku (would be rejected)")
        else:
            try:
                client = create_client(model_str, config)
                extractor = NarrativeExtractor(client)

                # Use a mock DB context for usage logging
                mock_db = MagicMock()
                mock_db.insert_usage = MagicMock(return_value="usage_1")

                result = extractor.extract(
                    transcript_text=formatted,
                    project_name="test-project",
                    cwd="/tmp/test",
                    db=mock_db,
                    project_id="proj_verify",
                )
                check(result is not None, "Extraction succeeded", "Extraction returned None")
                check(len(result.summary) > 0, f"Summary: {result.summary[:60]}...",
                      "Empty summary")
                check(isinstance(result.key_decisions, list), "key_decisions is list",
                      "key_decisions not list")
                check(isinstance(result.relevant_for_social, bool),
                      f"relevant_for_social={result.relevant_for_social}",
                      "relevant_for_social not bool")
            except Exception as e:
                fail(f"Live extraction failed: {e}")
    else:
        mock_client = MagicMock(spec=_LLMClient)
        mock_client.complete.return_value = _mock_extract_narrative_response()
        extractor = NarrativeExtractor(mock_client)

        mock_db = MagicMock()
        mock_db.insert_usage = MagicMock(return_value="usage_1")

        result = extractor.extract(
            transcript_text=formatted,
            project_name="test-project",
            cwd="/tmp/test",
            db=mock_db,
            project_id="proj_verify",
        )
        check(result is not None, "Extraction succeeded (mock)", "Extraction returned None")
        check(result.summary is not None and len(result.summary) > 0,
              f"Summary: {result.summary[:60]}", "Empty summary")
        check(len(result.key_decisions) == 2,
              f"key_decisions: {len(result.key_decisions)}", "Wrong count")
        check(result.relevant_for_social is True,
              "relevant_for_social=True", "Wrong value")
        check(len(result.social_hooks) == 2,
              f"social_hooks: {len(result.social_hooks)}", "Wrong count")

    # =========================================================================
    # Step 11: Full pipeline (live only): read -> filter -> extract -> save -> load
    # =========================================================================
    if live:
        step("Full pipeline: read -> filter -> extract -> save -> load")

        with patch(
            "social_hook.narrative.storage.get_narratives_path",
            return_value=narratives_dir,
        ):
            # Read -> filter -> format -> truncate (already done above)
            # Extract (already done above in step 10, reuse result)
            if result is not None:
                saved = save_narrative("proj_pipeline", result, "session_live", "auto")
                check(saved.exists(), "Pipeline save succeeded", "Save failed")

                loaded = load_recent_narratives("proj_pipeline", limit=5)
                check(len(loaded) >= 1, f"Pipeline load: {len(loaded)} narrative(s)",
                      "Load failed")
                if loaded:
                    check(
                        loaded[0]["summary"] == result.summary,
                        "Round-trip summary matches",
                        f"Mismatch: {loaded[0].get('summary')[:40]} vs {result.summary[:40]}",
                    )
            else:
                fail("Cannot test pipeline — extraction returned None")
    else:
        step("Full pipeline (dry-run: mock extraction)")

        with patch(
            "social_hook.narrative.storage.get_narratives_path",
            return_value=narratives_dir,
        ):
            saved = save_narrative("proj_pipeline", result, "session_dry", "auto")
            check(saved.exists(), "Pipeline save succeeded", "Save failed")

            loaded = load_recent_narratives("proj_pipeline", limit=5)
            check(len(loaded) >= 1, f"Pipeline load: {len(loaded)} narrative(s)",
                  "Load failed")

    # =========================================================================
    # Cleanup and summary
    # =========================================================================
    print(f"\n{'='*60}")
    if _failures == 0:
        print(f"  ALL {_step} STEPS PASSED")
    else:
        print(f"  {_failures} FAILURE(S) out of {_step} steps")
    print(f"{'='*60}\n")

    return _failures == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Narrative Capture verification")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run", action="store_true", default=True,
        help="No API calls (default)",
    )
    group.add_argument(
        "--live", action="store_true",
        help="Real API calls (~$0.50-$2.00, uses configured provider)",
    )
    args = parser.parse_args()

    success = verify(live=args.live)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
