"""Media management CLI commands."""

import json as json_mod

import typer

app = typer.Typer(name="media", help="Media management.", no_args_is_help=True)


@app.command("gc")
def media_gc(
    ctx: typer.Context,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Remove orphaned files from media cache.

    Example: social-hook media gc --dry-run
    Example: social-hook media gc --yes  (skip confirmation)
    """
    from social_hook.db.connection import init_database
    from social_hook.filesystem import cleanup_orphaned_media, get_db_path

    json_output = ctx.obj.get("json", False) if ctx.obj else False

    conn = init_database(get_db_path())
    try:
        # Always preview first
        would_remove = cleanup_orphaned_media(conn, dry_run=True)

        if not would_remove:
            if json_output:
                typer.echo(json_mod.dumps({"removed": [], "count": 0}))
            else:
                typer.echo("No orphaned media found.")
            return

        if dry_run:
            if json_output:
                typer.echo(
                    json_mod.dumps(
                        {"would_remove": would_remove, "count": len(would_remove)}, indent=2
                    )
                )
            else:
                typer.echo(f"Would remove {len(would_remove)} orphaned director(ies):")
                for p in would_remove:
                    typer.echo(f"  {p}")
            return

        if not yes:
            typer.echo(f"Will remove {len(would_remove)} orphaned director(ies):")
            for p in would_remove:
                typer.echo(f"  {p}")
            if not typer.confirm("Proceed?"):
                typer.echo("Aborted.")
                raise typer.Exit(0)

        removed = cleanup_orphaned_media(conn, dry_run=False)

        if json_output:
            typer.echo(json_mod.dumps({"removed": removed, "count": len(removed)}, indent=2))
        else:
            typer.echo(f"Removed {len(removed)} orphaned director(ies).")
    finally:
        conn.close()
