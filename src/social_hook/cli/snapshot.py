"""CLI commands for DB snapshot management."""

import datetime
import json as json_mod
import re
import shutil
import sqlite3

import typer

app = typer.Typer(no_args_is_help=True)

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_NAME_LEN = 64


def _snapshots_dir():
    from social_hook.filesystem import get_base_path

    d = get_base_path() / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validate_name(name: str) -> None:
    if len(name) > _MAX_NAME_LEN:
        typer.echo(f"Name too long (max {_MAX_NAME_LEN} chars).")
        raise typer.Exit(1)
    if not _NAME_RE.match(name):
        typer.echo("Invalid name. Use only letters, digits, hyphens, underscores.")
        raise typer.Exit(1)


@app.command()
def save(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Snapshot name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Save a snapshot of the current database.

    Example: social-hook snapshot save before-refactor
    """
    from social_hook.filesystem import get_db_path

    _validate_name(name)
    json_output = ctx.obj.get("json", False) if ctx.obj else False
    db = get_db_path()
    dest = _snapshots_dir() / f"{name}.db"

    if dest.exists() and not yes:
        confirm = typer.confirm(f"Snapshot '{name}' already exists. Overwrite?")
        if not confirm:
            typer.echo("Cancelled.")
            return

    # Checkpoint WAL so all data is in the main DB file
    try:
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except sqlite3.DatabaseError:
        pass  # Best-effort; copy will still work

    shutil.copy2(str(db), str(dest))

    if json_output:
        typer.echo(json_mod.dumps({"saved": True, "name": name, "path": str(dest)}, indent=2))
    else:
        typer.echo(f"Snapshot saved: {name}")


@app.command()
def restore(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Snapshot name to restore"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Restore a database snapshot (backs up current DB first).

    Example: social-hook snapshot restore before-refactor
    """
    from social_hook.filesystem import get_db_path

    _validate_name(name)
    json_output = ctx.obj.get("json", False) if ctx.obj else False
    src = _snapshots_dir() / f"{name}.db"

    if not src.exists():
        typer.echo(f"Snapshot not found: {name}")
        raise typer.Exit(1)

    # Validate it's a real SQLite file
    try:
        conn = sqlite3.connect(str(src))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result[0] != "ok":
            typer.echo(f"Snapshot '{name}' failed integrity check: {result[0]}")
            raise typer.Exit(1)
    except sqlite3.DatabaseError:
        typer.echo(f"Snapshot '{name}' is not a valid SQLite database.")
        raise typer.Exit(1) from None

    # Refuse to restore while bot daemon has the DB open
    from social_hook.bot.process import is_running, read_pid

    if is_running():
        pid = read_pid()
        typer.echo(f"Bot daemon is running (PID {pid}). Stop it first: social-hook bot stop")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Restore snapshot '{name}'? Current DB will be backed up.")
        if not confirm:
            typer.echo("Cancelled.")
            return

    db = get_db_path()
    backup = _snapshots_dir() / "_pre_restore.db"
    if db.exists():
        shutil.copy2(str(db), str(backup))

    shutil.copy2(str(src), str(db))

    # Remove stale WAL/SHM files — they belong to the old DB and
    # cause "database disk image is malformed" if left behind.
    for suffix in ("-wal", "-shm"):
        stale = db.parent / f"{db.name}{suffix}"
        if stale.exists():
            stale.unlink()

    if json_output:
        typer.echo(
            json_mod.dumps({"restored": True, "name": name, "backup": str(backup)}, indent=2)
        )
    else:
        typer.echo(f"Restored snapshot: {name}")


@app.command()
def reset(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Reset database to empty state (backs up current DB first).

    Example: social-hook snapshot reset --yes
    """
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    json_output = ctx.obj.get("json", False) if ctx.obj else False

    # Refuse to reset while bot daemon has the DB open
    from social_hook.bot.process import is_running, read_pid

    if is_running():
        pid = read_pid()
        typer.echo(f"Bot daemon is running (PID {pid}). Stop it first: social-hook bot stop")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm("Reset database? Current DB will be backed up.")
        if not confirm:
            typer.echo("Cancelled.")
            return

    db = get_db_path()
    backup = _snapshots_dir() / "_pre_reset.db"
    if db.exists():
        shutil.copy2(str(db), str(backup))
        db.unlink()

    # Remove stale WAL/SHM files from the old DB
    for suffix in ("-wal", "-shm"):
        stale = db.parent / f"{db.name}{suffix}"
        if stale.exists():
            stale.unlink()

    init_database(db)

    if json_output:
        typer.echo(json_mod.dumps({"reset": True, "backup": str(backup)}, indent=2))
    else:
        typer.echo("Database reset to empty state.")


@app.command("list")
def list_cmd(
    ctx: typer.Context,
):
    """List saved snapshots.

    Example: social-hook snapshot list
    """
    json_output = ctx.obj.get("json", False) if ctx.obj else False
    snap_dir = _snapshots_dir()
    files = sorted(snap_dir.glob("*.db"))
    # Exclude _-prefixed backup files
    files = [f for f in files if not f.stem.startswith("_")]

    if json_output:
        items = []
        for f in files:
            stat = f.stat()
            items.append(
                {
                    "name": f.stem,
                    "size_bytes": stat.st_size,
                    "modified": datetime.datetime.fromtimestamp(
                        stat.st_mtime, tz=datetime.timezone.utc
                    ).isoformat(),
                }
            )
        typer.echo(json_mod.dumps(items, indent=2))
        return

    if not files:
        typer.echo("No snapshots found.")
        return

    typer.echo(f"{'Name':<30} {'Size':>10}  {'Modified'}")
    typer.echo("-" * 65)
    for f in files:
        stat = f.stat()
        size_kb = stat.st_size / 1024
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        typer.echo(f"{f.stem:<30} {size_kb:>8.1f}KB  {mtime}")


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Snapshot name to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a saved snapshot.

    Example: social-hook snapshot delete old-snapshot --yes
    """
    _validate_name(name)
    json_output = ctx.obj.get("json", False) if ctx.obj else False
    target = _snapshots_dir() / f"{name}.db"

    if not target.exists():
        typer.echo(f"Snapshot not found: {name}")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Delete snapshot '{name}'?")
        if not confirm:
            typer.echo("Cancelled.")
            return

    target.unlink()

    if json_output:
        typer.echo(json_mod.dumps({"deleted": True, "name": name}, indent=2))
    else:
        typer.echo(f"Snapshot deleted: {name}")
