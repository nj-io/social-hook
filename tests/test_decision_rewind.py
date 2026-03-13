"""Tests for decision rewind: DB operation and CLI command."""

import json
import sqlite3
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from social_hook.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_env(tmp_path):
    """Isolated DB with a project, decision, drafts, and posts."""
    from social_hook.db.connection import init_database

    db_path = tmp_path / "social_hook.db"
    conn = init_database(str(db_path))

    # Project
    conn.execute(
        "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
        ("proj_test1", "test-project", str(tmp_path)),
    )
    conn.commit()
    conn.close()

    return {"tmp_path": tmp_path, "db_path": db_path}


def _conn(db_env):
    conn = sqlite3.connect(str(db_env["db_path"]))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_decision(
    conn, decision_id="decision_001", commit_hash="abc1234def5678", arc_id=None, processed=1
):
    conn.execute(
        """INSERT INTO decisions
           (id, project_id, commit_hash, decision, reasoning, processed, processed_at, batch_id, arc_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            decision_id,
            "proj_test1",
            commit_hash,
            "draft",
            "test reason",
            processed,
            "2026-01-01T00:00:00" if processed else None,
            "batch_1" if processed else None,
            arc_id,
        ),
    )
    conn.commit()


def _insert_draft(
    conn,
    draft_id,
    decision_id="decision_001",
    status="draft",
    is_intro=0,
    superseded_by=None,
    reference_post_id=None,
):
    conn.execute(
        """INSERT INTO drafts
           (id, project_id, decision_id, platform, status, content, is_intro,
            superseded_by, reference_post_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            draft_id,
            "proj_test1",
            decision_id,
            "x",
            status,
            "test content",
            is_intro,
            superseded_by,
            reference_post_id,
        ),
    )
    conn.commit()


def _insert_post(conn, post_id, draft_id):
    conn.execute(
        "INSERT INTO posts (id, project_id, draft_id, platform, external_id, external_url, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (post_id, "proj_test1", draft_id, "x", "ext_123", "https://x.com/123", "posted content"),
    )
    conn.commit()


def _insert_arc(conn, arc_id="arc_001", post_count=3):
    conn.execute(
        "INSERT INTO arcs (id, project_id, theme, status, post_count) VALUES (?, ?, ?, ?, ?)",
        (arc_id, "proj_test1", "Test arc", "active", post_count),
    )
    conn.commit()


def _insert_draft_tweet(conn, tweet_id, draft_id):
    conn.execute(
        "INSERT INTO draft_tweets (id, draft_id, position, content) VALUES (?, ?, ?, ?)",
        (tweet_id, draft_id, 1, "tweet content"),
    )
    conn.commit()


def _insert_draft_change(conn, change_id, draft_id):
    conn.execute(
        "INSERT INTO draft_changes (id, draft_id, field, old_value, new_value, changed_by) VALUES (?, ?, ?, ?, ?, ?)",
        (change_id, draft_id, "content", "old", "new", "human"),
    )
    conn.commit()


def _patch_paths(db_env):
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("social_hook.filesystem.get_db_path", return_value=db_env["db_path"]))
    stack.enter_context(
        patch("social_hook.filesystem.get_base_path", return_value=db_env["tmp_path"])
    )
    return stack


# ---------------------------------------------------------------------------
# DB operation tests
# ---------------------------------------------------------------------------


class TestRewindDecisionOps:
    def test_rewind_basic(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001")
        _insert_draft(conn, "draft_002")
        _insert_post(conn, "post_001", "draft_001")

        result = ops.rewind_decision(conn, "decision_001")

        assert result is not None
        assert result["decision_id"] == "decision_001"
        assert result["drafts_deleted"] == 2
        assert result["posts_deleted"] == 1

        # Decision still exists but is reset
        dec = ops.get_decision(conn, "decision_001")
        assert dec is not None
        assert dec.processed == 0
        assert dec.processed_at is None
        row = conn.execute(
            "SELECT batch_id FROM decisions WHERE id = ?", ("decision_001",)
        ).fetchone()
        assert row["batch_id"] is None

        # No drafts or posts remain
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM drafts WHERE decision_id = 'decision_001'"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM posts WHERE project_id = 'proj_test1'").fetchone()[0]
            == 0
        )
        conn.close()

    def test_rewind_with_arc_decrement(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        _insert_arc(conn, post_count=3)
        _insert_decision(conn, arc_id="arc_001")
        _insert_draft(conn, "draft_001")

        result = ops.rewind_decision(conn, "decision_001")

        assert result["arc_decremented"] is True
        arc = conn.execute("SELECT post_count FROM arcs WHERE id = 'arc_001'").fetchone()
        assert arc["post_count"] == 2
        conn.close()

    def test_rewind_no_drafts(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        _insert_decision(conn)

        result = ops.rewind_decision(conn, "decision_001")

        assert result["drafts_deleted"] == 0
        assert result["posts_deleted"] == 0
        dec = ops.get_decision(conn, "decision_001")
        assert dec.processed == 0
        conn.close()

    def test_rewind_refuses_posted_without_force(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001", status="posted")

        with pytest.raises(ValueError, match="posted draft"):
            ops.rewind_decision(conn, "decision_001")
        conn.close()

    def test_rewind_force_allows_posted(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001", status="posted")
        _insert_post(conn, "post_001", "draft_001")

        result = ops.rewind_decision(conn, "decision_001", force=True)

        assert result is not None
        assert result["had_posted_drafts"] is True
        assert result["drafts_deleted"] == 1
        assert result["posts_deleted"] == 1
        conn.close()

    def test_rewind_nulls_cross_references(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        # Decision 1 with draft and post
        _insert_decision(conn, "decision_001", "aaa111")
        _insert_draft(conn, "draft_001", "decision_001")
        _insert_post(conn, "post_001", "draft_001")

        # Decision 2 with draft referencing decision 1's artifacts
        _insert_decision(conn, "decision_002", "bbb222")
        _insert_draft(
            conn,
            "draft_002",
            "decision_002",
            superseded_by="draft_001",
            reference_post_id="post_001",
        )

        # Rewind decision 1
        ops.rewind_decision(conn, "decision_001")

        # Decision 2's draft should have NULL references
        d2 = conn.execute(
            "SELECT superseded_by, reference_post_id FROM drafts WHERE id = 'draft_002'"
        ).fetchone()
        assert d2["superseded_by"] is None
        assert d2["reference_post_id"] is None
        conn.close()

    def test_rewind_resets_platform_introduced(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        ops.set_platform_introduced(conn, "proj_test1", "x", True)

        _insert_decision(conn)
        _insert_draft(conn, "draft_001", is_intro=1)

        result = ops.rewind_decision(conn, "decision_001")

        assert result["audience_reset"] is True
        assert ops.get_platform_introduced(conn, "proj_test1", "x") is False
        conn.close()

    def test_rewind_preserves_platform_when_other_intros(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        ops.set_platform_introduced(conn, "proj_test1", "x", True)

        _insert_decision(conn, "decision_001", "aaa111")
        _insert_draft(conn, "draft_001", "decision_001", is_intro=1)

        # Another decision with an active intro draft
        _insert_decision(conn, "decision_002", "bbb222")
        _insert_draft(conn, "draft_002", "decision_002", is_intro=1)

        result = ops.rewind_decision(conn, "decision_001")

        assert result["audience_reset"] is False
        assert ops.get_platform_introduced(conn, "proj_test1", "x") is True
        conn.close()

    def test_rewind_not_found(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        result = ops.rewind_decision(conn, "decision_nonexistent")
        assert result is None
        conn.close()

    def test_rewind_arc_floor_zero(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        _insert_arc(conn, post_count=0)
        _insert_decision(conn, arc_id="arc_001")
        _insert_draft(conn, "draft_001")

        ops.rewind_decision(conn, "decision_001")

        arc = conn.execute("SELECT post_count FROM arcs WHERE id = 'arc_001'").fetchone()
        assert arc["post_count"] == 0
        conn.close()

    def test_rewind_deletes_changes_and_tweets(self, db_env):
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001")
        _insert_draft_tweet(conn, "tweet_001", "draft_001")
        _insert_draft_change(conn, "change_001", "draft_001")

        ops.rewind_decision(conn, "decision_001")

        assert (
            conn.execute(
                "SELECT COUNT(*) FROM draft_tweets WHERE draft_id = 'draft_001'"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM draft_changes WHERE draft_id = 'draft_001'"
            ).fetchone()[0]
            == 0
        )
        conn.close()

    def test_rewind_self_referencing_post(self, db_env):
        """Draft with reference_post_id pointing to its own decision's post — no FK violation."""
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001")
        _insert_post(conn, "post_001", "draft_001")
        # Second draft references the first draft's post
        _insert_draft(conn, "draft_002", reference_post_id="post_001")

        result = ops.rewind_decision(conn, "decision_001")

        assert result["drafts_deleted"] == 2
        assert result["posts_deleted"] == 1
        conn.close()

    def test_rewind_processed_hold_no_drafts(self, db_env):
        """Hold decision with processed=1 but no drafts — resets processed flag."""
        from social_hook.db import operations as ops

        conn = _conn(db_env)
        conn.execute(
            """INSERT INTO decisions
               (id, project_id, commit_hash, decision, reasoning, processed, processed_at, batch_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "decision_hold",
                "proj_test1",
                "ccc333",
                "hold",
                "wait for more",
                1,
                "2026-01-01T00:00:00",
                "batch_2",
            ),
        )
        conn.commit()

        result = ops.rewind_decision(conn, "decision_hold")

        assert result["drafts_deleted"] == 0
        dec = ops.get_decision(conn, "decision_hold")
        assert dec.processed == 0
        assert dec.processed_at is None
        conn.close()


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestRewindDecisionCli:
    def test_cli_rewind_by_commit(self, db_env):
        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001")
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "decision",
                    "rewind",
                    "abc1234def5678",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--yes",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "Rewound" in result.output
            assert "1 draft" in result.output

    def test_cli_rewind_by_decision_id(self, db_env):
        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001")
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "decision",
                    "rewind",
                    "decision_001",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--yes",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "Rewound" in result.output

    def test_cli_rewind_short_hash(self, db_env):
        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001")
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["decision", "rewind", "abc1234", "--project", str(db_env["tmp_path"]), "--yes"],
            )
            assert result.exit_code == 0, result.output
            assert "Rewound" in result.output

    def test_cli_rewind_ambiguous_hash(self, db_env):
        conn = _conn(db_env)
        _insert_decision(conn, "decision_001", "abc1111111")
        _insert_decision(conn, "decision_002", "abc2222222")
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["decision", "rewind", "abc", "--project", str(db_env["tmp_path"]), "--yes"],
            )
            assert result.exit_code == 1
            assert "Ambiguous" in result.output

    def test_cli_rewind_no_project(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                ["decision", "rewind", "abc1234", "--project", "/nonexistent/path", "--yes"],
            )
            assert result.exit_code == 1

    def test_cli_rewind_posted_blocked(self, db_env):
        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001", status="posted")
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "decision",
                    "rewind",
                    "abc1234def5678",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--yes",
                ],
            )
            assert result.exit_code == 1
            assert "posted" in result.output.lower()

    def test_cli_rewind_force_flag(self, db_env):
        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001", status="posted")
        _insert_post(conn, "post_001", "draft_001")
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "decision",
                    "rewind",
                    "abc1234def5678",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--yes",
                    "--force",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "Rewound" in result.output

    def test_cli_rewind_json_output(self, db_env):
        conn = _conn(db_env)
        _insert_decision(conn)
        _insert_draft(conn, "draft_001")
        conn.close()

        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "--json",
                    "decision",
                    "rewind",
                    "abc1234def5678",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--yes",
                ],
            )
            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["decision_id"] == "decision_001"
            assert data["drafts_deleted"] == 1
            assert data["backup"] == "_pre_rewind"

    def test_cli_rewind_not_found(self, db_env):
        with _patch_paths(db_env):
            result = runner.invoke(
                app,
                [
                    "decision",
                    "rewind",
                    "nonexistent123",
                    "--project",
                    str(db_env["tmp_path"]),
                    "--yes",
                ],
            )
            assert result.exit_code == 1
            assert "No decision found" in result.output
