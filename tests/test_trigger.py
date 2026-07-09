"""Tests for trigger pipeline (T29)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.config.yaml import ChannelConfig
from social_hook.models.core import Decision, Project
from social_hook.rate_limits import GateResult
from social_hook.trigger import (
    _build_merge_commit,
    _execute_merge_groups,
    git_remote_origin,
    parse_commit_info,
    run_trigger,
)


@pytest.fixture(autouse=True)
def _allow_rate_limit():
    """Default: rate limit gate allows all evaluations.

    Tests that need to verify gate behavior should explicitly patch
    social_hook.trigger.check_rate_limit themselves (which overrides this).
    """
    with patch(
        "social_hook.trigger.check_rate_limit",
        return_value=GateResult(blocked=False, reason=""),
    ):
        yield


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
            capture_output=True,
            text=True,
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
            capture_output=True,
            text=True,
        )
        commit_hash = result.stdout.strip()

        commit = parse_commit_info(commit_hash, str(repo))
        assert commit.timestamp is not None
        # ISO 8601 with timezone offset
        assert "T" in commit.timestamp
        assert "+" in commit.timestamp or "Z" in commit.timestamp or "-" in commit.timestamp[11:]

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
            capture_output=True,
            text=True,
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
            capture_output=True,
            text=True,
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
            ["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:user/repo.git"],
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
    def test_paused_project_returns_0(self, mock_config, mock_db, mock_db_path, mock_by_path):
        """Paused project exits with 0."""
        mock_config.return_value = MagicMock()
        mock_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1",
            name="test",
            repo_path="/tmp",
            paused=True,
        )

        exit_code = run_trigger("abc123", "/tmp")
        assert exit_code == 0


class TestTriggerBranchFilter:
    """Tests for trigger branch filter."""

    @patch("social_hook.trigger._get_current_branch")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_branch_filter_skips_non_matching(
        self, mock_config, mock_db, mock_db_path, mock_by_path, mock_branch
    ):
        """Non-matching branch skips pipeline."""
        mock_config.return_value = MagicMock()
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1",
            name="test",
            repo_path="/tmp",
            trigger_branch="main",
        )
        mock_branch.return_value = "feature/x"

        exit_code = run_trigger("abc123", "/tmp")
        assert exit_code == 0
        mock_conn.close.assert_called()

    @patch("social_hook.trigger._get_current_branch")
    @patch("social_hook.trigger.load_project_config", create=True)
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_branch_filter_allows_matching(
        self,
        mock_config,
        mock_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_branch,
    ):
        """Matching branch proceeds past filter (will fail later but that's fine)."""
        mock_config.return_value = MagicMock()
        mock_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1",
            name="test",
            repo_path="/tmp",
            trigger_branch="main",
        )
        mock_branch.return_value = "main"
        mock_parse.return_value = MagicMock(
            hash="abc123", message="test", timestamp=None, parent_timestamp=None
        )
        mock_context.return_value = MagicMock(project_summary="test")

        # Proceeds past branch check; fails at evaluator (exit 3) — not 0
        exit_code = run_trigger("abc123", "/tmp")
        assert exit_code != 0  # Didn't skip due to branch filter

    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_branch_filter_null_allows_all(
        self,
        mock_config,
        mock_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
    ):
        """No trigger_branch set proceeds past filter (will fail later)."""
        mock_config.return_value = MagicMock()
        mock_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1",
            name="test",
            repo_path="/tmp",
            trigger_branch=None,
        )
        mock_parse.return_value = MagicMock(
            hash="abc123", message="test", timestamp=None, parent_timestamp=None
        )
        mock_context.return_value = MagicMock(project_summary="test")

        # Proceeds past branch check (no filter); fails at evaluator — not 0
        exit_code = run_trigger("abc123", "/tmp")
        assert exit_code != 0  # Didn't skip due to branch filter

    @patch("social_hook.trigger._get_current_branch")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_trigger_branch_filter_detached_head(
        self, mock_config, mock_db, mock_db_path, mock_by_path, mock_branch
    ):
        """Detached HEAD skips when branch filter is set."""
        mock_config.return_value = MagicMock()
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(
            id="p1",
            name="test",
            repo_path="/tmp",
            trigger_branch="main",
        )
        mock_branch.return_value = None  # Detached HEAD

        exit_code = run_trigger("abc123", "/tmp")
        assert exit_code == 0
        mock_conn.close.assert_called()


class TestTriggerUsesAdapter:
    """Tests that trigger notification uses TelegramAdapter."""

    @pytest.fixture(autouse=True)
    def _no_real_notifications(self):
        """Override: this class tests notification paths with mocked adapters."""
        yield

    @patch("social_hook.messaging.telegram.TelegramAdapter.send_message")
    @patch("social_hook.bot.commands.set_chat_draft_context")
    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
        mock_set_context,
        mock_adapter_send,
    ):
        """run_trigger uses TelegramAdapter.send_message instead of direct HTTP."""
        from datetime import datetime

        # Config with Telegram env vars and dict-based platforms
        from social_hook.config.platforms import OutputPlatformConfig
        from social_hook.messaging.base import SendResult

        cfg = MagicMock()
        cfg.platforms = {
            "x": OutputPlatformConfig(
                enabled=True, priority="primary", type="builtin", account_tier="free"
            ),
        }
        cfg.media_generation.enabled = False
        cfg.media_generation.tools = {
            "mermaid": True,
            "nano_banana_pro": True,
            "playwright": True,
            "ray_so": True,
        }
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
            id="p1",
            name="test-proj",
            repo_path="/tmp",
        )

        # Commit
        commit = MagicMock()
        commit.hash = "abc12345"
        commit.message = "Add feature"
        mock_parse.return_value = commit

        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()

        # Evaluator says draft-worthy
        evaluator_instance = MagicMock()
        evaluation = _make_eval_mock(
            action="draft",
            reason="Good commit",
            angle="new feature",
            episode_type="launch",
            post_category="arc",
        )
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        # Drafter
        drafter_instance = MagicMock()
        draft_result = MagicMock()
        draft_result.content = "Check out this feature!"
        draft_result.reasoning = "Short and punchy"
        draft_result.vehicle = "single"
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


def _make_eval_mock(
    action="draft",
    reason="Good commit",
    angle="feature",
    episode_type="milestone",
    post_category="arc",
    arc_id=None,
    new_arc_theme=None,
    media_tool=None,
    consolidate_with=None,
    queue_actions=None,
):
    """Build a LogEvaluationInput-shaped mock for trigger tests."""
    from social_hook.llm.schemas import (
        LogEvaluationInput,
    )

    target_data = {
        "action": action,
        "reason": reason,
        "angle": angle,
        "episode_type": episode_type,
        "post_category": post_category,
        "arc_id": arc_id,
        "new_arc_theme": new_arc_theme,
        "media_tool": media_tool,
        "consolidate_with": consolidate_with,
    }
    # Remove None values so Pydantic uses defaults
    target_data = {k: v for k, v in target_data.items() if v is not None}

    return LogEvaluationInput.model_validate(
        {
            "commit_analysis": {"summary": "Test commit summary"},
            "targets": {"default": target_data},
            "queue_actions": queue_actions,
        }
    )


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
        "x": OutputPlatformConfig(
            enabled=True, priority="primary", type="builtin", account_tier="free"
        ),
    }
    cfg.media_generation.enabled = media_generation_enabled
    cfg.media_generation.tools = {
        "mermaid": True,
        "nano_banana_pro": True,
        "playwright": True,
        "ray_so": True,
    }
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

    evaluation = _make_eval_mock(
        action="draft",
        reason="Good commit",
        angle="feature",
        episode_type="milestone",
        post_category="arc",
        media_tool=evaluator_media_tool,
    )

    evaluator_instance = MagicMock()
    evaluator_instance.evaluate.return_value = evaluation

    draft_result = MagicMock()
    draft_result.content = "Check out this feature!"
    draft_result.reasoning = "Short and punchy"
    draft_result.vehicle = "thread" if use_thread else "single"
    draft_result.beat_count = 5 if use_thread else 1
    # Multi-media per-draft: the drafter now emits a list of MediaSpecItem
    # (one per media item). When drafter_media_type is set, translate it
    # into a single-item list so the downstream _generate_all_media path
    # exercises. When None, the list is empty — no media generation runs.
    if drafter_media_type is not None:
        tool_val = getattr(drafter_media_type, "value", drafter_media_type)
        # Each adapter expects tool-specific spec fields; provide the right
        # one (fallback to a generic prompt for any other tool).
        if tool_val == "mermaid":
            spec_body = {"diagram": "graph LR\n  A-->B"}
        elif tool_val == "ray_so":
            spec_body = {"code": "print('hi')"}
        elif tool_val == "playwright":
            spec_body = {"url": "https://example.com"}
        else:
            spec_body = {"prompt": "a diagram"}
        draft_result.media_specs = [
            {"id": "media_testmock0001", "tool": tool_val, "spec": spec_body}
        ]
    else:
        draft_result.media_specs = []

    drafter_instance = MagicMock()
    drafter_instance.create_draft.return_value = draft_result
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

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
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
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = mocks["media_generate_result"]

        with patch(
            "social_hook.adapters.registry.get_media_adapter", return_value=mock_adapter
        ) as mock_get:
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        mock_get.assert_called_once_with("mermaid", api_key=None)
        mock_adapter.generate.assert_called_once()
        call_kwargs = mock_adapter.generate.call_args
        assert (
            call_kwargs.kwargs.get("dry_run") is False
            or call_kwargs[1].get("dry_run") is False
            or (len(call_kwargs.args) >= 3 and call_kwargs.args[2] is False)
            or "dry_run" in str(call_kwargs)
        )

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
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
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        with patch("social_hook.adapters.registry.get_media_adapter") as mock_get:
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        mock_get.assert_not_called()

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
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
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        with patch("social_hook.adapters.registry.get_media_adapter") as mock_get:
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        mock_get.assert_not_called()

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
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
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
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

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
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
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        with patch("social_hook.adapters.registry.get_media_adapter") as mock_get:
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        # Adapter should not be fetched because key is missing and media_type_str was set to None
        mock_get.assert_not_called()

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
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
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = mocks["media_generate_result"]

        # Capture what gets passed to insert_draft
        saved_drafts = []

        class CaptureDryRun:
            """Captures insert_draft calls while acting as DryRunContext."""

            def __init__(self, conn, dry_run=False):
                self.conn = conn

            def insert_decision(self, decision):
                pass

            def insert_draft(self, draft):
                saved_drafts.append(draft)

            def insert_draft_part(self, part):
                pass

            def emit_data_event(self, *args, **kwargs):
                pass

            def update_decision(self, *args, **kwargs):
                pass

        # We need to patch DryRunContext to capture the draft
        with (
            patch("social_hook.adapters.registry.get_media_adapter", return_value=mock_adapter),
            patch(
                "social_hook.trigger.DryRunContext",
                side_effect=lambda conn, dry_run: CaptureDryRun(conn, dry_run),
            ),
        ):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        mock_adapter.generate.assert_called_once()
        assert len(saved_drafts) == 1
        saved_draft = saved_drafts[0]
        assert saved_draft.media_paths == ["/tmp/media/diagram.png"]
        # Multi-media per-draft: tool lives inside the spec item, not a
        # separate column.
        assert len(saved_draft.media_specs) == 1
        assert saved_draft.media_specs[0]["tool"] == "mermaid"


class TestTriggerSendsMediaNotification:
    """Tests that trigger sends media files via adapter after text notification."""

    @pytest.fixture(autouse=True)
    def _no_real_notifications(self):
        """Override: this class tests notification paths with mocked adapters."""
        yield

    @patch("social_hook.messaging.telegram.TelegramAdapter.send_media")
    @patch("social_hook.messaging.telegram.TelegramAdapter.send_message")
    @patch("social_hook.bot.commands.set_chat_draft_context")
    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
        mock_set_context,
        mock_adapter_send,
        mock_adapter_send_media,
    ):
        """When draft has media_paths, adapter.send_media() is called for each chat ID."""
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
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        mock_adapter_send.return_value = SendResult(success=True, message_id="m1")
        mock_adapter_send_media.return_value = SendResult(success=True, message_id="m2")

        mock_media_adapter = MagicMock()
        mock_media_adapter.generate.return_value = mocks["media_generate_result"]

        with patch(
            "social_hook.adapters.registry.get_media_adapter", return_value=mock_media_adapter
        ):
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
            assert "Media" in call.kwargs.get("caption", call.args[2] if len(call.args) > 2 else "")


class TestPerPlatformPipeline:
    """Tests for per-platform draft creation."""

    def _make_per_platform_mocks(self, platforms_dict, episode_type="milestone", web_enabled=False):
        """Build common mocks for per-platform tests."""
        from datetime import datetime

        cfg = MagicMock()
        cfg.platforms = platforms_dict
        cfg.media_generation.enabled = False
        cfg.media_generation.tools = {
            "mermaid": True,
            "nano_banana_pro": True,
            "playwright": True,
            "ray_so": True,
        }
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

        evaluation = _make_eval_mock(
            action="draft",
            reason="Good commit",
            angle="feature",
            episode_type=episode_type,
            post_category="arc",
        )

        evaluator_instance = MagicMock()
        evaluator_instance.evaluate.return_value = evaluation

        draft_result = MagicMock()
        draft_result.content = "Check out this feature!"
        draft_result.reasoning = "Short and punchy"
        draft_result.vehicle = "single"
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

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
    ):
        """Two enabled platforms both get drafts."""
        from social_hook.config.platforms import OutputPlatformConfig

        mocks = self._make_per_platform_mocks(
            {
                "x": OutputPlatformConfig(
                    enabled=True, priority="primary", type="builtin", account_tier="free"
                ),
                "linkedin": OutputPlatformConfig(
                    enabled=True, priority="secondary", type="builtin"
                ),
            }
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        # Capture insert_draft calls
        saved_drafts = []

        class CaptureDryRun:
            def __init__(self, conn, dry_run=False):
                self.conn = conn

            def insert_decision(self, decision):
                pass

            def insert_draft(self, draft):
                saved_drafts.append(draft)

            def insert_draft_part(self, part):
                pass

            def emit_data_event(self, *args, **kwargs):
                pass

            def update_decision(self, *args, **kwargs):
                pass

        with patch("social_hook.trigger.DryRunContext", side_effect=CaptureDryRun):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        assert len(saved_drafts) == 2
        platforms = {d.platform for d in saved_drafts}
        assert platforms == {"x", "linkedin"}

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
    ):
        """Secondary with filter=notable skips 'decision' episode type."""
        from social_hook.config.platforms import OutputPlatformConfig

        mocks = self._make_per_platform_mocks(
            {
                "x": OutputPlatformConfig(
                    enabled=True, priority="primary", type="builtin", account_tier="free"
                ),
                "linkedin": OutputPlatformConfig(
                    enabled=True, priority="secondary", type="builtin"
                ),
            },
            episode_type="decision",
        )

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        saved_drafts = []

        class CaptureDryRun:
            def __init__(self, conn, dry_run=False):
                self.conn = conn

            def insert_decision(self, decision):
                pass

            def insert_draft(self, draft):
                saved_drafts.append(draft)

            def insert_draft_part(self, part):
                pass

            def emit_data_event(self, *args, **kwargs):
                pass

            def update_decision(self, *args, **kwargs):
                pass

        with patch("social_hook.trigger.DryRunContext", side_effect=CaptureDryRun):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)

        assert exit_code == 0
        # Content filtering removed — all enabled platforms receive drafts
        assert len(saved_drafts) == 2
        platforms = {d.platform for d in saved_drafts}
        assert platforms == {"x", "linkedin"}

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
    ):
        """No enabled platforms falls back to preview platform and drafts."""
        from social_hook.config.platforms import OutputPlatformConfig

        mocks = self._make_per_platform_mocks(
            {
                "x": OutputPlatformConfig(
                    enabled=False, priority="primary", type="builtin", account_tier="free"
                ),
            }
        )

        saved_drafts = []

        class CaptureDryRun:
            def __init__(self, conn, dry_run=False):
                self.conn = conn

            def insert_decision(self, decision):
                return decision

            def update_decision(self, *args, **kwargs):
                return None

            def insert_draft(self, draft):
                saved_drafts.append(draft)
                return draft

            def insert_draft_part(self, part):
                pass

            def emit_data_event(self, *args, **kwargs):
                pass

        mock_config.return_value = mocks["cfg"]
        mock_init_db.return_value = MagicMock()
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_parse.return_value = mocks["commit"]
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        with patch("social_hook.trigger.DryRunContext", side_effect=CaptureDryRun):
            exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0
        # No enabled platforms and no targets config = no drafts created
        assert len(saved_drafts) == 0

    @patch("social_hook.drafting.calculate_optimal_time")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_drafter_cls,
        mock_schedule,
    ):
        """All platforms filtered exits with 0, no drafts."""
        from social_hook.config.platforms import OutputPlatformConfig

        # Only "significant" filter, but episode_type is "decision" — doesn't pass
        mocks = self._make_per_platform_mocks(
            {
                "linkedin": OutputPlatformConfig(
                    enabled=True,
                    priority="secondary",
                    type="builtin",
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
        mock_context.return_value = MagicMock(
            held_decisions=[], platform_introduced={"x": True}, project_summary="test"
        )
        mock_proj_config.return_value = MagicMock()
        mock_evaluator_cls.return_value = mocks["evaluator_instance"]
        mock_drafter_cls.return_value = mocks["drafter_instance"]
        mock_schedule.return_value = mocks["schedule"]

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0


# =============================================================================
# Per-tool media disable tests (2a)
# =============================================================================


class TestRateLimitGate:
    """Tests for rate limit gate integration in run_trigger."""

    @patch("social_hook.trigger.check_rate_limit")
    @patch("social_hook.trigger._get_current_branch")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_commit_trigger_gated_when_limit_hit(
        self, mock_config, mock_db, mock_db_path, mock_by_path, mock_branch, mock_gate
    ):
        """Auto commit trigger is gated when rate limit is hit."""
        from social_hook.rate_limits import GateResult

        mock_config.return_value = MagicMock()
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_branch.return_value = "main"
        mock_gate.return_value = GateResult(blocked=True, reason="Daily limit reached: 15/15")

        exit_code = run_trigger("abc123", "/tmp", trigger_source="commit")
        assert exit_code == 0
        mock_conn.close.assert_called()

    @patch("social_hook.trigger.check_rate_limit")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger._get_current_branch")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_manual_trigger_bypasses_gate(
        self,
        mock_config,
        mock_db,
        mock_db_path,
        mock_by_path,
        mock_branch,
        mock_parse,
        mock_proj_config,
        mock_context,
        mock_gate,
    ):
        """Manual trigger bypasses rate limit gate entirely."""
        mock_config.return_value = MagicMock()
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_branch.return_value = "main"
        mock_parse.return_value = MagicMock(
            hash="abc123", message="test", timestamp=None, parent_timestamp=None
        )
        mock_context.return_value = MagicMock(project_summary="test")

        # Proceeds past gate (not called), fails later at evaluator — that's fine
        run_trigger("abc123", "/tmp", trigger_source="manual")
        mock_gate.assert_not_called()

    @patch("social_hook.trigger.check_rate_limit")
    @patch("social_hook.trigger.assemble_evaluator_context")
    @patch("social_hook.config.project.load_project_config")
    @patch("social_hook.trigger.parse_commit_info")
    @patch("social_hook.trigger._get_current_branch")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_drain_trigger_bypasses_gate(
        self,
        mock_config,
        mock_db,
        mock_db_path,
        mock_by_path,
        mock_branch,
        mock_parse,
        mock_proj_config,
        mock_context,
        mock_gate,
    ):
        """Drain trigger bypasses rate limit gate entirely."""
        mock_config.return_value = MagicMock()
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_branch.return_value = "main"
        mock_parse.return_value = MagicMock(
            hash="abc123", message="test", timestamp=None, parent_timestamp=None
        )
        mock_context.return_value = MagicMock(project_summary="test")

        run_trigger("abc123", "/tmp", trigger_source="drain")
        mock_gate.assert_not_called()

    @patch("social_hook.trigger.check_rate_limit")
    @patch("social_hook.trigger._get_current_branch")
    @patch("social_hook.trigger.ops.get_project_by_path")
    @patch("social_hook.trigger.get_db_path")
    @patch("social_hook.trigger.init_database")
    @patch("social_hook.trigger.load_full_config")
    def test_deferred_decision_created_with_correct_fields(
        self, mock_config, mock_db, mock_db_path, mock_by_path, mock_branch, mock_gate
    ):
        """Deferred decision has correct type, reason, trigger_source, and no commit_message."""
        from social_hook.rate_limits import GateResult

        mock_config.return_value = MagicMock()
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_db_path.return_value = Path("/tmp/test.db")
        mock_by_path.return_value = Project(id="p1", name="test", repo_path="/tmp")
        mock_branch.return_value = "main"
        mock_gate.return_value = GateResult(blocked=True, reason="Gap not elapsed: 7m remaining")

        # Capture the decision inserted via DryRunContext
        inserted_decisions = []

        class CaptureDryRun:
            def __init__(self, conn, dry_run=False):
                self.conn = conn

            def insert_decision(self, decision):
                inserted_decisions.append(decision)

            def emit_data_event(self, *args, **kwargs):
                pass

        with patch("social_hook.trigger.DryRunContext", side_effect=CaptureDryRun):
            exit_code = run_trigger("abc123", "/tmp", trigger_source="commit")

        assert exit_code == 0
        assert len(inserted_decisions) == 1
        d = inserted_decisions[0]
        assert d.decision == "deferred_eval"
        assert d.reasoning == "Gap not elapsed: 7m remaining"
        assert d.commit_message is None
        assert d.trigger_source == "commit"
        assert d.branch == "main"
        assert d.project_id == "p1"


class TestGenerateMediaPerTool:
    """Per-tool gating for multi-media generation.

    Multi-media per-draft: the old ``trigger._generate_media`` helper was
    replaced by ``drafting._generate_one_media`` as part of the parallel-
    array rewrite (see drafting.py). The gating semantics below are
    unchanged; only the symbol name and return shape differ — generation
    failures now propagate as exceptions rather than ``(empty, None, None,
    err)`` tuples.
    """

    def test_per_tool_disabled(self):
        """A tool disabled in config.media_generation.tools raises RuntimeError."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"mermaid": False, "nano_banana_pro": True}

        with pytest.raises(RuntimeError, match="disabled"):
            _generate_one_media(
                cfg,
                {"id": "media_test00000001", "tool": "mermaid", "spec": {"diagram": "A-->B"}},
                "mermaid",
                dry_run=False,
                verbose=False,
                project_config=None,
            )

    def test_global_disabled(self):
        """media_generation.enabled=False short-circuits before the adapter lookup."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = False
        cfg.media_generation.tools = {"mermaid": True}

        with pytest.raises(RuntimeError, match="disabled globally"):
            _generate_one_media(
                cfg,
                {"id": "media_test00000001", "tool": "ray_so", "spec": {"code": "x=1"}},
                "ray_so",
                dry_run=False,
                verbose=False,
                project_config=None,
            )

    def test_project_override_disables(self):
        """Project-level media_guidance disables a globally-enabled tool."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"mermaid": True}

        project_config = MagicMock()
        guidance = MagicMock()
        guidance.enabled = False
        project_config.media_guidance.get.return_value = guidance

        with pytest.raises(RuntimeError, match="disabled"):
            _generate_one_media(
                cfg,
                {"id": "media_test00000001", "tool": "mermaid", "spec": {"diagram": "A-->B"}},
                "mermaid",
                dry_run=False,
                verbose=False,
                project_config=project_config,
            )

    @patch("social_hook.adapters.registry.get_media_adapter")
    def test_rayso_valid_spec_calls_adapter(self, mock_get_adapter):
        """Valid ray_so spec passes through to the adapter and returns a media path."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"ray_so": True}

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = MagicMock(
            success=True, file_path="/tmp/media/code.png"
        )
        mock_get_adapter.return_value = mock_adapter

        spec_body = {"code": "print('hello')", "language": "python", "title": "example.py"}
        path = _generate_one_media(
            cfg,
            {"id": "media_test00000001", "tool": "ray_so", "spec": spec_body},
            "ray_so",
            dry_run=False,
            verbose=False,
            project_config=None,
        )

        assert path == "/tmp/media/code.png"
        mock_adapter.generate.assert_called_once()
        call_kwargs = mock_adapter.generate.call_args
        assert call_kwargs[1]["spec"] == spec_body

    @patch("social_hook.adapters.registry.get_media_adapter")
    def test_mermaid_valid_spec_calls_adapter(self, mock_get_adapter):
        """Valid mermaid spec passes through to the adapter."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"mermaid": True}

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = MagicMock(
            success=True, file_path="/tmp/media/diagram.png"
        )
        mock_get_adapter.return_value = mock_adapter

        spec_body = {"diagram": "graph LR\n  A-->B"}
        path = _generate_one_media(
            cfg,
            {"id": "media_test00000002", "tool": "mermaid", "spec": spec_body},
            "mermaid",
            dry_run=False,
            verbose=False,
            project_config=None,
        )

        assert path == "/tmp/media/diagram.png"
        mock_adapter.generate.assert_called_once()
        call_kwargs = mock_adapter.generate.call_args
        assert call_kwargs[1]["spec"] == spec_body

    @patch("social_hook.adapters.registry.get_media_adapter")
    def test_nanabananapro_valid_spec_calls_adapter(self, mock_get_adapter):
        """nano_banana_pro pulls the API key from config.env."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"nano_banana_pro": True}
        cfg.env.get.return_value = "fake-gemini-key"

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = MagicMock(
            success=True, file_path="/tmp/media/visual.png"
        )
        mock_get_adapter.return_value = mock_adapter

        spec_body = {"prompt": "abstract code visualization"}
        path = _generate_one_media(
            cfg,
            {"id": "media_test00000003", "tool": "nano_banana_pro", "spec": spec_body},
            "nano_banana_pro",
            dry_run=False,
            verbose=False,
            project_config=None,
        )

        assert path == "/tmp/media/visual.png"
        mock_adapter.generate.assert_called_once()
        mock_get_adapter.assert_called_once_with("nano_banana_pro", api_key="fake-gemini-key")

    @patch("social_hook.adapters.registry.get_media_adapter")
    def test_playwright_valid_spec_calls_adapter(self, mock_get_adapter):
        """Valid playwright spec passes through to the adapter."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"playwright": True}

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = MagicMock(
            success=True, file_path="/tmp/media/screenshot.png"
        )
        mock_get_adapter.return_value = mock_adapter

        spec_body = {"url": "https://example.com", "selector": "#main"}
        path = _generate_one_media(
            cfg,
            {"id": "media_test00000004", "tool": "playwright", "spec": spec_body},
            "playwright",
            dry_run=False,
            verbose=False,
            project_config=None,
        )

        assert path == "/tmp/media/screenshot.png"
        mock_adapter.generate.assert_called_once()
        call_kwargs = mock_adapter.generate.call_args
        assert call_kwargs[1]["spec"] == spec_body

    def test_empty_spec_returns_empty(self):
        """Empty adapter-spec body raises (adapters return failure; surfaces as RuntimeError)."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"ray_so": True}

        with patch("social_hook.adapters.registry.get_media_adapter") as mock_get_adapter:
            mock_adapter = MagicMock()
            mock_adapter.generate.return_value = MagicMock(
                success=False, file_path=None, error="empty spec"
            )
            mock_get_adapter.return_value = mock_adapter

            with pytest.raises(RuntimeError):
                _generate_one_media(
                    cfg,
                    {"id": "media_test00000005", "tool": "ray_so", "spec": {}},
                    "ray_so",
                    dry_run=False,
                    verbose=False,
                    project_config=None,
                )

    def test_none_tool_rejected(self):
        """tool=None / tool='none' raises — no silent skip path any more."""
        from social_hook.drafting import _generate_one_media

        cfg = MagicMock()
        cfg.media_generation.enabled = True
        cfg.media_generation.tools = {"ray_so": True}

        with pytest.raises(RuntimeError, match="Invalid tool"):
            _generate_one_media(
                cfg,
                {"id": "media_test00000006", "tool": "none", "spec": {}},
                "none",
                dry_run=False,
                verbose=False,
                project_config=None,
            )


# =============================================================================
# Thread threshold tests (2c)
# =============================================================================


class TestVehicleValidationThreshold:
    """Tests for configurable thread_min in validate_draft_for_vehicle()."""

    def test_thread_min_3_accepts_3_parts(self):
        """With thread_min=3, content with 3 parts is valid as thread."""
        from social_hook.vehicle import validate_draft_for_vehicle

        content = "1/ First\n\n2/ Second\n\n3/ Third"
        result = validate_draft_for_vehicle(content, "thread", "x", 280, thread_min=3)
        assert result.valid is True

    def test_thread_min_6_rejects_4_parts(self):
        """With thread_min=6, content with 4 parts is invalid as thread."""
        from social_hook.vehicle import validate_draft_for_vehicle

        content = "1/ One\n\n2/ Two\n\n3/ Three\n\n4/ Four"
        result = validate_draft_for_vehicle(content, "thread", "x", 280, thread_min=6)
        assert result.valid is False
        assert result.suggested_vehicle == "single"

    def test_default_threshold_4_accepts_4_parts(self):
        """Default thread_min=4 accepts content with 4 parts."""
        from social_hook.vehicle import validate_draft_for_vehicle

        content = "1/ One\n\n2/ Two\n\n3/ Three\n\n4/ Four"
        result = validate_draft_for_vehicle(content, "thread", "x", 280)
        assert result.valid is True


class TestParseThreadPartsThreshold:
    """Tests for configurable thread_min in parse_thread_parts()."""

    def test_thread_min_3_accepts(self):
        """With thread_min=3, 3 numbered parts are accepted."""
        from social_hook.vehicle import parse_thread_parts

        content = "1/ First tweet\n\n2/ Second tweet\n\n3/ Third tweet"
        parts = parse_thread_parts(content, "x", thread_min=3)
        assert len(parts) == 3

    def test_default_rejects_3(self):
        """Default thread_min=4 rejects 3 numbered parts (falls to single)."""
        from social_hook.vehicle import parse_thread_parts

        content = "1/ First\n\n2/ Second\n\n3/ Third"
        parts = parse_thread_parts(content, "x", thread_min=4)
        # 3 parts < 4 min, numbered parse fails, try separators, paragraphs, then fallback
        assert len(parts) == 1  # fallback single


# =============================================================================
# Decision notification tests (Chunk 3)
# =============================================================================


class TestDecisionNotification:
    """Tests for broadcast_notification integration and notification_level config."""

    @pytest.fixture(autouse=True)
    def _no_real_notifications(self):
        """Override: this class tests notification paths with mocked adapters."""
        yield

    @patch("social_hook.notifications.broadcast_notification")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_broadcast,
    ):
        """Decision notification sent for not_post_worthy when level=all_decisions."""
        from social_hook.config.platforms import OutputPlatformConfig

        cfg = MagicMock()
        cfg.platforms = {
            "x": OutputPlatformConfig(
                enabled=True, priority="primary", type="builtin", account_tier="free"
            ),
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
        evaluation = _make_eval_mock(
            action="skip",
            reason="Minor fix",
        )
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0
        mock_broadcast.assert_called_once()
        # Verify the OutboundMessage contains project name
        msg = mock_broadcast.call_args[0][1]
        assert "test-proj" in msg.text

    @patch("social_hook.notifications.broadcast_notification")
    @patch("social_hook.drafting.draft")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_draft_fn,
        mock_broadcast,
    ):
        """Decision notification NOT sent for post_worthy when drafts are created.

        broadcast_notification IS called, but only for drafts (with buttons), not
        for the plain decision message.
        """
        from social_hook.config.platforms import OutputPlatformConfig
        from social_hook.config.yaml import ChannelConfig

        cfg = MagicMock()
        cfg.platforms = {
            "x": OutputPlatformConfig(
                enabled=True, priority="primary", type="builtin", account_tier="free"
            ),
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
        evaluation = _make_eval_mock(
            action="draft",
            reason="Great commit",
            angle="feature",
            episode_type="launch",
            post_category="arc",
        )
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        # draft() returns a result, so decision notification should be skipped
        from datetime import datetime

        mock_draft_obj = MagicMock()
        mock_draft_obj.id = "d1"
        mock_draft_obj.platform = "x"
        mock_draft_obj.content = "Test post"
        mock_draft_obj.media_paths = []
        mock_draft_obj.media_type = None

        mock_schedule = MagicMock()
        mock_schedule.datetime = datetime(2026, 1, 1, 12, 0)

        mock_result = MagicMock()
        mock_result.draft = mock_draft_obj
        mock_result.schedule = mock_schedule
        mock_result.thread_parts = []

        mock_draft_fn.return_value = [mock_result]

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0
        # broadcast_notification called for draft (with buttons), not plain decision
        assert mock_broadcast.call_count >= 1
        # All calls should have OutboundMessage with buttons (draft review)
        for c in mock_broadcast.call_args_list:
            msg = c[0][1]
            assert msg.buttons  # draft notifications have buttons

    @patch("social_hook.notifications.broadcast_notification")
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
        self,
        mock_config,
        mock_init_db,
        mock_db_path,
        mock_by_path,
        mock_parse,
        mock_context,
        mock_proj_config,
        mock_create_client,
        mock_evaluator_cls,
        mock_broadcast,
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
        evaluation = _make_eval_mock(
            action="skip",
            reason="Minor fix",
        )
        evaluator_instance.evaluate.return_value = evaluation
        mock_evaluator_cls.return_value = evaluator_instance

        exit_code = run_trigger("abc12345", "/tmp", dry_run=False)
        assert exit_code == 0
        mock_broadcast.assert_not_called()

    def test_broadcast_notification_message_format(self):
        """broadcast_notification receives correct OutboundMessage for decisions."""
        from social_hook.messaging.base import OutboundMessage
        from social_hook.notifications import broadcast_notification

        cfg = MagicMock()
        cfg.channels = {"web": MagicMock(enabled=False)}
        cfg.env.get = lambda key, default="": {}.get(key, default)

        msg = OutboundMessage(
            text=(
                "Commit evaluated\n\n"
                "Project: social-hook\n"
                "Commit: abc12345 - Fix typo in README\n"
                "Decision: skip\n"
                "Reasoning: Minor documentation fix, not interesting"
            )
        )

        # dry_run=True means nothing is sent, just verifying no crash
        broadcast_notification(cfg, msg, dry_run=True)

    def test_broadcast_notification_web(self):
        """broadcast_notification sends to web when enabled."""
        from social_hook.messaging.base import OutboundMessage
        from social_hook.notifications import broadcast_notification

        cfg = MagicMock()
        cfg.channels = {}  # No web config = enabled by default
        cfg.env.get = lambda key, default="": {}.get(key, default)

        msg = OutboundMessage(
            text=(
                "Commit evaluated\n\n"
                "Project: test-proj\n"
                "Commit: abc12345 - Fix typo\n"
                "Decision: skip\n"
                "Reasoning: Minor fix"
            )
        )

        with (
            patch("social_hook.filesystem.get_db_path", return_value=Path("/tmp/test.db")),
            patch("social_hook.messaging.web.WebAdapter") as mock_web_cls,
        ):
            mock_adapter = MagicMock()
            mock_web_cls.return_value = mock_adapter
            broadcast_notification(cfg, msg)
            mock_adapter.send_message.assert_called_once()
            sent_msg = mock_adapter.send_message.call_args[0][1]
            assert "skip" in sent_msg.text
            assert "test-proj" in sent_msg.text
            assert "abc12345" in sent_msg.text


# ---------------------------------------------------------------------------
# Merge queue action helpers
# ---------------------------------------------------------------------------


class TestBuildMergeCommit:
    """Tests for _build_merge_commit."""

    def test_basic(self):
        decisions = [
            Decision(
                id="dec_1",
                project_id="p1",
                commit_hash="abc12345",
                decision="draft",
                reasoning="Good",
                commit_summary="Added feature A",
            ),
            Decision(
                id="dec_2",
                project_id="p1",
                commit_hash="def67890",
                decision="draft",
                reasoning="Also good",
                commit_summary="Added feature B",
            ),
        ]
        from social_hook.models.core import Draft

        drafts = [
            Draft(
                id="d1",
                project_id="p1",
                decision_id="dec_1",
                platform="x",
                content="Draft about feature A",
            ),
            Draft(
                id="d2",
                project_id="p1",
                decision_id="dec_2",
                platform="x",
                content="Draft about feature B",
            ),
        ]
        result = _build_merge_commit(decisions, drafts)
        assert result.hash.startswith("merge-")
        assert "Merge of 2 drafts" in result.message
        assert "Original drafts to consolidate" in result.diff
        assert "Draft about feature A" in result.diff
        assert "Draft about feature B" in result.diff
        assert result.files_changed == []


class TestExecuteMergeGroups:
    """Tests for _execute_merge_groups."""

    def _make_draft(self, id="d1", platform="x", decision_id="dec_1", **kwargs):
        from social_hook.models.core import Draft

        defaults = {
            "id": id,
            "project_id": "p1",
            "decision_id": decision_id,
            "platform": platform,
            "content": f"Content for {id}",
            "status": "draft",
        }
        defaults.update(kwargs)
        return Draft(**defaults)

    def _make_decision(self, id="dec_1", commit_hash="abc12345", **kwargs):
        defaults = {
            "id": id,
            "project_id": "p1",
            "commit_hash": commit_hash,
            "decision": "draft",
            "reasoning": "Good commit",
            "angle": "feature",
            "post_category": "arc",
            "commit_summary": f"Summary for {id}",
        }
        defaults.update(kwargs)
        return Decision(**defaults)

    def _make_queue_actions(self, groups):
        """Build queue_actions dict from a list of (group_label, draft_ids, instruction) tuples."""
        from social_hook.llm.schemas import QueueAction

        actions = []
        for group_label, draft_ids, instruction in groups:
            for i, did in enumerate(draft_ids):
                qa = QueueAction(
                    action="merge",
                    draft_id=did,
                    reason="merge test",
                    merge_group=group_label,
                    merge_instruction=instruction if i == 0 else None,
                )
                actions.append(qa)
        return {"default": actions}

    def _setup_mocks(self, drafts_map, decisions_map):
        """Return (mock_config, mock_conn, mock_db, mock_project, mock_context, mock_pconfig)."""
        from social_hook.config.platforms import OutputPlatformConfig

        config = MagicMock()
        config.platforms = {
            "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin"),
            "linkedin": OutputPlatformConfig(enabled=True, priority="secondary", type="builtin"),
        }
        config.scheduling = MagicMock()
        conn = MagicMock()
        db = MagicMock()
        project = MagicMock()
        project.id = "p1"
        context = MagicMock()
        pconfig = MagicMock()

        return config, conn, db, project, context, pconfig

    @patch("social_hook.drafting.draft")
    @patch("social_hook.trigger.ops.supersede_draft")
    @patch("social_hook.trigger.ops.get_decision")
    @patch("social_hook.trigger.ops.get_draft")
    def test_happy_path(self, mock_get_draft, mock_get_dec, mock_supersede, mock_dfp):
        d1 = self._make_draft(id="d1", decision_id="dec_1")
        d2 = self._make_draft(id="d2", decision_id="dec_2")
        dec1 = self._make_decision(id="dec_1")
        dec2 = self._make_decision(id="dec_2", commit_hash="def67890")

        mock_get_draft.side_effect = lambda _conn, did: {"d1": d1, "d2": d2}.get(did)
        mock_get_dec.side_effect = lambda _conn, did: {"dec_1": dec1, "dec_2": dec2}.get(did)

        replacement_draft = MagicMock()
        replacement_draft.draft.id = "merged_d1"
        mock_dfp.return_value = [replacement_draft]

        queue_actions = self._make_queue_actions([("A", ["d1", "d2"], "Combine them")])
        config, conn, db, project, context, pconfig = self._setup_mocks(
            {"d1": d1, "d2": d2}, {"dec_1": dec1, "dec_2": dec2}
        )

        _execute_merge_groups(
            queue_actions,
            config,
            conn,
            db,
            project,
            context,
            pconfig,
            dry_run=False,
            verbose=False,
        )

        mock_dfp.assert_called_once()
        assert mock_supersede.call_count == 2
        mock_supersede.assert_any_call(conn, "d1", "merged_d1")
        mock_supersede.assert_any_call(conn, "d2", "merged_d1")

    @patch("social_hook.drafting.draft")
    @patch("social_hook.trigger.ops.get_decision")
    @patch("social_hook.trigger.ops.get_draft")
    def test_single_valid_draft_skips(self, mock_get_draft, mock_get_dec, mock_dfp):
        d1 = self._make_draft(id="d1")
        mock_get_draft.side_effect = lambda _conn, did: d1 if did == "d1" else None
        mock_get_dec.return_value = self._make_decision()

        queue_actions = self._make_queue_actions([("A", ["d1", "d2"], "Combine")])
        config, conn, db, project, context, pconfig = self._setup_mocks({}, {})

        _execute_merge_groups(
            queue_actions,
            config,
            conn,
            db,
            project,
            context,
            pconfig,
            dry_run=False,
            verbose=False,
        )

        mock_dfp.assert_not_called()

    @patch("social_hook.drafting.draft")
    @patch("social_hook.trigger.ops.supersede_draft")
    @patch("social_hook.trigger.ops.get_decision")
    @patch("social_hook.trigger.ops.get_draft")
    def test_multiple_groups(self, mock_get_draft, mock_get_dec, mock_supersede, mock_dfp):
        d1 = self._make_draft(id="d1", decision_id="dec_1")
        d2 = self._make_draft(id="d2", decision_id="dec_2")
        d3 = self._make_draft(id="d3", decision_id="dec_3")
        d4 = self._make_draft(id="d4", decision_id="dec_4")
        dec1 = self._make_decision(id="dec_1")
        dec2 = self._make_decision(id="dec_2", commit_hash="b")
        dec3 = self._make_decision(id="dec_3", commit_hash="c")
        dec4 = self._make_decision(id="dec_4", commit_hash="d")

        all_drafts = {"d1": d1, "d2": d2, "d3": d3, "d4": d4}
        all_decs = {"dec_1": dec1, "dec_2": dec2, "dec_3": dec3, "dec_4": dec4}
        mock_get_draft.side_effect = lambda _conn, did: all_drafts.get(did)
        mock_get_dec.side_effect = lambda _conn, did: all_decs.get(did)

        replacement = MagicMock()
        replacement.draft.id = "merged_x"
        mock_dfp.return_value = [replacement]

        queue_actions = self._make_queue_actions(
            [
                ("A", ["d1", "d2"], "Group A"),
                ("B", ["d3", "d4"], "Group B"),
            ]
        )
        config, conn, db, project, context, pconfig = self._setup_mocks({}, {})

        _execute_merge_groups(
            queue_actions,
            config,
            conn,
            db,
            project,
            context,
            pconfig,
            dry_run=False,
            verbose=False,
        )

        assert mock_dfp.call_count == 2

    @patch("social_hook.drafting.draft")
    @patch("social_hook.trigger.ops.supersede_draft")
    @patch("social_hook.trigger.ops.get_decision")
    @patch("social_hook.trigger.ops.get_draft")
    def test_cross_platform_subgrouping(
        self, mock_get_draft, mock_get_dec, mock_supersede, mock_dfp
    ):
        d1 = self._make_draft(id="d1", platform="x", decision_id="dec_1")
        d2 = self._make_draft(id="d2", platform="x", decision_id="dec_2")
        d3 = self._make_draft(id="d3", platform="linkedin", decision_id="dec_3")
        dec1 = self._make_decision(id="dec_1")
        dec2 = self._make_decision(id="dec_2", commit_hash="b")
        dec3 = self._make_decision(id="dec_3", commit_hash="c")

        all_drafts = {"d1": d1, "d2": d2, "d3": d3}
        all_decs = {"dec_1": dec1, "dec_2": dec2, "dec_3": dec3}
        mock_get_draft.side_effect = lambda _conn, did: all_drafts.get(did)
        mock_get_dec.side_effect = lambda _conn, did: all_decs.get(did)

        replacement = MagicMock()
        replacement.draft.id = "merged_x"
        mock_dfp.return_value = [replacement]

        queue_actions = self._make_queue_actions([("A", ["d1", "d2", "d3"], "Combine")])
        config, conn, db, project, context, pconfig = self._setup_mocks({}, {})

        _execute_merge_groups(
            queue_actions,
            config,
            conn,
            db,
            project,
            context,
            pconfig,
            dry_run=False,
            verbose=False,
        )

        # Only "x" group has 2+ drafts, "linkedin" has 1 → skipped
        mock_dfp.assert_called_once()
        assert mock_supersede.call_count == 2  # only the 2 "x" drafts superseded

    @patch("social_hook.drafting.draft")
    @patch("social_hook.trigger.ops.supersede_draft")
    @patch("social_hook.trigger.ops.get_decision")
    @patch("social_hook.trigger.ops.get_draft")
    def test_dry_run(self, mock_get_draft, mock_get_dec, mock_supersede, mock_dfp):
        d1 = self._make_draft(id="d1", decision_id="dec_1")
        d2 = self._make_draft(id="d2", decision_id="dec_2")
        dec1 = self._make_decision(id="dec_1")
        dec2 = self._make_decision(id="dec_2", commit_hash="b")

        mock_get_draft.side_effect = lambda _conn, did: {"d1": d1, "d2": d2}.get(did)
        mock_get_dec.side_effect = lambda _conn, did: {"dec_1": dec1, "dec_2": dec2}.get(did)

        replacement = MagicMock()
        replacement.draft.id = "merged_x"
        mock_dfp.return_value = [replacement]

        queue_actions = self._make_queue_actions([("A", ["d1", "d2"], "Combine")])
        config, conn, db, project, context, pconfig = self._setup_mocks({}, {})

        _execute_merge_groups(
            queue_actions,
            config,
            conn,
            db,
            project,
            context,
            pconfig,
            dry_run=True,
            verbose=False,
        )

        # dry_run: drafting happens (for preview) but supersede should not
        mock_supersede.assert_not_called()

    @patch("social_hook.drafting.draft")
    @patch("social_hook.trigger.ops.supersede_draft")
    @patch("social_hook.trigger.ops.get_decision")
    @patch("social_hook.trigger.ops.get_draft")
    def test_deferred_draft_no_supersede(
        self, mock_get_draft, mock_get_dec, mock_supersede, mock_dfp
    ):
        d1 = self._make_draft(id="d1", decision_id="dec_1")
        d2 = self._make_draft(id="d2", decision_id="dec_2")
        dec1 = self._make_decision(id="dec_1")
        dec2 = self._make_decision(id="dec_2", commit_hash="b")

        mock_get_draft.side_effect = lambda _conn, did: {"d1": d1, "d2": d2}.get(did)
        mock_get_dec.side_effect = lambda _conn, did: {"dec_1": dec1, "dec_2": dec2}.get(did)

        # Empty results = scheduler deferred the merged draft
        mock_dfp.return_value = []

        queue_actions = self._make_queue_actions([("A", ["d1", "d2"], "Combine")])
        config, conn, db, project, context, pconfig = self._setup_mocks({}, {})

        _execute_merge_groups(
            queue_actions,
            config,
            conn,
            db,
            project,
            context,
            pconfig,
            dry_run=False,
            verbose=False,
        )

        mock_dfp.assert_called_once()
        mock_supersede.assert_not_called()  # originals preserved
