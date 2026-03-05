"""Tests for CLI module (T21)."""

import json
import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from social_hook.cli import app
from social_hook.constants import PROJECT_NAME, PROJECT_SLUG

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


runner = CliRunner()


class TestVersion:
    """Tests for version command."""

    def test_version_output(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert PROJECT_SLUG in result.output

    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert PROJECT_SLUG in result.output.lower() or PROJECT_NAME in result.output


class TestInit:
    """Tests for init command."""

    def test_init_help(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "Initialize" in result.output or "initialize" in result.output


class TestTrigger:
    """Tests for trigger command."""

    def test_trigger_help(self):
        result = runner.invoke(app, ["trigger", "--help"])
        assert result.exit_code == 0
        output = strip_ansi(result.output)
        assert "--commit" in output
        assert "--repo" in output


class TestSchedulerTick:
    """Tests for scheduler-tick command."""

    def test_scheduler_tick_help(self):
        result = runner.invoke(app, ["scheduler-tick", "--help"])
        assert result.exit_code == 0


class TestBotSubcommand:
    """Tests for bot subcommand group."""

    def test_bot_help(self):
        result = runner.invoke(app, ["bot", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output
        assert "status" in result.output

    def test_bot_status_not_running(self):
        result = runner.invoke(app, ["bot", "status"])
        assert "not running" in result.output.lower()


class TestSubcommandGroups:
    """Tests for subcommand groups being registered."""

    def test_project_help(self):
        result = runner.invoke(app, ["project", "--help"])
        assert result.exit_code == 0

    def test_inspect_help(self):
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0

    def test_manual_help(self):
        result = runner.invoke(app, ["manual", "--help"])
        assert result.exit_code == 0

    def test_setup_help(self):
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0

    def test_test_help(self):
        result = runner.invoke(app, ["test", "--help"])
        assert result.exit_code == 0


class TestGlobalOptions:
    """Tests for global options."""

    def test_dry_run_flag(self):
        result = runner.invoke(app, ["--help"])
        assert "--dry-run" in strip_ansi(result.output)

    def test_verbose_flag(self):
        result = runner.invoke(app, ["--help"])
        assert "--verbose" in strip_ansi(result.output)

    def test_json_flag(self):
        result = runner.invoke(app, ["--help"])
        assert "--json" in strip_ansi(result.output)

    def test_config_flag(self):
        result = runner.invoke(app, ["--help"])
        assert "--config" in strip_ansi(result.output)


class TestLogsCommand:
    """Tests for logs command (D1)."""

    @patch("social_hook.cli.inspect.subprocess.run")
    @patch("social_hook.filesystem.get_base_path")
    def test_logs_invokes_tail(self, mock_base, mock_run, temp_dir):
        from social_hook.cli.inspect import app as inspect_app

        logs_dir = temp_dir / "logs"
        logs_dir.mkdir()
        (logs_dir / "trigger.log").write_text("log entry\n")
        (logs_dir / "scheduler.log").write_text("log entry\n")
        (logs_dir / "bot.log").write_text("log entry\n")
        mock_base.return_value = temp_dir

        inspect_runner = CliRunner()
        inspect_runner.invoke(inspect_app, ["logs"])
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "tail"
        assert "-f" in cmd

    @patch("social_hook.cli.inspect.subprocess.run")
    @patch("social_hook.filesystem.get_base_path")
    def test_logs_trigger_only(self, mock_base, mock_run, temp_dir):
        from social_hook.cli.inspect import app as inspect_app

        logs_dir = temp_dir / "logs"
        logs_dir.mkdir()
        (logs_dir / "trigger.log").write_text("log\n")
        mock_base.return_value = temp_dir

        inspect_runner = CliRunner()
        inspect_runner.invoke(inspect_app, ["logs", "trigger"])
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "trigger.log" in cmd[-1]

    @patch("social_hook.filesystem.get_base_path")
    def test_logs_no_files(self, mock_base, temp_dir):
        from social_hook.cli.inspect import app as inspect_app

        logs_dir = temp_dir / "logs"
        logs_dir.mkdir()
        mock_base.return_value = temp_dir

        inspect_runner = CliRunner()
        result = inspect_runner.invoke(inspect_app, ["logs"])
        assert "No log files" in result.output


class TestDraftCommand:
    """Tests for draft command (D2)."""

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_draft_decision_not_found(self, mock_config, mock_db_path, temp_dir):
        from social_hook.cli.manual import app as manual_app
        from social_hook.config.yaml import Config
        from social_hook.db import init_database

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = Config()
        init_database(db_path)

        manual_runner = CliRunner()
        result = manual_runner.invoke(manual_app, ["draft", "nonexistent"])
        assert result.exit_code == 1 or "not found" in result.output

    @patch("social_hook.filesystem.get_db_path")
    @patch("social_hook.config.load_full_config")
    def test_draft_not_post_worthy_allowed(self, mock_config, mock_db_path, temp_dir):
        """Manual draft overrides not_post_worthy decisions (no rejection)."""
        from social_hook.cli.manual import app as manual_app
        from social_hook.config.yaml import Config
        from social_hook.db import init_database, insert_decision, insert_project
        from social_hook.filesystem import generate_id
        from social_hook.models import Decision, Project

        db_path = temp_dir / "test.db"
        mock_db_path.return_value = db_path
        mock_config.return_value = Config()
        conn = init_database(db_path)

        project = Project(id=generate_id("project"), name="t", repo_path="/tmp/t")
        insert_project(conn, project)
        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash="abc",
            decision="skip",
            reasoning="test",
        )
        insert_decision(conn, decision)
        conn.close()

        # Mock the drafting pipeline (patch at source modules, not cli.manual)
        with (
            patch("social_hook.trigger.parse_commit_info") as mock_parse,
            patch("social_hook.config.project.load_project_config") as mock_proj,
            patch("social_hook.llm.prompts.assemble_evaluator_context") as mock_ctx,
            patch("social_hook.drafting.draft_for_platforms") as mock_draft,
        ):
            mock_parse.return_value = MagicMock(timestamp=None, parent_timestamp=None)
            mock_proj.return_value = MagicMock()
            mock_ctx.return_value = MagicMock()
            mock_draft.return_value = []

            manual_runner = CliRunner()
            result = manual_runner.invoke(manual_app, ["draft", decision.id])
            # Should succeed (override drafting, not reject)
            assert result.exit_code == 0
            mock_draft.assert_called_once()


class TestTestCmdRange:
    """Tests for test command --from/--to (D3)."""

    def test_from_to_help_text(self):
        result = runner.invoke(app, ["test", "--help"])
        output = strip_ansi(result.output)
        assert "--from" in output
        assert "--to" in output
        assert "--compare" in output

    def test_no_args_shows_error(self):
        result = runner.invoke(app, ["test", "--repo", "/tmp/fake"])
        # Should fail requesting --commit, --last, or --from/--to
        assert result.exit_code != 0 or "Specify" in result.output


class TestTestCmdCompare:
    """Tests for test command --compare (D3)."""

    def test_compare_shows_diffs(self, temp_dir):
        from social_hook.cli.test_cmd import _compare_results

        golden = temp_dir / "golden.json"
        golden.write_text(
            json.dumps(
                [
                    {"commit": "abc123", "exit_code": 0},
                    {"commit": "def456", "exit_code": 1},
                ]
            )
        )

        results = [
            {"commit": "abc123", "exit_code": 0},
            {"commit": "def456", "exit_code": 0},  # Changed
        ]

        # _compare_results prints output, just ensure no errors
        _compare_results(results, golden)

    def test_compare_all_match(self, temp_dir):
        from social_hook.cli.test_cmd import _compare_results

        golden = temp_dir / "golden.json"
        golden.write_text(
            json.dumps(
                [
                    {"commit": "abc123", "exit_code": 0},
                ]
            )
        )

        _compare_results([{"commit": "abc123", "exit_code": 0}], golden)

    def test_compare_missing_file(self, temp_dir):
        from social_hook.cli.test_cmd import _compare_results

        _compare_results([], temp_dir / "nonexistent.json")


class TestConfigCLI:
    """Tests for social-hook config commands."""

    def test_config_show(self, tmp_path):
        """config show outputs YAML."""
        import yaml

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "platforms": {
                        "x": {"enabled": True, "priority": "primary", "account_tier": "free"}
                    },
                }
            )
        )
        with patch("social_hook.filesystem.get_config_path", return_value=config_path):
            result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "platforms" in result.output

    def test_config_get(self, tmp_path):
        """config get returns a specific value."""
        import yaml

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "platforms": {
                        "x": {"enabled": True, "priority": "primary", "account_tier": "free"}
                    },
                }
            )
        )
        with patch("social_hook.filesystem.get_config_path", return_value=config_path):
            result = runner.invoke(app, ["config", "get", "platforms.x.account_tier"])
        assert result.exit_code == 0
        assert "free" in result.output

    def test_config_set(self, tmp_path):
        """config set modifies file correctly."""
        import yaml

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "platforms": {
                        "x": {"enabled": True, "priority": "primary", "account_tier": "free"}
                    },
                }
            )
        )
        with patch("social_hook.filesystem.get_config_path", return_value=config_path):
            result = runner.invoke(app, ["config", "set", "platforms.x.account_tier", "premium"])
        assert result.exit_code == 0
        updated = yaml.safe_load(config_path.read_text())
        assert updated["platforms"]["x"]["account_tier"] == "premium"


class TestMemoryCLI:
    """Tests for social-hook memory commands."""

    def test_memory_list_empty(self, tmp_path):
        """memory list shows empty message."""
        result = runner.invoke(app, ["memory", "list", "--project", str(tmp_path)])
        assert result.exit_code == 0
        assert "No memories found" in result.output

    def test_memory_add_and_list(self, tmp_path):
        """memory add then list shows entry."""
        config_dir = tmp_path / ".social-hook"
        config_dir.mkdir()
        result = runner.invoke(
            app,
            [
                "memory",
                "add",
                "--context",
                "test ctx",
                "--feedback",
                "test fb",
                "--project",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Memory added" in result.output

        result2 = runner.invoke(app, ["memory", "list", "--project", str(tmp_path)])
        assert result2.exit_code == 0
        assert "test ctx" in result2.output


class TestInspectPlatforms:
    """Tests for inspect platforms command."""

    @patch("social_hook.config.load_full_config")
    def test_platforms_lists_all(self, mock_config):
        from social_hook.cli.inspect import app as inspect_app
        from social_hook.config.platforms import OutputPlatformConfig
        from social_hook.config.yaml import Config

        mock_config.return_value = Config(
            platforms={
                "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin"),
                "linkedin": OutputPlatformConfig(
                    enabled=False, priority="secondary", type="builtin"
                ),
            }
        )

        inspect_runner = CliRunner()
        result = inspect_runner.invoke(inspect_app, ["platforms"])
        assert result.exit_code == 0
        assert "x" in result.output
        assert "enabled" in result.output
        assert "linkedin" in result.output
        assert "disabled" in result.output

    @patch("social_hook.config.load_full_config")
    def test_platforms_json_output(self, mock_config):
        from social_hook.cli.inspect import app as inspect_app
        from social_hook.config.platforms import OutputPlatformConfig
        from social_hook.config.yaml import Config

        mock_config.return_value = Config(
            platforms={
                "x": OutputPlatformConfig(enabled=True, priority="primary", type="builtin"),
            }
        )

        inspect_runner = CliRunner()
        result = inspect_runner.invoke(inspect_app, ["platforms"], obj={"json": True})
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "x"
        assert data[0]["enabled"] is True
