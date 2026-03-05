"""Tests for memory CRUD helpers in config/project.py."""

import pytest

from social_hook.config.project import (
    clear_memories,
    delete_memory,
    list_memories,
    save_memory,
)
from social_hook.constants import CONFIG_DIR_NAME


@pytest.fixture()
def project_dir(tmp_path):
    """Create a temp project directory with .social-hook dir."""
    config_dir = tmp_path / CONFIG_DIR_NAME
    config_dir.mkdir()
    return tmp_path


class TestMemoryHelpers:
    def test_list_memories_existing(self, project_dir):
        """list_memories returns correct entries."""
        save_memory(project_dir, "tweet about API", "Too formal", "draft_001")
        save_memory(project_dir, "thread about CLI", "Great tone", "draft_002")
        memories = list_memories(project_dir)
        assert len(memories) == 2
        assert memories[0]["context"] == "tweet about API"
        assert memories[1]["feedback"] == "Great tone"

    def test_list_memories_no_file(self, project_dir):
        """list_memories returns [] when no file exists."""
        memories = list_memories(project_dir)
        assert memories == []

    def test_delete_memory_valid(self, project_dir):
        """delete_memory removes the correct entry."""
        save_memory(project_dir, "ctx1", "fb1", "d1")
        save_memory(project_dir, "ctx2", "fb2", "d2")
        save_memory(project_dir, "ctx3", "fb3", "d3")
        delete_memory(project_dir, 1)  # 0-based, remove ctx2
        memories = list_memories(project_dir)
        assert len(memories) == 2
        assert memories[0]["context"] == "ctx1"
        assert memories[1]["context"] == "ctx3"

    def test_delete_memory_out_of_range(self, project_dir):
        """delete_memory raises IndexError for invalid index."""
        save_memory(project_dir, "ctx", "fb", "d")
        with pytest.raises(IndexError):
            delete_memory(project_dir, 5)

    def test_clear_memories(self, project_dir):
        """clear_memories returns count and empties file."""
        save_memory(project_dir, "ctx1", "fb1", "d1")
        save_memory(project_dir, "ctx2", "fb2", "d2")
        count = clear_memories(project_dir)
        assert count == 2
        assert list_memories(project_dir) == []

    def test_pipe_escape_roundtrip(self, project_dir):
        """Memory with | in feedback survives write -> read roundtrip."""
        save_memory(project_dir, "test|pipe", "feedback with | chars", "d|1")
        memories = list_memories(project_dir)
        assert len(memories) == 1
        assert memories[0]["context"] == "test|pipe"
        assert memories[0]["feedback"] == "feedback with | chars"
        assert memories[0]["draft_id"] == "d|1"

    def test_newline_sanitization(self, project_dir):
        """Memory with newlines in context is stored as single line."""
        save_memory(project_dir, "line1\nline2\nline3", "multi\nline", "d1")
        memories = list_memories(project_dir)
        assert len(memories) == 1
        assert "\n" not in memories[0]["context"]
        assert memories[0]["context"] == "line1 line2 line3"
        assert memories[0]["feedback"] == "multi line"
