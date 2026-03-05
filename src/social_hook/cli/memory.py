"""CLI commands for voice memory management."""

import os

import typer

app = typer.Typer(no_args_is_help=True)


def _resolve_project(project: str | None = None) -> str:
    """Resolve project path, defaulting to cwd."""
    return os.path.realpath(project or os.getcwd())


@app.command("list")
def list_cmd(
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
):
    """List all voice memories for a project."""
    from social_hook.config.project import list_memories

    repo_path = _resolve_project(project)
    memories = list_memories(repo_path)

    if not memories:
        typer.echo("No memories found.")
        return

    typer.echo(f"{'#':>3}  {'Date':<12} {'Context':<30} {'Feedback':<30} {'Draft ID'}")
    typer.echo("-" * 90)
    for i, m in enumerate(memories, start=1):
        ctx = m["context"][:28] + ".." if len(m["context"]) > 30 else m["context"]
        fb = m["feedback"][:28] + ".." if len(m["feedback"]) > 30 else m["feedback"]
        typer.echo(f"{i:>3}  {m['date']:<12} {ctx:<30} {fb:<30} {m['draft_id']}")


@app.command()
def add(
    context: str = typer.Option(..., "--context", "-c", help="Brief description of content type"),
    feedback: str = typer.Option(..., "--feedback", "-f", help="Human feedback text"),
    draft_id: str = typer.Option("", "--draft-id", "-d", help="Reference to original draft"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
):
    """Add a voice memory to the project."""
    from social_hook.config.project import save_memory

    repo_path = _resolve_project(project)
    save_memory(repo_path, context, feedback, draft_id)
    typer.echo("Memory added.")


@app.command()
def delete(
    index: int = typer.Argument(help="Memory number to delete (1-based, from 'memory list')"),
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
):
    """Delete a voice memory by its number."""
    from social_hook.config.project import delete_memory

    repo_path = _resolve_project(project)
    # Convert 1-based (user-facing) to 0-based (internal)
    zero_based = index - 1
    if zero_based < 0:
        typer.echo("Invalid index: must be >= 1", err=True)
        raise typer.Exit(1)
    try:
        delete_memory(repo_path, zero_based)
    except (IndexError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Memory #{index} deleted.")


@app.command()
def clear(
    project: str | None = typer.Option(None, "--project", "-p", help="Project path (default: cwd)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Clear all voice memories for a project."""
    from social_hook.config.project import clear_memories

    repo_path = _resolve_project(project)
    if not yes:
        confirm = typer.confirm("Clear all memories?")
        if not confirm:
            raise typer.Abort()
    count = clear_memories(repo_path)
    typer.echo(f"Cleared {count} memories.")
