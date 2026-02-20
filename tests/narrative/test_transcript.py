"""Tests for narrative.transcript — JSONL transcript reader + filter."""

import json
from pathlib import Path

import pytest

from social_hook.narrative.transcript import (
    discover_transcript_path,
    filter_for_extraction,
    format_for_prompt,
    read_transcript,
    truncate_to_budget,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_user_msg(content, *, is_sidechain=False):
    """Build a minimal user-type JSONL dict."""
    return {
        "type": "user",
        "message": {"role": "user", "content": content},
        "isSidechain": is_sidechain,
    }


def _make_assistant_msg(content, *, is_sidechain=False):
    """Build a minimal assistant-type JSONL dict."""
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": content},
        "isSidechain": is_sidechain,
    }


def _write_jsonl(path, entries):
    """Write a list of dicts as JSONL to a file."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


# =============================================================================
# read_transcript
# =============================================================================


class TestReadTranscript:
    """Tests for read_transcript."""

    def test_reads_valid_jsonl(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        entries = [
            _make_user_msg("Hello"),
            _make_assistant_msg([{"type": "text", "text": "Hi there"}]),
        ]
        _write_jsonl(transcript, entries)

        result = read_transcript(transcript)
        assert len(result) == 2
        assert result[0]["type"] == "user"
        assert result[1]["type"] == "assistant"

    def test_skips_malformed_lines(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        with open(transcript, "w") as f:
            f.write(json.dumps(_make_user_msg("Valid line")) + "\n")
            f.write("this is not valid json\n")
            f.write("{bad json\n")
            f.write(json.dumps(_make_assistant_msg("Also valid")) + "\n")

        result = read_transcript(transcript)
        assert len(result) == 2

    def test_filters_to_user_and_assistant_only(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        entries = [
            _make_user_msg("User message"),
            _make_assistant_msg("Assistant message"),
            {"type": "progress", "data": {"type": "hook_progress"}},
            {"type": "system", "subtype": "stop_hook_summary"},
            {"type": "queue-operation", "operation": "enqueue"},
            {"type": "file-history-snapshot", "snapshot": {}},
            {"type": "summary", "summary": "session summary", "leafUuid": "abc"},
        ]
        _write_jsonl(transcript, entries)

        result = read_transcript(transcript)
        assert len(result) == 2
        types = {r["type"] for r in result}
        assert types == {"user", "assistant"}

    def test_skips_empty_lines(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        with open(transcript, "w") as f:
            f.write(json.dumps(_make_user_msg("Hello")) + "\n")
            f.write("\n")
            f.write("   \n")
            f.write(json.dumps(_make_assistant_msg("World")) + "\n")

        result = read_transcript(transcript)
        assert len(result) == 2

    def test_skips_non_dict_json(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        with open(transcript, "w") as f:
            f.write(json.dumps(_make_user_msg("Valid")) + "\n")
            f.write(json.dumps([1, 2, 3]) + "\n")
            f.write(json.dumps("just a string") + "\n")

        result = read_transcript(transcript)
        assert len(result) == 1


# =============================================================================
# discover_transcript_path
# =============================================================================


class TestDiscoverTranscriptPath:
    """Tests for discover_transcript_path."""

    def test_constructs_correct_path(self, tmp_path, monkeypatch):
        # Simulate ~/.claude/projects/{encoded-cwd}/{session_id}.jsonl
        encoded_cwd = "-Users-neil-dev-project"
        projects_dir = tmp_path / ".claude" / "projects" / encoded_cwd
        projects_dir.mkdir(parents=True)
        transcript_file = projects_dir / "session123.jsonl"
        transcript_file.write_text("{}")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = discover_transcript_path("session123", "/Users/neil/dev/project")
        assert result is not None
        assert result == transcript_file

    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = discover_transcript_path("nonexistent", "/Users/neil/dev/project")
        assert result is None

    def test_encodes_cwd_correctly(self, tmp_path, monkeypatch):
        # Verify the encoding: /Users/neil/dev/my-project -> -Users-neil-dev-my-project
        encoded = "-Users-neil-dev-my-project"
        projects_dir = tmp_path / ".claude" / "projects" / encoded
        projects_dir.mkdir(parents=True)
        (projects_dir / "sess.jsonl").write_text("{}")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = discover_transcript_path("sess", "/Users/neil/dev/my-project")
        assert result is not None
        assert encoded in str(result)


# =============================================================================
# filter_for_extraction
# =============================================================================


class TestFilterForExtraction:
    """Tests for filter_for_extraction."""

    def test_strips_tool_use_blocks(self):
        msg = _make_assistant_msg([
            {"type": "text", "text": "I'll read the file"},
            {"type": "tool_use", "name": "Read", "input": {"path": "/etc/passwd"}},
        ])
        result = filter_for_extraction([msg])
        assert len(result) == 1
        blocks = result[0]["message"]["content"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"

    def test_strips_tool_result_blocks(self):
        msg = _make_user_msg([
            {"type": "tool_result", "content": "ANTHROPIC_API_KEY=sk-secret-key"},
        ])
        result = filter_for_extraction([msg])
        assert len(result) == 0  # No blocks left, message removed

    def test_strips_image_blocks(self):
        msg = _make_user_msg([
            {"type": "text", "text": "Here is a screenshot"},
            {"type": "image", "source": {"data": "base64data..."}},
        ])
        result = filter_for_extraction([msg])
        assert len(result) == 1
        blocks = result[0]["message"]["content"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"

    def test_keeps_text_blocks(self):
        msg = _make_assistant_msg([
            {"type": "text", "text": "Let me explain the architecture"},
        ])
        result = filter_for_extraction([msg])
        assert len(result) == 1
        blocks = result[0]["message"]["content"]
        assert len(blocks) == 1
        assert blocks[0]["text"] == "Let me explain the architecture"

    def test_keeps_thinking_blocks(self):
        msg = _make_assistant_msg([
            {"type": "thinking", "thinking": "The user wants to understand the design"},
            {"type": "text", "text": "Here is the design..."},
        ])
        result = filter_for_extraction([msg])
        assert len(result) == 1
        blocks = result[0]["message"]["content"]
        assert len(blocks) == 2
        assert blocks[0]["type"] == "thinking"
        assert blocks[1]["type"] == "text"

    def test_filters_out_sidechain_messages(self):
        msgs = [
            _make_user_msg("Main conversation", is_sidechain=False),
            _make_assistant_msg("Main reply", is_sidechain=False),
            _make_user_msg("Background task", is_sidechain=True),
            _make_assistant_msg("Background reply", is_sidechain=True),
        ]
        result = filter_for_extraction(msgs)
        assert len(result) == 2

    def test_handles_content_as_string(self):
        msg = _make_user_msg("Just a plain text message")
        result = filter_for_extraction([msg])
        assert len(result) == 1
        assert result[0]["message"]["content"] == "Just a plain text message"

    def test_handles_content_as_array(self):
        msg = _make_assistant_msg([
            {"type": "text", "text": "Response text"},
        ])
        result = filter_for_extraction([msg])
        assert len(result) == 1
        blocks = result[0]["message"]["content"]
        assert isinstance(blocks, list)
        assert len(blocks) == 1

    def test_removes_empty_text_blocks(self):
        msg = _make_assistant_msg([
            {"type": "text", "text": "\n\n"},
            {"type": "text", "text": "   "},
            {"type": "text", "text": "Actual content here"},
        ])
        result = filter_for_extraction([msg])
        assert len(result) == 1
        blocks = result[0]["message"]["content"]
        assert len(blocks) == 1
        assert blocks[0]["text"] == "Actual content here"

    def test_removes_message_when_all_blocks_filtered(self):
        msg = _make_user_msg([
            {"type": "tool_result", "content": "file contents here"},
        ])
        result = filter_for_extraction([msg])
        assert len(result) == 0

    def test_handles_whitespace_only_string_content(self):
        msg = _make_user_msg("   ")
        result = filter_for_extraction([msg])
        assert len(result) == 0

    def test_does_not_mutate_original(self):
        original_blocks = [
            {"type": "text", "text": "Keep this"},
            {"type": "tool_use", "name": "Bash", "input": {}},
        ]
        msg = _make_assistant_msg(list(original_blocks))
        filter_for_extraction([msg])
        # Original message should still have both blocks
        assert len(msg["message"]["content"]) == 2

    def test_handles_none_content(self):
        msg = {"type": "user", "message": {"role": "user", "content": None}}
        result = filter_for_extraction([msg])
        assert len(result) == 0

    def test_handles_missing_message(self):
        msg = {"type": "user"}
        result = filter_for_extraction([msg])
        assert len(result) == 0


# =============================================================================
# format_for_prompt
# =============================================================================


class TestFormatForPrompt:
    """Tests for format_for_prompt."""

    def test_user_assistant_format(self):
        msgs = [
            _make_user_msg("How does this work?"),
            _make_assistant_msg([{"type": "text", "text": "It works like this..."}]),
        ]
        filtered = filter_for_extraction(msgs)
        result = format_for_prompt(filtered)
        assert "[USER] How does this work?" in result
        assert "[ASSISTANT] It works like this..." in result

    def test_thinking_format(self):
        msg = _make_assistant_msg([
            {"type": "thinking", "thinking": "Let me analyze this"},
            {"type": "text", "text": "Here is my analysis"},
        ])
        filtered = filter_for_extraction([msg])
        result = format_for_prompt(filtered)
        assert "[ASSISTANT THINKING] Let me analyze this" in result
        assert "[ASSISTANT] Here is my analysis" in result

    def test_blocks_separated_by_double_newline(self):
        msgs = [
            _make_user_msg("Question"),
            _make_assistant_msg([{"type": "text", "text": "Answer"}]),
        ]
        filtered = filter_for_extraction(msgs)
        result = format_for_prompt(filtered)
        parts = result.split("\n\n")
        assert len(parts) == 2

    def test_string_content_uses_role_label(self):
        msg = _make_user_msg("Hello")
        filtered = filter_for_extraction([msg])
        result = format_for_prompt(filtered)
        assert result == "[USER] Hello"


# =============================================================================
# truncate_to_budget
# =============================================================================


class TestTruncateToBudget:
    """Tests for truncate_to_budget."""

    def test_no_truncation_when_under_budget(self):
        text = "Short text"
        result = truncate_to_budget(text, max_chars=100)
        assert result == text

    def test_no_truncation_when_exactly_at_budget(self):
        text = "x" * 100
        result = truncate_to_budget(text, max_chars=100)
        assert result == text

    def test_truncates_from_oldest_first(self):
        # Build text: oldest content at start, newest at end
        oldest = "OLDEST_CONTENT "
        newest = "NEWEST_CONTENT"
        text = oldest + ("x" * 100) + newest
        budget = 50
        result = truncate_to_budget(text, max_chars=budget)
        assert len(result) == budget
        assert newest in result
        assert oldest not in result

    def test_keeps_most_recent_content(self):
        parts = [f"[PART{i}] content for part {i}" for i in range(20)]
        text = "\n\n".join(parts)
        budget = 100
        result = truncate_to_budget(text, max_chars=budget)
        assert len(result) == budget
        # The last part should be preserved
        assert "PART19" in result

    def test_default_budget_is_100k(self):
        short_text = "x" * 50_000
        result = truncate_to_budget(short_text)
        assert result == short_text

        long_text = "x" * 150_000
        result = truncate_to_budget(long_text)
        assert len(result) == 100_000


# =============================================================================
# Integration: full pipeline
# =============================================================================


class TestPipelineIntegration:
    """End-to-end test of read -> filter -> format -> truncate."""

    def test_full_pipeline(self, tmp_path):
        transcript = tmp_path / "session.jsonl"
        entries = [
            _make_user_msg("Let's build a new feature"),
            _make_assistant_msg([
                {"type": "thinking", "thinking": "The user wants a new feature. I should plan the approach."},
                {"type": "text", "text": "I'll help you build that feature."},
                {"type": "tool_use", "name": "Read", "input": {"path": "/src/main.py"}},
            ]),
            _make_user_msg([
                {"type": "tool_result", "content": "def main(): pass"},
            ]),
            {"type": "progress", "data": {"type": "hook_progress"}},
            {"type": "system", "subtype": "stop_hook_summary"},
            _make_assistant_msg([
                {"type": "text", "text": "Here is the implementation."},
            ]),
        ]
        _write_jsonl(transcript, entries)

        messages = read_transcript(transcript)
        assert len(messages) == 4  # 2 user + 2 assistant (progress/system filtered)

        filtered = filter_for_extraction(messages)
        # user string msg, assistant with thinking+text (tool_use stripped),
        # user with tool_result stripped (removed entirely), assistant with text
        assert len(filtered) == 3

        text = format_for_prompt(filtered)
        assert "[USER] Let's build a new feature" in text
        assert "[ASSISTANT THINKING]" in text
        assert "[ASSISTANT] I'll help you build that feature." in text
        assert "[ASSISTANT] Here is the implementation." in text
        assert "tool_use" not in text
        assert "tool_result" not in text

        result = truncate_to_budget(text)
        assert len(result) <= 100_000


# =============================================================================
# Import test
# =============================================================================


class TestImports:
    """Verify transcript functions are importable from narrative package."""

    def test_importable_from_narrative(self):
        from social_hook.narrative import (
            discover_transcript_path,
            filter_for_extraction,
            format_for_prompt,
            read_transcript,
            truncate_to_budget,
        )
        assert callable(read_transcript)
        assert callable(discover_transcript_path)
        assert callable(filter_for_extraction)
        assert callable(format_for_prompt)
        assert callable(truncate_to_budget)
