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
