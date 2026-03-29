#!/usr/bin/env python3
"""WS4 Drivers verification script.

Usage:
    python scripts/verify_ws4.py --dry-run   # No API calls, no real env needed
    python scripts/verify_ws4.py --live      # Real API calls, needs ~/.social-hook/.env
"""

import argparse
import sys
from pathlib import Path


def verify_tier_config():
    """Verify X tier configuration."""
    print("--- Tier Configuration ---")
    from social_hook.config.yaml import TIER_CHAR_LIMITS, VALID_TIERS

    assert "free" in VALID_TIERS
    assert "basic" in VALID_TIERS
    assert "premium" in VALID_TIERS
    assert "premium_plus" in VALID_TIERS
    print(f"  OK  VALID_TIERS: {VALID_TIERS}")

    assert TIER_CHAR_LIMITS["free"] == 280
    assert TIER_CHAR_LIMITS["basic"] == 25_000
    assert TIER_CHAR_LIMITS["premium"] == 25_000
    assert TIER_CHAR_LIMITS["premium_plus"] == 25_000
    print("  OK  TIER_CHAR_LIMITS correct")
    print()
    return True


def verify_imports():
    """Verify all WS4 modules import cleanly."""
    print("--- Import Verification ---")
    modules = [
        ("social_hook.trigger", ["run_trigger", "parse_commit_info", "git_remote_origin"]),
        ("social_hook.scheduling", ["calculate_optimal_time", "ScheduleResult"]),
        (
            "social_hook.scheduler",
            ["scheduler_tick", "acquire_lock", "release_lock", "is_lock_stale", "get_lock_pid"],
        ),
        ("social_hook.bot.daemon", ["BotDaemon", "create_bot"]),
        (
            "social_hook.bot.process",
            ["get_pid_file", "write_pid", "read_pid", "is_pid_alive", "is_running", "stop_bot"],
        ),
        ("social_hook.bot.commands", ["handle_command", "handle_message"]),
        ("social_hook.bot.buttons", ["handle_callback"]),
        (
            "social_hook.bot.notifications",
            [
                "send_notification",
                "send_notification_with_buttons",
                "format_draft_review",
                "format_post_confirmation",
                "format_error_notification",
                "get_review_buttons",
            ],
        ),
        ("social_hook.setup.wizard", ["run_wizard"]),
        (
            "social_hook.setup.validation",
            [
                "validate_anthropic_key",
                "validate_telegram_bot",
                "validate_x_api",
                "get_linkedin_auth_url",
                "validate_media_gen",
            ],
        ),
        (
            "social_hook.setup.install",
            [
                "install_hook",
                "uninstall_hook",
                "check_hook_installed",
                "install_cron",
                "uninstall_cron",
                "check_cron_installed",
                "OUR_HOOK",
                "CRON_MARKER",
            ],
        ),
        ("social_hook.cli.project", ["app"]),
        ("social_hook.cli.manual", ["app"]),
        ("social_hook.cli.inspect", ["app"]),
        ("social_hook.cli.setup", ["app"]),
        ("social_hook.cli.test_cmd", ["app"]),
    ]

    errors = []
    for module_name, attrs in modules:
        try:
            mod = __import__(module_name, fromlist=attrs)
            for attr in attrs:
                if not hasattr(mod, attr):
                    errors.append(f"  {module_name} missing: {attr}")
            print(f"  OK  {module_name}")
        except Exception as e:
            errors.append(f"  FAIL  {module_name}: {e}")
            print(f"  FAIL  {module_name}: {e}")

    if errors:
        print(f"\n{len(errors)} import error(s)")
        return False
    print("  All imports OK\n")
    return True


def verify_db_operations():
    """Verify WS4-specific DB operations."""
    print("--- DB Operations ---")
    import tempfile

    from social_hook.db import (
        delete_project,
        get_all_recent_decisions,
        get_due_drafts,
        get_project_by_origin,
        get_project_by_path,
        init_database,
        insert_project,
    )
    from social_hook.filesystem import generate_id
    from social_hook.models.core import Project

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_database(db_path)

        # Test project with paused field
        project = Project(
            id=generate_id("project"),
            name="test-ws4",
            repo_path="/tmp/ws4-test",
            repo_origin="git@github.com:user/repo.git",
            paused=True,
        )
        insert_project(conn, project)

        # By path
        found = get_project_by_path(conn, "/tmp/ws4-test")
        assert found is not None, "get_project_by_path failed"
        assert found.paused is True, "paused field not persisted"
        print("  OK  get_project_by_path")

        # By origin
        found_list = get_project_by_origin(conn, "git@github.com:user/repo.git")
        assert len(found_list) == 1, "get_project_by_origin failed"
        print("  OK  get_project_by_origin")

        # Due drafts (should be empty)
        due = get_due_drafts(conn)
        assert due == [], "get_due_drafts should be empty"
        print("  OK  get_due_drafts")

        # All recent decisions
        decisions = get_all_recent_decisions(conn)
        assert decisions == [], "get_all_recent_decisions should be empty"
        print("  OK  get_all_recent_decisions")

        # Delete
        deleted = delete_project(conn, project.id)
        assert deleted is True, "delete_project failed"
        print("  OK  delete_project")

        conn.close()
    print()
    return True


def verify_scheduling():
    """Verify scheduling algorithm."""
    print("--- Scheduling ---")
    import tempfile

    from social_hook.db import init_database
    from social_hook.filesystem import generate_id
    from social_hook.scheduling import ScheduleResult, calculate_optimal_time

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_database(db_path)

        result = calculate_optimal_time(
            conn,
            generate_id("project"),
            tz="UTC",
        )
        assert isinstance(result, ScheduleResult)
        assert result.datetime is not None
        print(f"  OK  Next optimal time: {result.datetime}")
        print(f"       {result.time_reason}")

        conn.close()
    print()
    return True


def verify_hook_installer():
    """Verify hook installer."""
    print("--- Hook Installer ---")
    import tempfile

    from social_hook.setup.install import check_hook_installed, install_hook, uninstall_hook

    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_file = Path(tmpdir) / "hooks.json"

        # Install
        success, msg = install_hook(hooks_file)
        assert success, f"install_hook failed: {msg}"
        print(f"  OK  install: {msg}")

        # Check
        assert check_hook_installed(hooks_file), "check_hook_installed returned False"
        print("  OK  check: installed")

        # Idempotent
        success, msg = install_hook(hooks_file)
        assert "already" in msg.lower(), "not idempotent"
        print(f"  OK  idempotent: {msg}")

        # Uninstall
        success, msg = uninstall_hook(hooks_file)
        assert success, f"uninstall_hook failed: {msg}"
        assert not check_hook_installed(hooks_file)
        print(f"  OK  uninstall: {msg}")
    print()
    return True


def verify_bot_components():
    """Verify bot components."""
    print("--- Bot Components ---")
    from social_hook.bot.daemon import BotDaemon
    from social_hook.bot.notifications import (
        format_draft_review,
        format_error_notification,
        format_post_confirmation,
        get_review_buttons,
    )
    from social_hook.bot.process import get_pid_file, is_running

    # PID file
    pid_file = get_pid_file()
    print(f"  OK  PID file: {pid_file}")

    # Running check
    running = is_running()
    print(f"  OK  is_running: {running}")

    # Notification formatting (with new optional params)
    msg = format_draft_review(
        project_name="test",
        commit_hash="abc1234",
        commit_message="Test commit",
        platform="x",
        content="Hello world",
        char_count=11,
        is_thread=False,
    )
    assert "*New draft ready for review*" in msg
    print("  OK  format_draft_review")

    # Thread notification
    thread_msg = format_draft_review(
        project_name="test",
        commit_hash="abc1234",
        commit_message="Test commit",
        platform="x",
        content="Thread content",
        is_thread=True,
        tweet_count=5,
    )
    assert "Thread" in thread_msg or "thread" in thread_msg
    print("  OK  format_draft_review (thread)")

    msg = format_post_confirmation("test", "x", "content")
    assert "*Posted successfully*" in msg
    print("  OK  format_post_confirmation")

    msg = format_error_notification("test", "x", "error", retry_count=1)
    assert "*Post failed*" in msg
    print("  OK  format_error_notification")

    buttons = get_review_buttons("draft_123")
    assert len(buttons) == 2
    print("  OK  get_review_buttons")

    # BotDaemon creation
    bot = BotDaemon(token="test")
    assert bot.token == "test"
    print("  OK  BotDaemon creation")
    print()
    return True


def verify_cli():
    """Verify CLI structure."""
    print("--- CLI ---")
    from typer.testing import CliRunner

    from social_hook.cli import app

    runner = CliRunner()

    # Version
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    print(f"  OK  version: {result.output.strip()}")

    # Help
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    print("  OK  --help")

    # Bot status
    result = runner.invoke(app, ["bot", "status"])
    assert "not running" in result.output.lower()
    print("  OK  bot status")

    # Subcommand groups
    for cmd in ["project", "inspect", "manual", "setup", "test"]:
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0, f"{cmd} --help failed"
        print(f"  OK  {cmd} --help")
    print()
    return True


def main():
    parser = argparse.ArgumentParser(description="WS4 Drivers verification")
    parser.add_argument("--dry-run", action="store_true", help="No real API calls")
    parser.add_argument("--live", action="store_true", help="Real API calls")
    parser.parse_args()

    print("=" * 50)
    print("WS4 Drivers Verification")
    print("=" * 50 + "\n")

    results = []
    results.append(("tier_config", verify_tier_config()))
    results.append(("imports", verify_imports()))
    results.append(("db_operations", verify_db_operations()))
    results.append(("scheduling", verify_scheduling()))
    results.append(("hook_installer", verify_hook_installer()))
    results.append(("bot_components", verify_bot_components()))
    results.append(("cli", verify_cli()))

    print("=" * 50)
    print("Results:")
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  {status}  {name}")

    print("=" * 50)
    if all_pass:
        print("All checks passed!")
    else:
        print("Some checks failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
