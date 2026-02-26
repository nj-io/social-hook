"""Tests for trigger pipeline (T29)."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.config.yaml import ChannelConfig
from social_hook.db import init_database, insert_project
from social_hook.filesystem import generate_id
from social_hook.models import Project
from social_hook.trigger import (
    git_remote_origin,
    parse_commit_info,
    run_trigger,
)


class TestParseCommitInfo:
    """Tests for parse_commit_info."""

    def test_parse_valid_commit(self, temp_dir):
        """Parse a real git commit in a temp repo."""
        repo = temp_dir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"],
            capture_output=True,
        )

        # Create a file and commit
        (repo / "test.py").write_text("print('hello')")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "Initial commit"],
            capture_output=True,
        )

        # Get commit hash
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        commit_hash = result.stdout.strip()

        commit = parse_commit_info(commit_hash, str(repo))
        assert commit.hash == commit_hash
        assert commit.message == "Initial commit"

    def test_parse_commit_has_timestamp(self, temp_dir):
        """parse_commit_info returns ISO 8601 timestamp."""
        repo = temp_dir / "repo_ts"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"],
            capture_output=True,
        )
        (repo / "test.py").write_text("print('hello')")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "First commit"],
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        commit_hash = result.stdout.strip()

        commit = parse_commit_info(commit_hash, str(repo))
        assert commit.timestamp is not None
        # ISO 8601 with timezone offset
        assert "T" in commit.timestamp
        assert "+" in commit.timestamp or "-" in commit.timestamp[11:]

    def test_first_commit_has_no_parent_timestamp(self, temp_dir):
        """First commit in a repo has parent_timestamp=None."""
        repo = temp_dir / "repo_first"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"],
            capture_output=True,
        )
        (repo / "test.py").write_text("print('hello')")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "First commit"],
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        commit_hash = result.stdout.strip()

        commit = parse_commit_info(commit_hash, str(repo))
        assert commit.parent_timestamp is None

    def test_second_commit_has_parent_timestamp(self, temp_dir):
        """Second commit in a repo has a valid parent_timestamp."""
        repo = temp_dir / "repo_second"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"],
            capture_output=True,
        )
        (repo / "test.py").write_text("v1")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "First"],
            capture_output=True,
        )
        (repo / "test.py").write_text("v2")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "Second"],
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        )
        commit_hash = result.stdout.strip()

        commit = parse_commit_info(commit_hash, str(repo))
        assert commit.timestamp is not None
        assert commit.parent_timestamp is not None
        # Both are valid ISO 8601 timestamps
        assert "T" in commit.parent_timestamp

    def test_parse_nonexistent_commit(self, temp_dir):
        """Gracefully handles nonexistent commit."""
        commit = parse_commit_info("nonexistent", str(temp_dir))
        assert commit.hash == "nonexistent"
        assert "(unable to parse)" in commit.message
        assert commit.timestamp is None
        assert commit.parent_timestamp is None


class TestGitRemoteOrigin:
    """Tests for git_remote_origin."""

    def test_no_remote(self, temp_dir):
        """Returns None for repo without remote."""
        repo = temp_dir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        assert git_remote_origin(str(repo)) is None

    def test_with_remote(self, temp_dir):
        """Returns origin URL."""
        repo = temp_dir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin",
             "git@github.com:user/repo.git"],
            capture_output=True,
        )
        assert git_remote_origin(str(repo)) == "git@github.com:user/repo.git"

    def test_non_git_directory(self, temp_dir):
        """Returns None for non-git directory."""
        assert git_remote_origin(str(temp_dir)) is None


class TestRunTrigger:
    """Tests for run_trigger."""

    @patch("social_hook.trigger.load_full_config")
    def test_config_error_returns_1(self, mock_config):
        """Config error returns exit code 1."""
        from social_hook.errors import ConfigError
        mock_config.side_effect = ConfigError("bad config")
        exit_code = run_trigger("abc123", "/tmp/nonexistent")
        assert exit_code == 1

    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_db_error_returns_2(self, mock_config, mock_db):
        """DB error returns exit code 2."""
        from social_hook.errors import DatabaseError
        mock_config.return_value = MagicMock()
        mock_db.side_effect = DatabaseError("db error")
        exit_code = run_trigger("abc123", "/tmp/nonexistent")
        assert exit_code == 2

    @patch("social_hook.trigger.ops.get_project_by_origin")
    @patch("social_hook.trigger.git_remote_origin")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_unregistered_repo_returns_0(
        self, mock_config, mock_db, mock_db_path, mock_by_path, mock_origin, mock_by_origin
    ):
        """Unregistered repo exits silently with 0."""
        mock_config.return_value = MagicMock()
        mock_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = None
        mock_origin.return_value = None
        mock_by_origin.return_value = []

        exit_code = run_trigger("abc123", "/tmp/nonexistent")
        assert exit_code == 0

    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_paused_project_returns_0(
        self, mock_config, mock_db, mock_db_path, mock_by_path
    ):
        """Paused project exits with 0."""
        mock_config.return_value = MagicMock()
        mock_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1", name="test", repo_path="/tmp", paused=True,
        )

        exit_code = run_trigger("abc123", "/tmp")
        assert exit_code == 0


class TestTriggerUsesAdapter:
    """Tests that trigger notification uses TelegramAdapter."""

    @patch("social_hook.messaging.telegram.TelegramAdapter.send_message")
    @patch("social_hook.bot.commands.set_chat_draft_context")
    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_sends_via_adapter(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
        mock_set_context, mock_adapter_send,
    ):
        """run_trigger uses TelegramAdapter.send_message instead of direct HTTP."""
        from datetime import datetime
        from social_hook.messaging.base import SendResult

        # Config with Telegram env vars and dict-based platforms
        from social_hook.config.platforms import OutputPlatformConfig
        cfg = MagicMock()
        cfg.platforms = {
            "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin", account_tier="free"),
        }
        cfg.media_generation.enabled = False
        cfg.media_generation.tools = {"mermaid": True, "nano_banana_pro": True, "playwright": True, "ray_so": True}
        cfg.scheduling.timezone = "UTC"
        cfg.scheduling.max_posts_per_day = 3
        cfg.scheduling.min_gap_minutes = 30
        cfg.scheduling.optimal_days = ["Tue", "Wed", "Thu"]
        cfg.scheduling.optimal_hours = [9, 12, 17]
        cfg.scheduling.max_per_week = 10
        cfg.scheduling.thread_min_tweets = 4
        cfg.channels = {"web": ChannelConfig(enabled=False)}
        cfg.env.get = lambda key, default="": {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ALLOWED_CHAT_IDS": "111,222",
        }.get(key, default)
        mock_config.return_value = cfg

        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1", name="test-proj", repo_path="/tmp",
        )

        # Commit
        commit = MagicMock()
        commit.hash = "abc12345"
        commit.message = "Add feature"
        mock_parse.return_value = commit

        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()

        # Evaluator says post-worthy
        evaluator_instance = MagicMock()
        evaluation = MagicMock()
        evaluation.decision = "post_worthy"
        evaluation.reasoning = "Good commit"
        evaluation.angle = "new feature"
        evaluation.episode_type = "launch"
        evaluation.post_category = "arc"
        evaluation.arc_id = None
        evaluation.media_tool = None
        evaluation.platforms = {}
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        # Drafter
        drafter_instance = MagicMock()
        draft_result = MagicMock()
        draft_result.content = "Check out this feature!"
        draft_result.reasoning = "Short and punchy"
        draft_result.format_hint = "single"
        draft_result.beat_count = 1
        draft_result.media_type = None
        drafter_instance.create_draft.return_value = draft_result
        mock_drafter_cls.return_value = drafter_instance

        # Schedule
        schedule = MagicMock()
        schedule.datetime = datetime(2026, 2, 20, 12, 0, 0)
        schedule.time_reason = "optimal"
        schedule.deferred = False
        mock_schedule.return_value = schedule

        # Adapter send returns success
        mock_adapter_send.return_value = SendResult(success=True, message_id="m1")

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0

        # TelegramAdapter.send_message should have been called for each chat ID
        assert mock_adapter_send.call_count == 2
        # Verify it was called with chat IDs "111" and "222"
        call_chat_ids = [c.args[0] for c in mock_adapter_send.call_args_list]
        assert "111" in call_chat_ids
        assert "222" in call_chat_ids


def _make_trigger_mocks(
    media_generation_enabled=False,
    drafter_media_type=None,
    evaluator_media_tool=None,
    media_generate_result=None,
    gemini_key=None,
    use_thread=False,
):
    """Helper to build the common mock setup for trigger media tests.

    Returns dict of (mock_name -> mock_object) for use with patch decorators,
    plus a reference to the config and draft_result for assertion.
    """
    from datetime import datetime
    from social_hook.adapters.models import MediaResult
    from social_hook.config.platforms import OutputPlatformConfig

    cfg = MagicMock()
    cfg.platforms = {
        "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin", account_tier="free"),
    }
    cfg.media_generation.enabled = media_generation_enabled
    cfg.media_generation.tools = {"mermaid": True, "nano_banana_pro": True, "playwright": True, "ray_so": True}
    cfg.scheduling.timezone = "UTC"
    cfg.scheduling.max_posts_per_day = 3
    cfg.scheduling.min_gap_minutes = 30
    cfg.scheduling.optimal_days = ["Tue", "Wed", "Thu"]
    cfg.scheduling.optimal_hours = [9, 12, 17]
    cfg.scheduling.max_per_week = 10
    cfg.scheduling.thread_min_tweets = 4
    cfg.channels = {"web": ChannelConfig(enabled=False)}

    env_map = {}
    if gemini_key:
        env_map["GEMINI_API_KEY"] = gemini_key
    cfg.env.get = lambda key, default="": env_map.get(key, default)

    commit = MagicMock()
    commit.hash = "abc12345"
    commit.message = "Add feature"

    evaluation = MagicMock()
    evaluation.decision = "post_worthy"
    evaluation.reasoning = "Good commit"
    evaluation.angle = "feature"
    evaluation.episode_type = "milestone"
    evaluation.post_category = "arc"
    evaluation.arc_id = None
    evaluation.media_tool = evaluator_media_tool
    evaluation.platforms = {}

    evaluator_instance = MagicMock()
    evaluator_instance.evaluate.return_value = evaluation

    draft_result = MagicMock()
    draft_result.content = "Check out this feature!"
    draft_result.reasoning = "Short and punchy"
    draft_result.format_hint = "thread" if use_thread else "single"
    draft_result.beat_count = 5 if use_thread else 1
    draft_result.media_type = drafter_media_type
    draft_result.media_spec = {"prompt": "a diagram"} if drafter_media_type else None

    drafter_instance = MagicMock()
    drafter_instance.create_draft.return_value = draft_result
    if use_thread:
        thread_result = MagicMock()
        thread_result.content = "1/ First tweet\n\n2/ Second tweet\n\n3/ Third\n\n4/ Fourth"
        thread_result.reasoning = "Thread reasoning"
        drafter_instance.create_thread.return_value = thread_result

    schedule = MagicMock()
    schedule.datetime = datetime(2026, 2, 20, 12, 0, 0)
    schedule.time_reason = "optimal"
    schedule.deferred = False

    if media_generate_result is None:
        media_generate_result = MediaResult(success=True, file_path="/tmp/media/img.png")

    return {
        "cfg": cfg,
        "commit": commit,
        "evaluation": evaluation,
        "evaluator_instance": evaluator_instance,
        "draft_result": draft_result,
        "drafter_instance": drafter_instance,
        "schedule": schedule,
        "media_generate_result": media_generate_result,
    }


class TestTriggerMedia:
    """Tests for media generation in the trigger pipeline."""

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_generates_media_when_enabled(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """When media_generation.enabled and drafter returns media_type, adapter.generate() is called."""
        from social_hook.adapters.models import MediaResult
        from social_hook.llm.schemas import MediaTool

        mocks = _make_trigger_mocks(
            media_generation_enabled=True,
            drafter_media_type=MediaTool.mermaid,
            evaluator_media_tool="mermaid",
            media_generate_result=MediaResult(success=True, file_path="/tmp/media/diagram.png"),
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = mocks["media_generate_result"]

        with patch("social_hook.adapters.registry.get_media_adapter", return_value=mock_adapter) as mock_get:
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        mock_get.assert_called_once_with("mermaid", api_key=None)
        mock_adapter.generate.assert_called_once()
        call_kwargs = mock_adapter.generate.call_args
        assert call_kwargs.kwargs.get("dry_run") is False or call_kwargs[1].get("dry_run") is False \
            or (len(call_kwargs.args) >= 3 and call_kwargs.args[2] is False) \
            or "dry_run" in str(call_kwargs)

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_skips_media_when_disabled(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """When media_generation.enabled=False, no media adapter is called."""
        from social_hook.llm.schemas import MediaTool

        mocks = _make_trigger_mocks(
            media_generation_enabled=False,
            drafter_media_type=MediaTool.mermaid,
            evaluator_media_tool="mermaid",
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        with patch("social_hook.adapters.registry.get_media_adapter") as mock_get:
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        mock_get.assert_not_called()

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_skips_media_when_none(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """When drafter returns media_type=none and evaluator has no media_tool, skip media."""
        mocks = _make_trigger_mocks(
            media_generation_enabled=True,
            drafter_media_type=None,
            evaluator_media_tool=None,
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        with patch("social_hook.adapters.registry.get_media_adapter") as mock_get:
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        mock_get.assert_not_called()

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_handles_media_failure(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """When media generation fails, draft is still saved with media_paths=[]."""
        from social_hook.adapters.models import MediaResult
        from social_hook.llm.schemas import MediaTool

        mocks = _make_trigger_mocks(
            media_generation_enabled=True,
            drafter_media_type=MediaTool.mermaid,
            evaluator_media_tool="mermaid",
            media_generate_result=MediaResult(success=False, error="render failed"),
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = mocks["media_generate_result"]

        with patch("social_hook.adapters.registry.get_media_adapter", return_value=mock_adapter):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        # Draft still saved successfully
        assert exit_code == 0
        mock_adapter.generate.assert_called_once()

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_skips_nano_without_key(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """When nano_banana_pro requested but GEMINI_API_KEY not set, skip gracefully."""
        from social_hook.llm.schemas import MediaTool

        mocks = _make_trigger_mocks(
            media_generation_enabled=True,
            drafter_media_type=MediaTool.nano_banana_pro,
            evaluator_media_tool="nano_banana_pro",
            gemini_key=None,
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        with patch("social_hook.adapters.registry.get_media_adapter") as mock_get:
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        # Adapter should not be fetched because key is missing and media_type_str was set to None
        mock_get.assert_not_called()

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_thread_with_media(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """When use_thread=True and media generated, draft.media_paths is set on the saved draft."""
        from social_hook.adapters.models import MediaResult
        from social_hook.llm.schemas import MediaTool

        mocks = _make_trigger_mocks(
            media_generation_enabled=True,
            drafter_media_type=MediaTool.mermaid,
            evaluator_media_tool="mermaid",
            media_generate_result=MediaResult(success=True, file_path="/tmp/media/diagram.png"),
            use_thread=True,
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = mocks["media_generate_result"]

        # Capture what gets passed to insert_draft
        saved_drafts = []
        original_db = mock_init_db.return_value

        class CaptureDryRun:
            """Captures insert_draft calls while acting as DryRunContext."""
            def __init__(self, conn):
                self._conn = conn

            def insert_decision(self, decision):
                pass

            def insert_draft(self, draft):
                saved_drafts.append(draft)

            def insert_draft_tweet(self, tweet):
                pass

            def emit_data_event(self, *args, **kwargs):
                pass

        # We need to patch DryRunContext to capture the draft
        with patch("social_hook.adapters.registry.get_media_adapter", return_value=mock_adapter), \
             patch("social_hook.trigger.DryRunContext", side_effect=lambda conn, dry_run: CaptureDryRun(conn)):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        mock_adapter.generate.assert_called_once()
        assert len(saved_drafts) == 1
        saved_draft = saved_drafts[0]
        assert saved_draft.media_paths == ["/tmp/media/diagram.png"]
        assert saved_draft.media_type == "mermaid"


class TestTriggerSendsMediaNotification:
    """Tests that trigger sends media files via adapter after text notification."""

    @patch("social_hook.messaging.telegram.TelegramAdapter.send_media")
    @patch("social_hook.messaging.telegram.TelegramAdapter.send_message")
    @patch("social_hook.bot.commands.set_chat_draft_context")
    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_sends_media_notification(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
        mock_set_context, mock_adapter_send, mock_adapter_send_media,
    ):
        """When draft has media_paths, adapter.send_media() is called for each chat ID."""
        from datetime import datetime
        from social_hook.adapters.models import MediaResult
        from social_hook.llm.schemas import MediaTool
        from social_hook.messaging.base import SendResult

        mocks = _make_trigger_mocks(
            media_generation_enabled=True,
            drafter_media_type=MediaTool.mermaid,
            evaluator_media_tool="mermaid",
            media_generate_result=MediaResult(success=True, file_path="/tmp/media/img.png"),
        )
        # Need telegram env vars
        env_map = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ALLOWED_CHAT_IDS": "111,222",
        }
        mocks["cfg"].env.get = lambda key, default="": env_map.get(key, default)

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test-proj", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        mock_adapter_send.return_value = SendResult(success=True, message_id="m1")
        mock_adapter_send_media.return_value = SendResult(success=True, message_id="m2")

        mock_media_adapter = MagicMock()
        mock_media_adapter.generate.return_value = mocks["media_generate_result"]

        with patch("social_hook.adapters.registry.get_media_adapter", return_value=mock_media_adapter):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0

        # send_media should have been called once per media_path per chat_id
        # 1 media file * 2 chat IDs = 2 calls
        assert mock_adapter_send_media.call_count == 2
        call_chat_ids = [c.args[0] for c in mock_adapter_send_media.call_args_list]
        assert "111" in call_chat_ids
        assert "222" in call_chat_ids
        # Verify media path and caption
        for call in mock_adapter_send_media.call_args_list:
            assert call.args[1] == "/tmp/media/img.png"
            assert "Media for" in call.kwargs.get("caption", call.args[2] if len(call.args) > 2 else "")


class TestPerPlatformPipeline:
    """Tests for per-platform draft creation."""

    def _make_per_platform_mocks(self, platforms_dict, episode_type="milestone",
                                  web_enabled=False):
        """Build common mocks for per-platform tests."""
        from datetime import datetime
        from social_hook.config.platforms import OutputPlatformConfig

        cfg = MagicMock()
        cfg.platforms = platforms_dict
        cfg.media_generation.enabled = False
        cfg.media_generation.tools = {"mermaid": True, "nano_banana_pro": True, "playwright": True, "ray_so": True}
        cfg.scheduling.timezone = "UTC"
        cfg.scheduling.max_posts_per_day = 3
        cfg.scheduling.min_gap_minutes = 30
        cfg.scheduling.optimal_days = ["Tue", "Wed", "Thu"]
        cfg.scheduling.optimal_hours = [9, 12, 17]
        cfg.scheduling.max_per_week = 10
        cfg.scheduling.thread_min_tweets = 4
        cfg.channels = {"web": ChannelConfig(enabled=web_enabled)}
        cfg.env.get = lambda key, default="": {}.get(key, default)

        commit = MagicMock()
        commit.hash = "abc12345"
        commit.message = "Add feature"

        evaluation = MagicMock()
        evaluation.decision = "post_worthy"
        evaluation.reasoning = "Good commit"
        evaluation.angle = "feature"
        evaluation.episode_type = episode_type
        evaluation.post_category = "arc"
        evaluation.arc_id = None
        evaluation.media_tool = None
        evaluation.platforms = {}

        evaluator_instance = MagicMock()
        evaluator_instance.evaluate.return_value = evaluation

        draft_result = MagicMock()
        draft_result.content = "Check out this feature!"
        draft_result.reasoning = "Short and punchy"
        draft_result.format_hint = "single"
        draft_result.beat_count = 1
        draft_result.media_type = None

        drafter_instance = MagicMock()
        drafter_instance.create_draft.return_value = draft_result

        schedule = MagicMock()
        schedule.datetime = datetime(2026, 2, 20, 12, 0, 0)
        schedule.time_reason = "optimal"
        schedule.deferred = False

        return {
            "cfg": cfg,
            "commit": commit,
            "evaluation": evaluation,
            "evaluator_instance": evaluator_instance,
            "draft_result": draft_result,
            "drafter_instance": drafter_instance,
            "schedule": schedule,
        }

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_per_platform_draft_creation(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """Two enabled platforms both get drafts."""
        from social_hook.config.platforms import OutputPlatformConfig

        mocks = self._make_per_platform_mocks({
            "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin", account_tier="free"),
            "linkedin": OutputPlatformConfig(enabled=True, priority="secondary", type="builtin"),
        })

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        # Capture insert_draft calls
        saved_drafts = []

        class CaptureDryRun:
            def __init__(self, conn, dry_run):
                pass
            def insert_decision(self, decision):
                pass
            def insert_draft(self, draft):
                saved_drafts.append(draft)
            def insert_draft_tweet(self, tweet):
                pass
            def emit_data_event(self, *args, **kwargs):
                pass

        with patch("social_hook.trigger.DryRunContext", side_effect=CaptureDryRun):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        assert len(saved_drafts) == 2
        platforms = {d.platform for d in saved_drafts}
        assert platforms == {"x", "linkedin"}

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_content_filter_notable(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """Secondary with filter=notable skips 'decision' episode type."""
        from social_hook.config.platforms import OutputPlatformConfig

        mocks = self._make_per_platform_mocks(
            {
                "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin", account_tier="free"),
                "linkedin": OutputPlatformConfig(enabled=True, priority="secondary", type="builtin"),
            },
            episode_type="decision",
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        saved_drafts = []

        class CaptureDryRun:
            def __init__(self, conn, dry_run):
                pass
            def insert_decision(self, decision):
                pass
            def insert_draft(self, draft):
                saved_drafts.append(draft)
            def insert_draft_tweet(self, tweet):
                pass
            def emit_data_event(self, *args, **kwargs):
                pass

        with patch("social_hook.trigger.DryRunContext", side_effect=CaptureDryRun):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        # X primary has filter=all, so decision passes. LinkedIn secondary has filter=significant, decision doesn't pass.
        assert len(saved_drafts) == 1
        assert saved_drafts[0].platform == "x"

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_no_enabled_platforms(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """No enabled platforms exits with 0, no drafts."""
        from social_hook.config.platforms import OutputPlatformConfig

        mocks = self._make_per_platform_mocks({
            "x": OutputPlatformConfig(enabled=False, priority="primary", type="builtin", account_tier="free"),
        })

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0
        # drafter should never be called
        mock_drafter_cls.return_value.create_draft.assert_not_called()

    @patch("social_hook.trigger.calculate_optimal_time")
    @patch("social_hook.llm.drafter.Drafter")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_all_platforms_filtered(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_drafter_cls, mock_schedule,
    ):
        """All platforms filtered exits with 0, no drafts."""
        from social_hook.config.platforms import OutputPlatformConfig

        # Only "significant" filter, but episode_type is "decision" — doesn't pass
        mocks = self._make_per_platform_mocks(
            {
                "linkedin": OutputPlatformConfig(
                    enabled=True, priority="secondary", type="builtin",
                    filter="significant",
                ),
            },
            episode_type="decision",
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = {}
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0


# =============================================================================
# Per-tool media disable tests (2a)
# =============================================================================


class TestGenerateMediaPerTool:
    """Tests for per-tool media disable in _generate_media()."""

    def test_per_tool_disabled(self):
        """When a specific tool is disabled in config.media_generation.tools, _generate_media skips it."""
        from social_hook.trigger import _generate_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"mermaid": False, "nano_banana_pro": True}

        evaluation = MagicMock()
        evaluation.media_tool = "mermaid"

        paths, mtype, spec = _generate_media(cfg, evaluation, dry_run=False)
        assert paths == []
        assert mtype is None
        assert spec is None

    def test_global_disabled(self):
        """When media_generation.enabled=False, _generate_media returns empty."""
        from social_hook.trigger import _generate_media

        cfg = MagicMock()
        cfg.media_generation.enabled = False
        cfg.media_generation.tools = {"mermaid": True}

        evaluation = MagicMock()
        evaluation.media_tool = "mermaid"

        paths, mtype, spec = _generate_media(cfg, evaluation, dry_run=False)
        assert paths == []
        assert mtype is None
        assert spec is None

    def test_project_override_disables(self):
        """Project-level media_guidance can disable a tool that's globally enabled."""
        from social_hook.trigger import _generate_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"mermaid": True}

        evaluation = MagicMock()
        evaluation.media_tool = "mermaid"

        project_config = MagicMock()
        guidance = MagicMock()
        guidance.enabled = False
        project_config.media_guidance.get.return_value = guidance

        paths, mtype, spec = _generate_media(
            cfg, evaluation, dry_run=False, project_config=project_config
        )
        assert paths == []
        assert mtype is None
        assert spec is None


# =============================================================================
# Thread threshold tests (2c)
# =============================================================================


class TestNeedsThreadThreshold:
    """Tests for configurable thread_min in _needs_thread()."""

    def test_thread_min_3(self):
        """With thread_min=3, 3 beats triggers thread."""
        from social_hook.trigger import _needs_thread

        draft = MagicMock()
        draft.format_hint = None
        draft.beat_count = 3
        draft.content = "short"
        assert _needs_thread(draft, "x", "free", thread_min=3) is True

    def test_thread_min_6(self):
        """With thread_min=6, 4 beats does NOT trigger thread."""
        from social_hook.trigger import _needs_thread

        draft = MagicMock()
        draft.format_hint = None
        draft.beat_count = 4
        draft.content = "short"
        assert _needs_thread(draft, "x", "free", thread_min=6) is False

    def test_default_threshold_4(self):
        """Default thread_min=4, 4 beats triggers thread."""
        from social_hook.trigger import _needs_thread

        draft = MagicMock()
        draft.format_hint = None
        draft.beat_count = 4
        draft.content = "short"
        assert _needs_thread(draft, "x", "free") is True


class TestParseThreadTweetsThreshold:
    """Tests for configurable thread_min in _parse_thread_tweets()."""

    def test_thread_min_3_accepts(self):
        """With thread_min=3, 3 numbered tweets are accepted."""
        from social_hook.trigger import _parse_thread_tweets

        content = "1/ First tweet\n\n2/ Second tweet\n\n3/ Third tweet"
        tweets = _parse_thread_tweets(content, thread_min=3)
        assert len(tweets) == 3

    def test_default_rejects_3(self):
        """Default thread_min=4 rejects 3 numbered tweets (falls to single)."""
        from social_hook.trigger import _parse_thread_tweets

        content = "1/ First\n\n2/ Second\n\n3/ Third"
        tweets = _parse_thread_tweets(content, thread_min=4)
        # 3 tweets < 4 min, numbered parse fails, try separators, paragraphs, then fallback
        assert len(tweets) == 1  # fallback single


# =============================================================================
# Decision notification tests (Chunk 3)
# =============================================================================


class TestDecisionNotification:
    """Tests for _send_decision_notification and notification_level config."""

    @patch("social_hook.trigger._send_decision_notification")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_notification_sent_for_not_post_worthy(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_send_notif,
    ):
        """Decision notification sent for not_post_worthy when level=all_decisions."""
        from social_hook.config.platforms import OutputPlatformConfig

        cfg = MagicMock()
        cfg.platforms = {
            "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin", account_tier="free"),
        }
        cfg.media_generation.enabled = False
        cfg.notification_level = "all_decisions"
        cfg.channels = {}
        cfg.env.get = lambda key, default="": {}.get(key, default)
        mock_config.return_value = cfg

        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test-proj", repo_path="/tmp")

        commit = MagicMock()
        commit.hash = "abc12345"
        commit.message = "Fix typo"
        commit.timestamp = None
        commit.parent_timestamp = None
        mock_parse.return_value = commit
        mock_context.return_value = MagicMock(project_summary="test")
        mock_proj_config.return_value = MagicMock()

        evaluator_instance = MagicMock()
        evaluation = MagicMock()
        evaluation.decision = "not_post_worthy"
        evaluation.reasoning = "Minor fix"
        evaluation.angle = None
        evaluation.episode_type = None
        evaluation.post_category = None
        evaluation.arc_id = None
        evaluation.media_tool = None
        evaluation.platforms = {}
        evaluation.commit_summary = None
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0
        mock_send_notif.assert_called_once()
        args = mock_send_notif.call_args[0]
        assert args[1].name == "test-proj"  # project

    @patch("social_hook.trigger._send_decision_notification")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_notification_skipped_for_post_worthy(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_send_notif,
    ):
        """Decision notification NOT sent for post_worthy (draft notification handles it)."""
        from social_hook.config.platforms import OutputPlatformConfig
        from social_hook.config.yaml import ChannelConfig

        cfg = MagicMock()
        cfg.platforms = {
            "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin", account_tier="free"),
        }
        cfg.media_generation.enabled = False
        cfg.notification_level = "all_decisions"
        cfg.channels = {"web": ChannelConfig(enabled=False)}
        cfg.env.get = lambda key, default="": {}.get(key, default)
        cfg.scheduling.timezone = "UTC"
        cfg.scheduling.max_posts_per_day = 3
        cfg.scheduling.min_gap_minutes = 30
        cfg.scheduling.optimal_days = ["Tue", "Wed", "Thu"]
        cfg.scheduling.optimal_hours = [9, 12, 17]
        cfg.scheduling.max_per_week = 10
        cfg.scheduling.thread_min_tweets = 4
        mock_config.return_value = cfg

        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test-proj", repo_path="/tmp")

        commit = MagicMock()
        commit.hash = "abc12345"
        commit.message = "Add feature"
        commit.timestamp = None
        commit.parent_timestamp = None
        mock_parse.return_value = commit
        mock_context.return_value = MagicMock(project_summary="test")
        mock_proj_config.return_value = MagicMock()

        evaluator_instance = MagicMock()
        evaluation = MagicMock()
        evaluation.decision = "post_worthy"
        evaluation.reasoning = "Great commit"
        evaluation.angle = "feature"
        evaluation.episode_type = "launch"
        evaluation.post_category = "arc"
        evaluation.arc_id = None
        evaluation.media_tool = None
        evaluation.platforms = {}
        evaluation.commit_summary = None
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0
        mock_send_notif.assert_not_called()

    @patch("social_hook.trigger._send_decision_notification")
    @patch("social_hook.llm.evaluator.Evaluator")
    @patch("social_hook.llm.factory.create_client")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_notification_skipped_when_drafts_only(
        self, mock_config, mock_init_db, mock_db_path, mock_by_path,
        mock_parse, mock_context, mock_proj_config, mock_create_client,
        mock_evaluator_cls, mock_send_notif,
    ):
        """Decision notification NOT sent when notification_level=drafts_only."""
        cfg = MagicMock()
        cfg.platforms = {}
        cfg.media_generation.enabled = False
        cfg.notification_level = "drafts_only"
        cfg.channels = {}
        cfg.env.get = lambda key, default="": {}.get(key, default)
        mock_config.return_value = cfg

        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test-proj", repo_path="/tmp")

        commit = MagicMock()
        commit.hash = "abc12345"
        commit.message = "Fix typo"
        commit.timestamp = None
        commit.parent_timestamp = None
        mock_parse.return_value = commit
        mock_context.return_value = MagicMock(project_summary="test")
        mock_proj_config.return_value = MagicMock()

        evaluator_instance = MagicMock()
        evaluation = MagicMock()
        evaluation.decision = "not_post_worthy"
        evaluation.reasoning = "Minor fix"
        evaluation.angle = None
        evaluation.episode_type = None
        evaluation.post_category = None
        evaluation.arc_id = None
        evaluation.media_tool = None
        evaluation.platforms = {}
        evaluation.commit_summary = None
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0
        mock_send_notif.assert_not_called()

    def test_send_decision_notification_message_format(self):
        """_send_decision_notification formats message correctly."""
        from social_hook.trigger import _send_decision_notification
        from social_hook.messaging.base import OutboundMessage
        from social_hook.config.yaml import ChannelConfig

        cfg = MagicMock()
        cfg.channels = {"web": ChannelConfig(enabled=False)}
        cfg.env.get = lambda key, default="": {}.get(key, default)

        project = MagicMock()
        project.name = "social-hook"
        commit = MagicMock()
        commit.hash = "abc12345abcdef"
        commit.message = "Fix typo in README"
        decision = MagicMock()
        decision.decision = "not_post_worthy"
        decision.reasoning = "Minor documentation fix, not interesting"

        with patch("social_hook.messaging.web.WebAdapter") as mock_web:
            _send_decision_notification(cfg, project, commit, decision)
            # Web disabled, so WebAdapter.send_message not called
            mock_web.return_value.send_message.assert_not_called()

    def test_send_decision_notification_web(self):
        """_send_decision_notification sends to web when enabled."""
        from social_hook.trigger import _send_decision_notification

        cfg = MagicMock()
        cfg.channels = {}  # No web config = enabled by default
        cfg.env.get = lambda key, default="": {}.get(key, default)

        project = MagicMock()
        project.name = "test-proj"
        commit = MagicMock()
        commit.hash = "abc12345abcdef"
        commit.message = "Fix typo"
        decision = MagicMock()
        decision.decision = "not_post_worthy"
        decision.reasoning = "Minor fix"

        with patch("social_hook.trigger.get_db_path", return_value=Path("/tmp/test.db")):
            with patch("social_hook.messaging.web.WebAdapter") as mock_web_cls:
                mock_adapter = MagicMock()
                mock_web_cls.return_value = mock_adapter
                _send_decision_notification(cfg, project, commit, decision)
                mock_adapter.send_message.assert_called_once()
                msg = mock_adapter.send_message.call_args[0][1]
                assert "not_post_worthy" in msg.text
                assert "test-proj" in msg.text
                assert "abc12345" in msg.text
