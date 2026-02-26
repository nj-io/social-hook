"""Tests for filesystem and utilities (T4, T5, T6)."""

import json
import logging
import os
from pathlib import Path

import pytest

from social_hook.filesystem import generate_id, init_filesystem, get_base_path
from social_hook.constants import CONFIG_DIR_NAME
from social_hook.logging import setup_logging


# =============================================================================
# T4: File System Setup
# =============================================================================


class TestFilesystemSetup:
    """T4: File system setup tests."""

    def test_create_structure(self, temp_dir):
        """init_filesystem creates ~/.social-hook/ structure."""
        base = init_filesystem(temp_dir / CONFIG_DIR_NAME)
        assert base.exists()
        assert base.is_dir()

    def test_directory_contents(self, temp_dir):
        """init_filesystem creates required subdirectories."""
        base = init_filesystem(temp_dir / CONFIG_DIR_NAME)

        assert (base / "migrations").exists()
        assert (base / "logs").exists()
        assert (base / "media-cache").exists()
        assert (base / "prompts").exists()

    def test_example_files_created(self, temp_dir):
        """init_filesystem creates .env.example and config.yaml.example."""
        base = init_filesystem(temp_dir / CONFIG_DIR_NAME)

        assert (base / ".env.example").exists()
        assert (base / "config.yaml.example").exists()

        # Check content
        env_example = (base / ".env.example").read_text()
        assert "ANTHROPIC_API_KEY" in env_example

        config_example = (base / "config.yaml.example").read_text()
        assert "models:" in config_example

    def test_env_permissions(self, temp_dir):
        """Existing .env file has mode 0o600."""
        base = temp_dir / CONFIG_DIR_NAME
        base.mkdir(parents=True)

        env_file = base / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=test\n")
        os.chmod(env_file, 0o644)  # Start with different permissions

        init_filesystem(base)

        # Check permissions (only on Unix-like systems)
        stat_info = env_file.stat()
        mode = stat_info.st_mode & 0o777
        assert mode == 0o600

    def test_idempotent(self, temp_dir):
        """Running init_filesystem twice causes no error."""
        base = temp_dir / CONFIG_DIR_NAME

        init_filesystem(base)
        init_filesystem(base)  # Second call

        assert base.exists()
        assert (base / "logs").exists()

    def test_custom_base_path(self, temp_dir):
        """init_filesystem with custom path creates at custom location."""
        custom_path = temp_dir / "custom" / "location"
        base = init_filesystem(custom_path)

        assert base == custom_path
        assert custom_path.exists()


# =============================================================================
# T5: Logging
# =============================================================================


class TestLogging:
    """T5: Logging tests."""

    def test_setup_logger(self, temp_dir):
        """setup_logging returns configured logger."""
        log_dir = temp_dir / "logs"
        logger = setup_logging("trigger", log_dir=log_dir)

        assert logger is not None

    def test_log_info(self, temp_dir):
        """Log INFO creates JSON line in component.log."""
        log_dir = temp_dir / "logs"
        logger = setup_logging("trigger", log_dir=log_dir)

        logger.info("test message", event="decision_made")

        log_file = log_dir / "trigger.log"
        assert log_file.exists()

        content = log_file.read_text()
        log_entry = json.loads(content.strip())

        assert log_entry["level"] == "INFO"
        assert log_entry["message"] == "test message"
        assert log_entry["event"] == "decision_made"
        assert log_entry["component"] == "trigger"

    def test_log_format(self, temp_dir):
        """Log format has timestamp, level, component, event."""
        log_dir = temp_dir / "logs"
        logger = setup_logging("scheduler", log_dir=log_dir)

        logger.info("test", event="tick", project_id="proj-123")

        log_file = log_dir / "scheduler.log"
        content = log_file.read_text()
        log_entry = json.loads(content.strip())

        assert "timestamp" in log_entry
        assert "level" in log_entry
        assert "component" in log_entry
        assert log_entry["component"] == "scheduler"

    def test_log_to_correct_file(self, temp_dir):
        """Each component logs to its own file."""
        log_dir = temp_dir / "logs"

        logger1 = setup_logging("trigger", log_dir=log_dir)
        logger2 = setup_logging("scheduler", log_dir=log_dir)

        logger1.info("trigger message")
        logger2.info("scheduler message")

        trigger_log = log_dir / "trigger.log"
        scheduler_log = log_dir / "scheduler.log"

        assert trigger_log.exists()
        assert scheduler_log.exists()

        assert "trigger message" in trigger_log.read_text()
        assert "scheduler message" in scheduler_log.read_text()

    def test_debug_level_disabled_by_default(self, temp_dir):
        """Debug messages not written at INFO level."""
        log_dir = temp_dir / "logs"
        logger = setup_logging("test", level=logging.INFO, log_dir=log_dir)

        logger.debug("debug message")
        logger.info("info message")

        log_file = log_dir / "test.log"
        content = log_file.read_text()

        assert "debug message" not in content
        assert "info message" in content


# =============================================================================
# T6: ID Generation
# =============================================================================


class TestIdGeneration:
    """T6: ID generation tests."""

    def test_generate_id_format(self):
        """generate_id returns prefix + 12 hex chars."""
        id = generate_id("draft")
        assert id.startswith("draft_")
        assert len(id) == len("draft_") + 12

        # Check the suffix is hex
        suffix = id.split("_")[1]
        int(suffix, 16)  # Should not raise

    def test_uniqueness(self):
        """1000 generated IDs are all unique."""
        ids = [generate_id("test") for _ in range(1000)]
        assert len(set(ids)) == 1000

    def test_empty_prefix_raises(self):
        """Empty prefix raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            generate_id("")

        assert "Prefix cannot be empty" in str(exc_info.value)

    def test_different_prefixes(self):
        """Different prefixes produce different ID formats."""
        draft_id = generate_id("draft")
        decision_id = generate_id("decision")
        project_id = generate_id("project")

        assert draft_id.startswith("draft_")
        assert decision_id.startswith("decision_")
        assert project_id.startswith("project_")
