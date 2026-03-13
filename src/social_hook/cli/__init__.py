"""CLI module for social-hook."""

from pathlib import Path

import typer

from social_hook import __version__
from social_hook.constants import PROJECT_DESCRIPTION, PROJECT_NAME, PROJECT_SLUG

# Create main Typer app
app = typer.Typer(
    name=PROJECT_SLUG,
    help=f"{PROJECT_DESCRIPTION}.",
    no_args_is_help=True,
)


# Global options callback
@app.callback()
def main(
    ctx: typer.Context,
    config: Path | None = typer.Option(
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
    typer.echo(f"{PROJECT_SLUG} {__version__}")


@app.command("help", context_settings={"allow_extra_args": True, "allow_interspersed_args": False})
def help_cmd(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as structured JSON"),
):
    """Show command help. Use --json for machine-readable output.

    Examples: social-hook help draft, social-hook help draft approve, social-hook help --json
    """
    import json as json_mod

    import click

    click_app = typer.main.get_command(app)
    command_parts = ctx.args  # e.g. ["draft", "approve"]

    def _cmd_to_dict(cmd, name=None):
        result = {}
        if name:
            result["name"] = name
        if cmd.help:
            result["help"] = cmd.help.split("\n")[0]

        if hasattr(cmd, "commands") and cmd.commands:
            cmds = {}
            for sub_name in sorted(cmd.commands):
                sub_cmd = cmd.commands[sub_name]
                if getattr(sub_cmd, "hidden", False):
                    continue
                cmds[sub_name] = _cmd_to_dict(sub_cmd, sub_name)
            if cmds:
                result["commands"] = cmds

        args = []
        for param in cmd.params:
            if isinstance(param, click.Argument):
                args.append(
                    {
                        "name": param.name,
                        "required": param.required,
                    }
                )
        if args:
            result["arguments"] = args

        opts = []
        skip_names = {"install_completion", "show_completion", "help", "ctx"}
        for param in cmd.params:
            if isinstance(param, click.Option):
                if param.name in skip_names:
                    continue
                opt_info = {
                    "name": param.opts[0] if param.opts else f"--{param.name}",
                }
                if len(param.opts) > 1:
                    opt_info["short"] = param.opts[1]
                if param.help:
                    opt_info["help"] = param.help
                type_name = param.type.name if hasattr(param.type, "name") else str(param.type)
                opt_info["type"] = type_name.upper()
                if param.default is not None:
                    opt_info["default"] = param.default
                opts.append(opt_info)
        if opts:
            result["options"] = opts

        return result

    def _resolve_command(parts):
        """Walk the Click command tree following the given path parts."""
        current = click_app
        info_parts = [PROJECT_SLUG]
        for part in parts:
            if not hasattr(current, "commands") or not current.commands:
                typer.echo(f"Unknown command: {' '.join(parts)}")
                raise typer.Exit(1)
            sub = current.commands.get(part)
            if not sub:
                typer.echo(f"Unknown command: {' '.join(parts)}")
                raise typer.Exit(1)
            current = sub
            info_parts.append(part)
        return current, " ".join(info_parts)

    if json_output:
        if command_parts:
            target, _ = _resolve_command(command_parts)
            typer.echo(
                json_mod.dumps(_cmd_to_dict(target, command_parts[-1]), indent=2, default=str)
            )
        else:
            global_options = []
            skip_names = {"install_completion", "show_completion", "help", "ctx"}
            for param in click_app.params:
                if isinstance(param, click.Option) and param.name not in skip_names:
                    opt_info = {
                        "name": param.opts[0] if param.opts else f"--{param.name}",
                    }
                    if len(param.opts) > 1:
                        opt_info["short"] = param.opts[1]
                    if param.help:
                        opt_info["help"] = param.help
                    type_name = param.type.name if hasattr(param.type, "name") else str(param.type)
                    opt_info["type"] = type_name.upper()
                    if param.default is not None:
                        opt_info["default"] = param.default  # type: ignore[assignment]
                    global_options.append(opt_info)

            output = {
                "name": PROJECT_SLUG,
                "global_options": global_options,
                "commands": {},
            }

            for cmd_name in sorted(click_app.commands):  # type: ignore[attr-defined]
                cmd = click_app.commands[cmd_name]  # type: ignore[attr-defined]
                if getattr(cmd, "hidden", False):
                    continue
                output["commands"][cmd_name] = _cmd_to_dict(cmd, cmd_name)  # type: ignore[index]

            typer.echo(json_mod.dumps(output, indent=2, default=str))
    elif command_parts:
        try:
            target, info_name = _resolve_command(command_parts)
            help_ctx = click.Context(target, info_name=info_name)
            typer.echo(target.get_help(help_ctx))
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}")
            raise typer.Exit(1) from None
    else:
        help_ctx = click.Context(click_app, info_name=PROJECT_SLUG)
        typer.echo(click_app.get_help(help_ctx))


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
    typer.echo(f"  3. Run: {PROJECT_SLUG} register /path/to/your/repo")


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


@app.command("consolidation-tick")
def consolidation_tick_cmd(
    ctx: typer.Context,
):
    """Run one consolidation tick: process batched decisions."""
    from social_hook.consolidation import consolidation_tick as do_tick

    dry_run = ctx.obj.get("dry_run", False)
    config_path = ctx.obj.get("config")

    processed = do_tick(
        dry_run=dry_run,
        config_path=str(config_path) if config_path else None,
    )
    if processed > 0:
        typer.echo(f"Processed {processed} consolidation decision(s)")


@app.command()
def web(
    ctx: typer.Context,
    port: int = typer.Option(3000, "--port", "-p", help="Port for Next.js dev server"),
    api_port: int = typer.Option(8741, "--api-port", help="Port for FastAPI server"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    install: bool = typer.Option(False, "--install", help="Run npm install before starting"),
):
    """Start the web dashboard (Next.js + FastAPI)."""
    import shutil
    import subprocess as sp

    if not shutil.which("node"):
        typer.echo("Error: Node.js is required for the web dashboard but was not found.")
        typer.echo("Install Node.js from https://nodejs.org/")
        raise typer.Exit(1)

    web_dir = Path(__file__).resolve().parent.parent.parent.parent / "web"
    if not web_dir.exists():
        typer.echo(f"Error: Web directory not found at {web_dir}")
        typer.echo("The web dashboard may not be installed.")
        raise typer.Exit(1)

    if install:
        typer.echo("Running npm install...")
        result = sp.run(["npm", "install"], cwd=str(web_dir))
        if result.returncode != 0:
            typer.echo("Error: npm install failed")
            raise typer.Exit(1)

    import socket

    def _find_free_port(start: int, bind_host: str) -> int:
        for p in range(start, start + 10):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((bind_host, p))
                    return p
                except OSError:
                    continue
        return start

    # Kill any stale process on the API port before starting
    def _kill_port(p: int) -> None:
        try:
            out = sp.check_output(["lsof", "-ti", f":{p}"], text=True).strip()
            if out:
                for pid in out.split("\n"):
                    sp.run(["kill", "-9", pid.strip()], check=False)
                import time

                time.sleep(0.5)
        except (sp.CalledProcessError, FileNotFoundError):
            pass

    _kill_port(api_port)

    port = _find_free_port(port, host)
    api_port = _find_free_port(api_port, host)

    # Start FastAPI in background
    typer.echo(f"Starting API server on {host}:{api_port}...")
    api_proc = sp.Popen(
        ["uvicorn", "social_hook.web.server:app", "--host", host, "--port", str(api_port)],
    )

    try:
        # Start Next.js in foreground
        typer.echo(f"Starting web dashboard on http://{host}:{port}...")
        import os

        next_env = os.environ.copy()
        next_env["NEXT_PUBLIC_API_URL"] = f"http://{host}:{api_port}"
        next_env["NEXT_PUBLIC_API_PORT"] = str(api_port)
        next_env["NEXT_PUBLIC_PROJECT_NAME"] = PROJECT_NAME
        next_env["NEXT_PUBLIC_PROJECT_SLUG"] = PROJECT_SLUG
        sp.run(
            ["npx", "next", "dev", "--port", str(port)],
            cwd=str(web_dir),
            env=next_env,
        )
    except KeyboardInterrupt:
        typer.echo("\nShutting down...")
    finally:
        api_proc.terminate()
        try:
            api_proc.wait(timeout=3)
        except sp.TimeoutExpired:
            api_proc.kill()
            api_proc.wait(timeout=2)


# =============================================================================
# Bot subcommand group
# =============================================================================

bot_app = typer.Typer(name="bot", help="Bot daemon management.", no_args_is_help=True)
app.add_typer(bot_app, name="bot")


@bot_app.command("start")
def bot_start(
    ctx: typer.Context,
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as background daemon"),
):
    """Start the bot daemon."""
    import os

    from social_hook.bot.process import is_running, read_pid

    # If the PID file contains our own PID, we were spawned by the
    # parent daemon launcher (eager PID write) — proceed normally.
    if is_running() and read_pid() != os.getpid():
        typer.echo("Bot is already running.")
        raise typer.Exit(1)

    from social_hook.config import load_full_config

    config_path = ctx.obj.get("config") if ctx.obj else None
    config = load_full_config(str(config_path) if config_path else None)

    from social_hook.bot.daemon import create_bot
    from social_hook.bot.process import get_pid_file
    from social_hook.errors import ConfigError

    try:
        bot = create_bot(config=config)
    except ConfigError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(1) from None

    if daemon:
        import shutil
        import subprocess as sp
        import sys

        from social_hook.filesystem import get_base_path

        log_path = get_base_path() / "logs" / "bot.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fd = open(log_path, "a")  # noqa: SIM115 — fd must outlive this scope for subprocess

        # Re-invoke in foreground mode as a detached subprocess
        binary = shutil.which(PROJECT_SLUG) or PROJECT_SLUG
        cmd = [binary, "bot", "start"]
        if config_path:
            cmd.extend(["--config", str(config_path)])

        kwargs: dict = {"stdout": log_fd, "stderr": log_fd, "stdin": sp.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = sp.DETACHED_PROCESS | sp.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        proc = sp.Popen(cmd, **kwargs)
        log_fd.close()  # Child inherited the FD; parent doesn't need it
        # Write PID eagerly so is_running() returns true immediately,
        # preventing duplicate daemons from concurrent start requests.
        # The child will overwrite with the same PID in bot.run().
        pid_file = get_pid_file()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid))
        typer.echo(f"Bot started (PID {proc.pid})")
        return
    else:
        import logging

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        typer.echo("Bot starting (foreground mode, Ctrl+C to stop)...")
        bot.run(pid_file=get_pid_file())


@bot_app.command("stop")
def bot_stop():
    """Stop the bot daemon."""
    from social_hook.bot.process import is_running, stop_bot

    if not is_running():
        typer.echo("Bot is not running.")
        return

    typer.echo("Stopping bot (may take up to 40s)...")
    if stop_bot():
        typer.echo("Bot stopped.")
    else:
        typer.echo("Failed to stop bot.")


@bot_app.command("status")
def bot_status():
    """Check if the bot daemon is running."""
    from social_hook.bot.process import is_running, read_pid

    if is_running():
        pid = read_pid()
        typer.echo(f"Bot is running (PID {pid})")
    else:
        typer.echo("Bot is not running.")


@app.command()
def discover(
    ctx: typer.Context,
    project_id: str = typer.Argument(..., help="Project ID to discover"),
):
    """Run two-pass project discovery and print results."""
    from social_hook.config.yaml import load_full_config
    from social_hook.db import operations as ops
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    verbose = ctx.obj.get("verbose", False)
    config_path = ctx.obj.get("config")

    try:
        config = load_full_config(
            yaml_path=str(config_path) if config_path else None,
        )
    except Exception as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(1) from None

    db_path = get_db_path()
    conn = init_database(db_path)

    project = ops.get_project(conn, project_id)
    if project is None:
        typer.echo(f"Project not found: {project_id}", err=True)
        conn.close()
        raise typer.Exit(1)

    from social_hook.config.project import load_project_config
    from social_hook.llm.discovery import discover_project
    from social_hook.llm.dry_run import DryRunContext
    from social_hook.llm.factory import create_client

    project_config = load_project_config(project.repo_path)
    dry_run = ctx.obj.get("dry_run", False)
    db_ctx = DryRunContext(conn, dry_run=dry_run)

    client = create_client(config.models.evaluator, config, verbose=verbose)

    typer.echo(f"Discovering project: {project.name} ({project.repo_path})")

    summary, selected_files, file_summaries, prompt_docs = discover_project(
        client=client,
        repo_path=project.repo_path,
        project_docs=project_config.context.project_docs,
        max_discovery_tokens=project_config.context.max_discovery_tokens,
        max_file_size=project_config.context.max_file_size,
        db=db_ctx,
        project_id=project.id,
    )

    if summary:
        if not dry_run:
            ops.update_project_summary(conn, project.id, summary)
            ops.update_discovery_files(conn, project.id, selected_files)
            if file_summaries:
                ops.upsert_file_summaries(conn, project.id, file_summaries)
            if prompt_docs:
                ops.update_prompt_docs(conn, project.id, prompt_docs)
        typer.echo(f"\nSelected files ({len(selected_files)}):")
        for f in selected_files:
            typer.echo(f"  {f}")
        typer.echo(f"\nSummary:\n{summary}")
    else:
        typer.echo("Discovery failed - no summary generated.", err=True)
        conn.close()
        raise typer.Exit(1)

    conn.close()


# =============================================================================
# Hidden commands (called by hooks, not by users)
# =============================================================================


@app.command("commit-hook", hidden=True)
def commit_hook():
    """Internal: called by PostToolUse hook. Reads JSON from stdin, filters for git commits."""
    import json
    import re
    import sys

    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return  # Silently exit — not our concern

    command = data.get("tool_input", {}).get("command", "")
    if not re.search(r"git\s+(commit|merge|rebase|cherry-pick)", command):
        return  # Not a git commit command, nothing to do

    cwd = data.get("cwd", "")
    if not cwd:
        return

    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            return
        commit_hash = result.stdout.strip()
    except Exception:
        return

    from social_hook.trigger import run_trigger

    run_trigger(commit_hash=commit_hash, repo_path=cwd)


@app.command("git-hook", hidden=True)
def git_hook():
    """Internal: called by git post-commit hook. Detects commit and triggers pipeline."""
    import logging
    import subprocess

    from social_hook.filesystem import get_base_path

    log_dir = get_base_path() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "git-hook.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("social_hook.git_hook")

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Failed to get repo root: %s", result.stderr)
            return
        repo_path = result.stdout.strip()

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_path,
        )
        if result.returncode != 0:
            logger.error("Failed to get HEAD: %s", result.stderr)
            return
        commit_hash = result.stdout.strip()

        logger.info("Git hook triggered: %s in %s", commit_hash[:8], repo_path)

        from social_hook.trigger import run_trigger

        exit_code = run_trigger(commit_hash=commit_hash, repo_path=repo_path)
        logger.info("Trigger completed with exit code %d", exit_code)
    except Exception:
        logger.exception("Git hook failed")


@app.command("narrative-capture", hidden=True)
def narrative_capture():
    """Internal: called by PreCompact hook. Reads JSON from stdin."""
    import json
    import logging
    import os
    import sys

    from social_hook.filesystem import get_base_path

    # Set up file logging for this subprocess
    log_dir = get_base_path() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "narrative.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)

    logger = logging.getLogger("social_hook.narrative_capture")

    try:
        data = json.loads(sys.stdin.read())
        session_id = data.get("session_id", "")
        transcript_path = data.get("transcript_path", "")
        cwd = data.get("cwd", "")
        trigger = data.get("trigger", "unknown")

        # Load config, check enabled
        from social_hook.config.yaml import load_full_config

        config = load_full_config()
        if not config.journey_capture.enabled:
            return

        # Init DB
        from social_hook.db.connection import init_database
        from social_hook.filesystem import get_db_path

        db_path = get_db_path()
        conn = init_database(db_path)

        # Normalize cwd and look up project (matches trigger.py pattern)
        normalized_cwd = os.path.realpath(cwd).rstrip("/")
        from social_hook.db import operations as ops

        project = ops.get_project_by_path(conn, normalized_cwd)
        if project is None:
            from social_hook.trigger import git_remote_origin

            origin = git_remote_origin(cwd)
            if origin:
                projects = ops.get_project_by_origin(conn, origin)
                if projects:
                    project = projects[0]

        if project is None:
            logger.debug("No registered project for cwd=%s", cwd)
            conn.close()
            return

        if project.paused:
            logger.debug("Project %s is paused, skipping", project.id)
            conn.close()
            return

        # Resolve model, reject Haiku
        model_str = config.journey_capture.model or config.models.evaluator
        if "haiku" in model_str.lower():
            logger.warning(
                "Skipping narrative extraction: %s is too small. Use Sonnet or Opus.",
                model_str,
            )
            conn.close()
            return

        # Resolve transcript path (with fallback for empty path bug)
        from pathlib import Path

        from social_hook.narrative.transcript import (
            discover_transcript_path,
            filter_for_extraction,
            format_for_prompt,
            read_transcript,
            truncate_to_budget,
        )

        resolved_path = transcript_path
        if not resolved_path or not Path(resolved_path).exists():
            resolved_path = discover_transcript_path(session_id, cwd)
        if not resolved_path or not Path(resolved_path).exists():
            logger.debug(
                "Transcript not found for session=%s cwd=%s",
                session_id,
                cwd,
            )
            conn.close()
            return

        # Read -> filter -> format -> truncate
        messages = read_transcript(resolved_path)
        filtered = filter_for_extraction(messages)
        if not filtered:
            logger.debug("No conversational content in transcript")
            conn.close()
            return
        formatted = format_for_prompt(filtered)
        text = truncate_to_budget(formatted)

        # Extract narrative
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.factory import create_client
        from social_hook.narrative.extractor import NarrativeExtractor

        db_ctx = DryRunContext(conn, dry_run=False)
        client = create_client(model_str, config)
        extractor = NarrativeExtractor(client)
        extraction = extractor.extract(
            transcript_text=text,
            project_name=project.name,
            cwd=normalized_cwd,
            db=db_ctx,
            project_id=project.id,
        )

        if extraction is None:
            conn.close()
            return

        # Save narrative
        from social_hook.narrative.storage import (
            cleanup_old_narratives,
            save_narrative,
        )

        save_narrative(project.id, extraction, session_id, trigger)
        cleanup_old_narratives(project.id)

        logger.info(
            "Narrative captured for project=%s session=%s",
            project.id,
            session_id,
        )
        conn.close()

    except Exception:
        logging.getLogger("social_hook.narrative_capture").exception("narrative-capture failed")
        # Exit 0 -- never disrupt the user's session


# =============================================================================
# Register subcommand modules
# =============================================================================

from social_hook.cli.arc import app as arc_app
from social_hook.cli.config import app as config_app
from social_hook.cli.inspect import app as inspect_app
from social_hook.cli.journey import app as journey_app
from social_hook.cli.manual import app as manual_app
from social_hook.cli.memory import app as memory_app
from social_hook.cli.project import app as project_app
from social_hook.cli.setup import app as setup_app
from social_hook.cli.test_cmd import app as test_app

# Project commands: register, unregister, list
app.add_typer(project_app, name="project", help="Project management.")

# Inspection commands: log, pending, usage
app.add_typer(inspect_app, name="inspect", help="Inspect system state.")

# Manual commands: evaluate, draft, post
app.add_typer(manual_app, name="manual", help="Manual operations.")

# Setup wizard
app.add_typer(setup_app, name="setup", help=f"Configure {PROJECT_SLUG}.")

# Test command
app.add_typer(test_app, name="test", help="Test commit evaluation.")

# Journey capture commands: on, off, status
app.add_typer(journey_app, name="journey", help="Development Journey capture.")

# Config commands: show, get, set
app.add_typer(config_app, name="config", help="View and modify configuration.")

# Memory commands: list, add, delete, clear
app.add_typer(memory_app, name="memory", help="Manage voice memories.")

# Arc commands: list, create, complete, abandon
app.add_typer(arc_app, name="arc", help="Manage narrative arcs.")

from social_hook.cli.decision import app as decision_app
from social_hook.cli.draft import app as draft_app

# Decision management: list, delete
app.add_typer(decision_app, name="decision", help="Decision management.")

# Draft lifecycle: approve, reject, schedule, cancel, retry, edit, etc.
app.add_typer(draft_app, name="draft", help="Draft lifecycle management.")

from social_hook.cli.media import app as media_app

# Media commands: gc
app.add_typer(media_app, name="media", help="Media management.")

from social_hook.cli.snapshot import app as snapshot_app

# DB snapshot management: save, restore, reset, list, delete
app.add_typer(snapshot_app, name="snapshot", help="DB snapshot management.")

from social_hook.cli.events import events as events_cmd
from social_hook.cli.quickstart import quickstart as quickstart_cmd
from social_hook.cli.rate_limits import rate_limits as rate_limits_cmd

app.command("events")(events_cmd)
app.command("rate-limits")(rate_limits_cmd)
app.command("quickstart")(quickstart_cmd)
