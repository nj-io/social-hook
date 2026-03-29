"""Tests for DryRunContext."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from social_hook.llm.dry_run import _READ_PREFIXES, DryRunContext


class TestDryRunSkipsWrites:
    """Verify that write operations are skipped in dry-run mode."""

    def test_delete_skipped_in_dry_run(self):
        """delete_* returns None and does not call the underlying operation."""
        conn = MagicMock(spec=sqlite3.Connection)
        ctx = DryRunContext(conn, dry_run=True)

        with patch("social_hook.db.operations.delete_project") as mock_delete:
            result = ctx.delete_project("proj_123")

        mock_delete.assert_not_called()
        assert result is None

    def test_mark_skipped_in_dry_run(self):
        """mark_* returns None and does not call the underlying operation."""
        conn = MagicMock(spec=sqlite3.Connection)
        ctx = DryRunContext(conn, dry_run=True)

        with patch("social_hook.db.operations.mark_decisions_processed") as mock_mark:
            result = ctx.mark_decisions_processed(["dec_1", "dec_2"])

        mock_mark.assert_not_called()
        assert result is None

    def test_execute_skipped_in_dry_run(self):
        """execute_* returns None and does not call the underlying operation."""
        conn = MagicMock(spec=sqlite3.Connection)
        ctx = DryRunContext(conn, dry_run=True)

        with patch("social_hook.db.operations.execute_queue_action") as mock_exec:
            result = ctx.execute_queue_action({"action": "test"})

        mock_exec.assert_not_called()
        assert result is None


class TestDryRunPassesReads:
    """Verify that read operations pass through in dry-run mode."""

    def test_get_passes_through_in_dry_run(self):
        """get_project with dry_run=True still calls the underlying function."""
        conn = MagicMock(spec=sqlite3.Connection)
        ctx = DryRunContext(conn, dry_run=True)

        sentinel = MagicMock()
        with patch("social_hook.db.operations.get_project", return_value=sentinel) as mock_get:
            result = ctx.get_project("proj_123")

        mock_get.assert_called_once_with(conn, "proj_123")
        assert result is sentinel

    def test_all_reads_pass_through(self):
        """Every get_* function in db.operations would pass through by prefix logic."""
        from social_hook.db import operations as ops

        get_functions = [
            name for name in dir(ops) if callable(getattr(ops, name)) and name.startswith("get_")
        ]

        # Sanity check: there should be a non-trivial number of get_* functions
        assert len(get_functions) > 5, f"Expected many get_* functions, found {len(get_functions)}"

        # Verify the prefix logic: every get_* function name starts with _READ_PREFIXES
        for name in get_functions:
            assert name.startswith(_READ_PREFIXES), (
                f"{name} should be treated as a read but doesn't match _READ_PREFIXES"
            )


class TestDryRunWriteReturnValues:
    """Verify that skipped write operations return correct defaults."""

    def test_insert_returns_id(self):
        """insert_* returns the object's .id when skipped."""
        conn = MagicMock(spec=sqlite3.Connection)
        ctx = DryRunContext(conn, dry_run=True)

        obj = MagicMock()
        obj.id = "draft_abc"
        with patch("social_hook.db.operations.insert_draft"):
            result = ctx.insert_draft(obj)

        assert result == "draft_abc"

    def test_update_returns_false(self):
        """update_* returns False when skipped."""
        conn = MagicMock(spec=sqlite3.Connection)
        ctx = DryRunContext(conn, dry_run=True)

        with patch("social_hook.db.operations.update_draft"):
            result = ctx.update_draft("draft_abc", status="approved")

        assert result is False


class TestDryRunDisabled:
    """Verify that dry_run=False passes all operations through."""

    def test_delete_passes_through_when_not_dry_run(self):
        """delete_* calls the underlying function when dry_run=False."""
        conn = MagicMock(spec=sqlite3.Connection)
        ctx = DryRunContext(conn, dry_run=False)

        with patch("social_hook.db.operations.delete_project", return_value=True) as mock_del:
            result = ctx.delete_project("proj_123")

        mock_del.assert_called_once_with(conn, "proj_123")
        assert result is True


class TestDryRunAttributeError:
    """Verify that non-existent attributes raise AttributeError."""

    def test_nonexistent_attribute_raises(self):
        """Accessing a name not in db.operations raises AttributeError."""
        conn = MagicMock(spec=sqlite3.Connection)
        ctx = DryRunContext(conn, dry_run=False)

        with pytest.raises(AttributeError, match="not found in"):
            ctx.this_function_does_not_exist()
