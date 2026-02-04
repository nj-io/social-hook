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
        help="Run full pipeline without posting (for testing)",
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


# TODO(WS4): Remove this command when setup wizard is implemented.
# The setup wizard (social-hook setup) will handle initialization interactively.
# This command exists for development/testing to quickly bootstrap the database.
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


# Placeholder commands for future implementation


@app.command()
def trigger(
    commit: str = typer.Option(..., "--commit", help="Commit hash to evaluate"),
    repo: str = typer.Option(..., "--repo", help="Repository path"),
):
    """Evaluate a commit (called by hook)."""
    typer.echo(f"Trigger: commit={commit}, repo={repo}")
    typer.echo("(Not yet implemented)")


@app.command()
def register(
    path: Optional[Path] = typer.Argument(None, help="Path to repository (default: current directory)"),
):
    """Register a project for social-hook."""
    if path is None:
        path = Path.cwd()

    typer.echo(f"Registering project at {path}")
    typer.echo("(Not yet implemented)")


@app.command("list")
def list_projects():
    """List registered projects."""
    typer.echo("Registered projects:")
    typer.echo("(Not yet implemented)")


@app.command()
def pending(
    project_id: Optional[str] = typer.Argument(None, help="Project ID (optional)"),
):
    """View pending drafts."""
    typer.echo("Pending drafts:")
    typer.echo("(Not yet implemented)")


@app.command()
def log(
    project_id: Optional[str] = typer.Argument(None, help="Project ID (optional)"),
):
    """View decision log."""
    typer.echo("Decision log:")
    typer.echo("(Not yet implemented)")


@app.command()
def usage(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to show"),
):
    """View token usage and costs."""
    typer.echo(f"Usage for last {days} days:")
    typer.echo("(Not yet implemented)")
