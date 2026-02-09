"""CLI module for social-hook."""

from pathlib import Path
from typing import Optional

import typer

from social_hook import __version__

# Create main Typer app
app = typer.Typer(
    name="social-hook",
    help="Automated social media content from development activity.",
    no_args_is_help=True,
)


# Global options callback
@app.callback()
def main(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Override config location",
        envvar="SOCIAL_HOOK_CONFIG",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run full pipeline without posting or DB writes (for testing)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="JSON output for scripting",
    ),
):
    """Social Hook - Automated social media content from development activity."""
    # Store options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["dry_run"] = dry_run
    ctx.obj["verbose"] = verbose
    ctx.obj["json"] = json_output


@app.command()
def version():
    """Show version information."""
    typer.echo(f"social-hook {__version__}")


@app.command()
def init():
    """Initialize social-hook (create directories and database).

    DEV ONLY: This is a temporary command for testing. Use 'social-hook setup'
    when it's available (WS4).
    """
    from social_hook.db import init_database
    from social_hook.filesystem import get_db_path, init_filesystem

    # Initialize file system
    base = init_filesystem()
    typer.echo(f"Created directory structure at {base}")

    # Initialize database
    db_path = get_db_path()
    init_database(db_path)
    typer.echo(f"Initialized database at {db_path}")

    typer.echo("\nNext steps:")
    typer.echo(f"  1. Copy {base}/.env.example to {base}/.env and add your API keys")
    typer.echo(f"  2. Copy {base}/config.yaml.example to {base}/config.yaml and customize")
    typer.echo("  3. Run: social-hook register /path/to/your/repo")


@app.command()
def trigger(
    ctx: typer.Context,
    commit: str = typer.Option(..., "--commit", help="Commit hash to evaluate"),
    repo: str = typer.Option(..., "--repo", help="Repository path"),
):
    """Evaluate a commit and create draft if post-worthy (called by hook)."""
    from social_hook.trigger import run_trigger

    dry_run = ctx.obj.get("dry_run", False)
    verbose = ctx.obj.get("verbose", False)
    config_path = ctx.obj.get("config")

    exit_code = run_trigger(
        commit_hash=commit,
        repo_path=repo,
        dry_run=dry_run,
        config_path=str(config_path) if config_path else None,
        verbose=verbose,
    )
    raise SystemExit(exit_code)


@app.command("scheduler-tick")
def scheduler_tick(
    ctx: typer.Context,
):
    """Run one scheduler tick: post all due drafts."""
    from social_hook.scheduler import scheduler_tick as do_tick

    dry_run = ctx.obj.get("dry_run", False)
    config_path = ctx.obj.get("config")

    processed = do_tick(
        dry_run=dry_run,
        config_path=str(config_path) if config_path else None,
    )
    if processed > 0:
        typer.echo(f"Processed {processed} draft(s)")


# =============================================================================
# Bot subcommand group
# =============================================================================

bot_app = typer.Typer(name="bot", help="Telegram bot management.", no_args_is_help=True)
app.add_typer(bot_app, name="bot")


@bot_app.command("start")
def bot_start(
    ctx: typer.Context,
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as background daemon"),
):
    """Start the Telegram bot."""
    from social_hook.bot.process import is_running

    if is_running():
        typer.echo("Bot is already running.")
        raise typer.Exit(1)

    from social_hook.config import load_full_config

    config_path = ctx.obj.get("config") if ctx.obj else None
    config = load_full_config(str(config_path) if config_path else None)

    token = config.env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        typer.echo("Error: TELEGRAM_BOT_TOKEN not set in .env")
        raise typer.Exit(1)

    allowed_str = config.env.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    allowed = {s.strip() for s in allowed_str.split(",") if s.strip()} if allowed_str else set()

    from social_hook.bot.daemon import create_bot
    from social_hook.bot.process import get_pid_file

    bot = create_bot(token=token, allowed_chat_ids=allowed, config=config)

    if daemon:
        import os
        import sys

        pid = os.fork()
        if pid > 0:
            typer.echo(f"Bot started (PID {pid})")
            return

        # Child process
        os.setsid()
        sys.stdin.close()

        # Redirect stdout/stderr to log file
        from social_hook.filesystem import get_base_path

        log_path = get_base_path() / "logs" / "bot.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fd = open(log_path, "a")
        os.dup2(log_fd.fileno(), sys.stdout.fileno())
        os.dup2(log_fd.fileno(), sys.stderr.fileno())

        bot.run(pid_file=get_pid_file())
    else:
        typer.echo("Bot starting (foreground mode, Ctrl+C to stop)...")
        bot.run(pid_file=get_pid_file())


@bot_app.command("stop")
def bot_stop():
    """Stop the Telegram bot."""
    from social_hook.bot.process import is_running, stop_bot

    if not is_running():
        typer.echo("Bot is not running.")
        return

    if stop_bot():
        typer.echo("Bot stopped.")
    else:
        typer.echo("Failed to stop bot.")


@bot_app.command("status")
def bot_status():
    """Check if the Telegram bot is running."""
    from social_hook.bot.process import is_running, read_pid

    if is_running():
        pid = read_pid()
        typer.echo(f"Bot is running (PID {pid})")
    else:
        typer.echo("Bot is not running.")


# =============================================================================
# Register subcommand modules
# =============================================================================

from social_hook.cli.project import app as project_app
from social_hook.cli.inspect import app as inspect_app
from social_hook.cli.manual import app as manual_app
from social_hook.cli.setup import app as setup_app
from social_hook.cli.test_cmd import app as test_app

# Project commands: register, unregister, list
app.add_typer(project_app, name="project", help="Project management.")

# Inspection commands: log, pending, usage
app.add_typer(inspect_app, name="inspect", help="Inspect system state.")

# Manual commands: evaluate, draft, post
app.add_typer(manual_app, name="manual", help="Manual operations.")

# Setup wizard
app.add_typer(setup_app, name="setup", help="Configure social-hook.")

# Test command
app.add_typer(test_app, name="test", help="Test commit evaluation.")
