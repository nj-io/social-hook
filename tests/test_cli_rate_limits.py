"""Tests for CLI rate-limits command."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


def _init_test_db(tmp_path):
    """Init DB and return (conn, db_path)."""
    from social_hook.db.connection import init_database

    db_path = tmp_path / "test.db"
    conn = init_database(db_path)
    return conn, db_path


class TestRateLimitsCommand:
    """Tests for rate-limits command."""

    def test_help_text(self):
        result = runner.invoke(app, ["rate-limits", "--help"])
        assert result.exit_code == 0
        assert "rate limit" in result.output.lower()

    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_db_path")
    def test_no_usage_data(self, mock_db_path, mock_config, tmp_path):
        """With an empty DB, all values should be zero."""
        from social_hook.config.yaml import Config

        conn, db_path = _init_test_db(tmp_path)
        conn.close()
        mock_db_path.return_value = db_path
        mock_config.return_value = Config()

        result = runner.invoke(app, ["rate-limits"])
        assert result.exit_code == 0
        assert "0/15 (auto)" in result.output
        assert "+ 0 (manual)" in result.output
        assert "now" in result.output
        assert "$0.00" in result.output

    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_db_path")
    def test_no_usage_data_json(self, mock_db_path, mock_config, tmp_path):
        """--json with empty DB returns zeros."""
        from social_hook.config.yaml import Config

        conn, db_path = _init_test_db(tmp_path)
        conn.close()
        mock_db_path.return_value = db_path
        mock_config.return_value = Config()

        result = runner.invoke(app, ["--json", "rate-limits"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["evaluations_today"] == 0
        assert data["max_evaluations_per_day"] == 15
        assert data["manual_evaluations_today"] == 0
        assert data["next_available_in_seconds"] == 0
        assert data["queued_triggers"] == 0
        assert data["cost_today_cents"] == 0.0

    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_db_path")
    def test_with_seeded_usage(self, mock_db_path, mock_config, tmp_path):
        """Seed usage_log rows and verify counts."""
        from social_hook.config.yaml import Config

        conn, db_path = _init_test_db(tmp_path)
        mock_db_path.return_value = db_path
        mock_config.return_value = Config()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        # 3 auto evals today
        for i in range(3):
            conn.execute(
                """
                INSERT INTO usage_log (id, project_id, operation_type, model,
                    input_tokens, output_tokens, cost_cents, trigger_source, created_at)
                VALUES (?, NULL, 'evaluate', 'test/model', 100, 50, 1.5, 'auto', ?)
                """,
                (f"u_auto_{i}", now),
            )
        # 1 manual eval today
        conn.execute(
            """
            INSERT INTO usage_log (id, project_id, operation_type, model,
                input_tokens, output_tokens, cost_cents, trigger_source, created_at)
            VALUES ('u_manual_0', NULL, 'evaluate', 'test/model', 100, 50, 2.0, 'manual', ?)
            """,
            (now,),
        )
        conn.commit()
        conn.close()

        result = runner.invoke(app, ["--json", "rate-limits"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["evaluations_today"] == 3
        assert data["manual_evaluations_today"] == 1
        # 3 * 1.5 + 2.0 = 6.5
        assert abs(data["cost_today_cents"] - 6.5) < 0.01

    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_db_path")
    def test_queued_triggers(self, mock_db_path, mock_config, tmp_path):
        """Deferred_eval decisions show as queued triggers."""
        from social_hook.config.yaml import Config
        from social_hook.db import operations as ops
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Decision, Project

        conn, db_path = _init_test_db(tmp_path)
        mock_db_path.return_value = db_path
        mock_config.return_value = Config()

        # Need a project for FK
        project = Project(id=generate_id("project"), name="t", repo_path="/tmp/t")
        ops.insert_project(conn, project)

        # 2 deferred_eval decisions
        for i in range(2):
            d = Decision(
                id=generate_id("decision"),
                project_id=project.id,
                commit_hash=f"abc{i}",
                decision="deferred_eval",
                reasoning="rate limited",
                processed=False,
            )
            ops.insert_decision(conn, d)
        conn.close()

        result = runner.invoke(app, ["--json", "rate-limits"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["queued_triggers"] == 2

    @patch("social_hook.config.yaml.load_full_config")
    @patch("social_hook.filesystem.get_db_path")
    def test_json_keys(self, mock_db_path, mock_config, tmp_path):
        """JSON output has all expected keys."""
        from social_hook.config.yaml import Config

        conn, db_path = _init_test_db(tmp_path)
        conn.close()
        mock_db_path.return_value = db_path
        mock_config.return_value = Config()

        result = runner.invoke(app, ["--json", "rate-limits"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        expected_keys = {
            "evaluations_today",
            "max_evaluations_per_day",
            "manual_evaluations_today",
            "next_available_in_seconds",
            "queued_triggers",
            "cost_today_cents",
        }
        assert set(data.keys()) == expected_keys
