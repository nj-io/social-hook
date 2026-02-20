"""Tests for narrative.storage — JSONL narrative storage."""

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from social_hook.narrative.storage import (
    cleanup_old_narratives,
    load_recent_narratives,
    save_narrative,
)


# =============================================================================
# Helpers
# =============================================================================


@dataclass
class FakeExtraction:
    """Minimal stand-in for ExtractNarrativeInput."""

    summary: str = "Built a login page"
    key_decisions: list[str] = field(default_factory=lambda: ["Used JWT tokens"])
    rejected_approaches: list[str] = field(default_factory=lambda: ["Session cookies"])
    aha_moments: list[str] = field(default_factory=lambda: ["OAuth was simpler"])
    challenges: list[str] = field(default_factory=lambda: ["CORS issues"])
    narrative_arc: str = "Started with cookies, switched to JWT."
    relevant_for_social: bool = True
    social_hooks: list[str] = field(default_factory=lambda: ["Why we ditched cookies"])


def _read_jsonl(path: Path) -> list[dict]:
    """Read all JSON lines from a file."""
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


# =============================================================================
# save_narrative
# =============================================================================


class TestSaveNarrative:
    """Tests for save_narrative."""

    def test_creates_file_and_appends(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        extraction = FakeExtraction()
        result = save_narrative("my-project", extraction, "sess-001", "auto")

        assert result == tmp_path / "my-project.jsonl"
        assert result.exists()

        entries = _read_jsonl(result)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["session_id"] == "sess-001"
        assert entry["trigger"] == "auto"
        assert entry["summary"] == "Built a login page"
        assert entry["key_decisions"] == ["Used JWT tokens"]
        assert entry["relevant_for_social"] is True
        assert "timestamp" in entry

    def test_appends_multiple_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        extraction = FakeExtraction()

        save_narrative("proj", extraction, "sess-001", "auto")
        save_narrative("proj", extraction, "sess-002", "manual")

        entries = _read_jsonl(tmp_path / "proj.jsonl")
        assert len(entries) == 2
        assert entries[0]["session_id"] == "sess-001"
        assert entries[1]["session_id"] == "sess-002"


# =============================================================================
# load_recent_narratives
# =============================================================================


class TestLoadRecentNarratives:
    """Tests for load_recent_narratives."""

    def test_returns_only_relevant_for_social(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        relevant = FakeExtraction(relevant_for_social=True)
        irrelevant = FakeExtraction(relevant_for_social=False)

        save_narrative("proj", relevant, "sess-001", "auto")
        save_narrative("proj", irrelevant, "sess-002", "auto")
        save_narrative("proj", relevant, "sess-003", "auto")

        result = load_recent_narratives("proj")
        assert len(result) == 2
        assert all(e["relevant_for_social"] is True for e in result)

    def test_deduplicates_by_session_id_keeps_latest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        early = FakeExtraction(summary="First attempt")
        later = FakeExtraction(summary="Second attempt")

        save_narrative("proj", early, "sess-001", "auto")
        save_narrative("proj", later, "sess-001", "auto")

        result = load_recent_narratives("proj")
        assert len(result) == 1
        assert result[0]["summary"] == "Second attempt"

    def test_respects_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        extraction = FakeExtraction()
        for i in range(10):
            save_narrative("proj", extraction, f"sess-{i:03}", "auto")

        result = load_recent_narratives("proj", limit=3)
        assert len(result) == 3

    def test_returns_most_recent_first(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        for i in range(5):
            ext = FakeExtraction(summary=f"Session {i}")
            save_narrative("proj", ext, f"sess-{i:03}", "auto")

        result = load_recent_narratives("proj")
        # Most recent (last written) should come first.
        assert result[0]["summary"] == "Session 4"
        assert result[-1]["summary"] == "Session 0"

    def test_handles_empty_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        (tmp_path / "proj.jsonl").write_text("")

        result = load_recent_narratives("proj")
        assert result == []

    def test_handles_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        result = load_recent_narratives("proj")
        assert result == []


# =============================================================================
# cleanup_old_narratives
# =============================================================================


# =============================================================================
# load_recent_narratives: time-window filtering
# =============================================================================


class TestLoadRecentNarrativesTimeWindow:
    """Tests for time-window filtering in load_recent_narratives."""

    def _write_entry(self, path: Path, session_id: str, ts: str, summary: str = ""):
        """Write a narrative entry with a specific timestamp."""
        record = {
            "timestamp": ts,
            "session_id": session_id,
            "trigger": "auto",
            "summary": summary or f"Session {session_id}",
            "key_decisions": [],
            "rejected_approaches": [],
            "aha_moments": [],
            "challenges": [],
            "narrative_arc": "",
            "relevant_for_social": True,
            "social_hooks": [],
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def test_no_window_params_backwards_compatible(self, tmp_path, monkeypatch):
        """Without after/before, all entries get _in_window=True."""
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        extraction = FakeExtraction()
        save_narrative("proj", extraction, "sess-001", "auto")

        result = load_recent_narratives("proj")
        assert len(result) == 1
        assert result[0]["_in_window"] is True

    def test_in_window_entries_returned_first(self, tmp_path, monkeypatch):
        """In-window entries come before out-of-window entries."""
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"

        # Old entry (before window)
        self._write_entry(path, "old-sess", "2026-02-18T10:00:00+00:00", "Old session")
        # In-window entry
        self._write_entry(path, "in-sess", "2026-02-19T15:00:00+00:00", "In-window session")
        # Another old entry
        self._write_entry(path, "old2-sess", "2026-02-17T10:00:00+00:00", "Older session")

        result = load_recent_narratives(
            "proj", limit=5,
            after="2026-02-19T10:00:00+00:00",
            before="2026-02-20T10:00:00+00:00",
        )
        assert len(result) == 3
        # In-window first
        assert result[0]["summary"] == "In-window session"
        assert result[0]["_in_window"] is True
        # Then out-of-window (most recent first)
        assert result[1]["_in_window"] is False
        assert result[2]["_in_window"] is False

    def test_timezone_safe_comparison(self, tmp_path, monkeypatch):
        """UTC narrative timestamp compared with +07:00 window boundary."""
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"

        # Narrative at 11:00 UTC = 18:00+07:00
        self._write_entry(path, "sess-1", "2026-02-20T11:00:00+00:00", "UTC narrative")

        # Window: after 10:30+07:00 (= 03:30 UTC), before 18:30+07:00 (= 11:30 UTC)
        result = load_recent_narratives(
            "proj", limit=5,
            after="2026-02-20T10:30:00+07:00",
            before="2026-02-20T18:30:00+07:00",
        )
        assert len(result) == 1
        assert result[0]["_in_window"] is True

    def test_boundary_exclusive_after_inclusive_before(self, tmp_path, monkeypatch):
        """after is exclusive (>), before is inclusive (<=)."""
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"

        # Entry exactly at after boundary
        self._write_entry(path, "at-after", "2026-02-20T10:00:00+00:00", "At after")
        # Entry exactly at before boundary
        self._write_entry(path, "at-before", "2026-02-20T12:00:00+00:00", "At before")
        # Entry between boundaries
        self._write_entry(path, "between", "2026-02-20T11:00:00+00:00", "Between")

        result = load_recent_narratives(
            "proj", limit=5,
            after="2026-02-20T10:00:00+00:00",
            before="2026-02-20T12:00:00+00:00",
        )
        # "At after" (== after) should be out-of-window (exclusive)
        # "At before" (== before) should be in-window (inclusive)
        # "Between" should be in-window
        in_window = [e for e in result if e["_in_window"]]
        out_of_window = [e for e in result if not e["_in_window"]]
        assert len(in_window) == 2
        assert len(out_of_window) == 1
        assert out_of_window[0]["summary"] == "At after"

    def test_empty_window_returns_extended_context(self, tmp_path, monkeypatch):
        """When no narratives fall in window, out-of-window entries still returned."""
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"

        self._write_entry(path, "old-1", "2026-02-18T10:00:00+00:00", "Old 1")
        self._write_entry(path, "old-2", "2026-02-17T10:00:00+00:00", "Old 2")

        # Window is in the future — no entries match
        result = load_recent_narratives(
            "proj", limit=5,
            after="2026-02-25T00:00:00+00:00",
            before="2026-02-26T00:00:00+00:00",
        )
        assert len(result) == 2
        assert all(not e["_in_window"] for e in result)

    def test_limit_respected_with_window(self, tmp_path, monkeypatch):
        """Limit applies to total returned (in-window + extended)."""
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"

        # 3 in-window, 5 out-of-window
        for i in range(3):
            self._write_entry(path, f"in-{i}", f"2026-02-20T{10+i}:00:00+00:00")
        for i in range(5):
            self._write_entry(path, f"out-{i}", f"2026-02-18T{10+i}:00:00+00:00")

        result = load_recent_narratives(
            "proj", limit=4,
            after="2026-02-20T00:00:00+00:00",
            before="2026-02-21T00:00:00+00:00",
        )
        assert len(result) == 4
        # All 3 in-window + 1 extended
        in_window = [e for e in result if e["_in_window"]]
        out_of_window = [e for e in result if not e["_in_window"]]
        assert len(in_window) == 3
        assert len(out_of_window) == 1

    def test_only_after_boundary(self, tmp_path, monkeypatch):
        """With only after (no before), all entries after the boundary are in-window."""
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"

        self._write_entry(path, "old", "2026-02-18T10:00:00+00:00")
        self._write_entry(path, "new", "2026-02-20T10:00:00+00:00")

        result = load_recent_narratives(
            "proj", limit=5,
            after="2026-02-19T00:00:00+00:00",
        )
        in_window = [e for e in result if e["_in_window"]]
        assert len(in_window) == 1
        assert in_window[0]["session_id"] == "new"

    def test_only_before_boundary(self, tmp_path, monkeypatch):
        """With only before (no after), all entries before the boundary are in-window."""
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"

        self._write_entry(path, "early", "2026-02-18T10:00:00+00:00")
        self._write_entry(path, "late", "2026-02-25T10:00:00+00:00")

        result = load_recent_narratives(
            "proj", limit=5,
            before="2026-02-20T00:00:00+00:00",
        )
        in_window = [e for e in result if e["_in_window"]]
        out_of_window = [e for e in result if not e["_in_window"]]
        assert len(in_window) == 1
        assert in_window[0]["session_id"] == "early"
        assert len(out_of_window) == 1


class TestCleanupOldNarratives:
    """Tests for cleanup_old_narratives."""

    def _write_entry_with_timestamp(self, path: Path, session_id: str, ts: str):
        """Write a single narrative entry with a specific timestamp."""
        record = {
            "timestamp": ts,
            "session_id": session_id,
            "trigger": "auto",
            "summary": f"Session {session_id}",
            "key_decisions": [],
            "rejected_approaches": [],
            "aha_moments": [],
            "challenges": [],
            "narrative_arc": "",
            "relevant_for_social": True,
            "social_hooks": [],
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def test_removes_old_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"
        now = datetime.datetime.now(datetime.timezone.utc)
        old_ts = (now - datetime.timedelta(days=100)).isoformat()
        recent_ts = (now - datetime.timedelta(days=10)).isoformat()

        self._write_entry_with_timestamp(path, "old-sess", old_ts)
        self._write_entry_with_timestamp(path, "recent-sess", recent_ts)

        removed = cleanup_old_narratives("proj", max_age_days=90)
        assert removed == 1

        entries = _read_jsonl(path)
        assert len(entries) == 1
        assert entries[0]["session_id"] == "recent-sess"

    def test_keeps_recent_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"
        now = datetime.datetime.now(datetime.timezone.utc)

        for i in range(5):
            ts = (now - datetime.timedelta(days=i)).isoformat()
            self._write_entry_with_timestamp(path, f"sess-{i}", ts)

        removed = cleanup_old_narratives("proj", max_age_days=90)
        assert removed == 0
        assert len(_read_jsonl(path)) == 5

    def test_handles_empty_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        (tmp_path / "proj.jsonl").write_text("")

        removed = cleanup_old_narratives("proj")
        assert removed == 0

    def test_handles_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        removed = cleanup_old_narratives("proj")
        assert removed == 0

    def test_returns_correct_count(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "social_hook.narrative.storage.get_narratives_path", lambda: tmp_path
        )
        path = tmp_path / "proj.jsonl"
        now = datetime.datetime.now(datetime.timezone.utc)

        # Write 3 old and 2 recent entries.
        for i in range(3):
            ts = (now - datetime.timedelta(days=100 + i)).isoformat()
            self._write_entry_with_timestamp(path, f"old-{i}", ts)
        for i in range(2):
            ts = (now - datetime.timedelta(days=i)).isoformat()
            self._write_entry_with_timestamp(path, f"new-{i}", ts)

        removed = cleanup_old_narratives("proj", max_age_days=90)
        assert removed == 3
        assert len(_read_jsonl(path)) == 2
