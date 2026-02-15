"""Pytest fixtures for social-hook tests."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from social_hook.db import get_connection, init_database
from social_hook.filesystem import init_filesystem


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_db(temp_dir):
    """Create a temporary database."""
    db_path = temp_dir / "test.db"
    conn = init_database(db_path)
    yield conn
    conn.close()


@pytest.fixture
def temp_base(temp_dir):
    """Initialize social-hook filesystem in a temp directory."""
    base = init_filesystem(temp_dir / ".social-hook")
    yield base


@pytest.fixture
def temp_env_file(temp_dir):
    """Create a temporary .env file with test values."""
    env_path = temp_dir / ".env"
    env_path.write_text(
        """\
ANTHROPIC_API_KEY=sk-ant-test-key
TELEGRAM_BOT_TOKEN=123456:ABC
"""
    )
    yield env_path


@pytest.fixture
def temp_config_file(temp_dir):
    """Create a temporary config.yaml file."""
    config_path = temp_dir / "config.yaml"
    config_path.write_text(
        """\
models:
  evaluator: anthropic/claude-opus-4-5
  drafter: anthropic/claude-sonnet-4-5
  gatekeeper: anthropic/claude-haiku-4-5

platforms:
  x:
    enabled: true
    account_tier: free
  linkedin:
    enabled: false

scheduling:
  timezone: America/Los_Angeles
  max_posts_per_day: 3
  min_gap_minutes: 30
"""
    )
    yield config_path


@pytest.fixture
def temp_project_dir(temp_dir):
    """Create a temporary project directory with config files in .social-hook/."""
    project_dir = temp_dir / "my-project"
    project_dir.mkdir()

    # Create .social-hook subdirectory
    config_dir = project_dir / ".social-hook"
    config_dir.mkdir()

    # Create social-context.md
    (config_dir / "social-context.md").write_text(
        """\
# Social Context

## Voice
Technical but approachable.

## Audience
Developers interested in automation.
"""
    )

    # Create content-config.yaml
    (config_dir / "content-config.yaml").write_text(
        """\
platforms:
  x:
    enabled: true
    threads:
      enabled: true
      max_tweets: 5
"""
    )

    # Create memories.md
    (config_dir / "memories.md").write_text(
        """\
# Voice Memories

| Date | Context | Feedback | Draft ID |
|------|---------|----------|----------|
| 2026-01-30 | Technical architecture | "Too many emojis" | draft-001 |
"""
    )

    yield project_dir
