"""Quickstart command — zero to first draft with minimal input.

Registers a project, imports commits, runs discovery, and generates a
summary-based first draft. Optionally batch-evaluates recent commits.

Example: social-hook quickstart /path/to/repo
Example: social-hook quickstart --evaluate-last 3 /path/to/repo
"""

from __future__ import annotations

import json as json_mod
import os
import subprocess
from pathlib import Path
from typing import Any, NoReturn

import typer

from social_hook.constants import PROJECT_SLUG

app = typer.Typer()


@app.command(
    help=(
        "Get started instantly. Auto-detects setup, registers the current repo, "
        "and generates your first draft.\n\n"
        "Makes LLM calls for project discovery and drafting. "
        "Writes decisions and drafts to the database.\n\n"
        "Example: social-hook quickstart /path/to/repo\n"
        "Example: social-hook quickstart --evaluate-last 3 --yes"
    ),
)
def quickstart(
    ctx: typer.Context,
    path: str = typer.Argument(None, help="Repository path (default: current directory)"),
    key: str = typer.Option(None, "--key", help="Anthropic API key (skips prompt)"),
    evaluate_last: int = typer.Option(
        0,
        "--evaluate-last",
        help="Evaluate last N commits for additional drafts (max 5)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip all confirmation prompts"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Run the quickstart flow.

    Zero-to-first-draft onboarding. Auto-detects your LLM provider,
    registers your repo, imports commit history, runs AI project discovery,
    and generates an introductory draft — all in one command.
    """
    # Resolve JSON output from global or local flag
    is_json = json_output or (ctx.obj or {}).get("json", False)
    dry_run = (ctx.obj or {}).get("dry_run", False)
    verbose = (ctx.obj or {}).get("verbose", False)

    # Cap evaluate_last
    evaluate_last = min(max(evaluate_last, 0), 5)

    # 1. Resolve path, verify git repo
    repo_path = str(Path(path or os.getcwd()).expanduser().resolve())
    result = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _error_exit(f"Not a git repository: {repo_path}", is_json)

    project_name = Path(repo_path).name

    # 2. Confirm before proceeding
    if not yes and not is_json:
        typer.echo(f"Repository: {repo_path}")
        typer.echo(f"Project name: {project_name}")
        if not typer.confirm("Continue?", default=True):
            raise typer.Exit(0)

    # 3. Check for existing config
    from social_hook.filesystem import init_filesystem

    base = init_filesystem()
    config_path = base / "config.yaml"
    has_config = config_path.exists()

    if not has_config:
        # 4. Auto-detect providers and configure
        _auto_configure(base, key, is_json, verbose)

    # 5. Load config
    from social_hook.config.yaml import load_full_config

    try:
        config = load_full_config()
    except Exception as e:
        _error_exit(f"Config error: {e}", is_json)

    # 6. Initialize DB
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    db_path = get_db_path()
    conn = init_database(db_path)

    # 7. Register project (or find existing — check path and origin)
    from social_hook.db.operations import get_project_by_path, register_project

    project = get_project_by_path(conn, repo_path)
    if project is None:
        # Also check by origin (handles worktrees pointing to same repo)
        origin_result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        if origin_result.returncode == 0:
            origin_url = origin_result.stdout.strip()
            row = conn.execute(
                "SELECT id, name FROM projects WHERE repo_origin = ?", (origin_url,)
            ).fetchone()
            if row:
                from social_hook.db.operations import get_project

                project = get_project(conn, row[0])
                if project and not is_json:
                    typer.echo(
                        f"Found existing project by origin: {project.name} ({project.id[:8]})"
                    )

    if project is None:
        try:
            project, _origin = register_project(conn, repo_path, name=project_name)
            if not is_json:
                typer.echo(f"Registered project: {project.name} ({project.id[:8]})")
        except ValueError as e:
            _error_exit(str(e), is_json)
    elif not is_json:
        typer.echo(f"Project already registered: {project.name} ({project.id[:8]})")

    # 8. Import commits
    from social_hook.import_commits import import_project_commits

    if not is_json:
        typer.echo("Importing commits...")
    import_result = import_project_commits(conn, project.id, repo_path)
    if not is_json:
        typer.echo(
            f"  Imported {import_result['imported']} commits ({import_result['skipped']} skipped)"
        )

    # 9. Run project discovery
    summary = _run_discovery(config, conn, project, repo_path, dry_run, verbose, is_json)

    # 10. Summary-based first draft
    draft_info = None
    if summary and not dry_run:
        draft_info = _run_summary_draft(config, conn, project, summary, repo_path, verbose, is_json)

    # 11. Batch evaluate (if requested)
    batch_results: list[dict[str, Any]] = []
    if evaluate_last > 0:
        batch_results = _run_batch_evaluate(
            config, conn, project, repo_path, evaluate_last, dry_run, verbose, is_json
        )

    # 12. Display results
    if is_json:
        output: dict[str, Any] = {
            "project_id": project.id,
            "project_name": project.name,
            "repo_path": repo_path,
            "commits_imported": import_result["imported"],
            "summary_generated": summary is not None,
        }
        if draft_info:
            output["first_draft"] = draft_info
        if batch_results:
            output["batch_evaluate"] = batch_results
        typer.echo(json_mod.dumps(output, indent=2, default=str))
    else:
        if draft_info:
            typer.echo(f"\n{'=' * 50}")
            typer.echo("First Draft (preview)")
            typer.echo(f"{'=' * 50}")
            typer.echo(draft_info.get("content", "(no content)"))
            typer.echo(f"{'=' * 50}\n")
        if batch_results:
            typer.echo(f"Batch evaluated {len(batch_results)} commit(s)")

        typer.echo("\nNext steps:")
        typer.echo(f"  Run `{PROJECT_SLUG} setup` to fully configure your project")
        typer.echo(f"  Run `{PROJECT_SLUG} web` to open the dashboard")

    conn.close()


def _error_exit(msg: str, is_json: bool) -> NoReturn:
    """Print error and exit."""
    if is_json:
        typer.echo(json_mod.dumps({"error": msg}))
    else:
        typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(1)


def _auto_configure(base: Path, api_key: str | None, is_json: bool, verbose: bool) -> None:
    """Auto-detect providers and write minimal config."""
    import yaml

    from social_hook.setup.wizard import discover_providers

    env_dict = dict(os.environ)
    if api_key:
        env_dict["ANTHROPIC_API_KEY"] = api_key

    providers = discover_providers(env_dict)

    # Pick best provider
    models: dict[str, str] = {}
    env_vars: dict[str, str] = {}

    has_cli = any(p["id"] == "claude-cli" and p["status"] == "detected" for p in providers)
    has_anthropic = any(p["id"] == "anthropic" and p["status"] == "configured" for p in providers)

    if has_cli:
        models = {
            "evaluator": "claude-cli/sonnet",
            "drafter": "claude-cli/sonnet",
            "gatekeeper": "claude-cli/haiku",
        }
        if not is_json:
            typer.echo("Using Claude CLI (subscription, $0 extra cost)")
    elif api_key or has_anthropic:
        models = {
            "evaluator": "anthropic/claude-sonnet-4-5",
            "drafter": "anthropic/claude-sonnet-4-5",
            "gatekeeper": "anthropic/claude-haiku-4-5",
        }
        if api_key:
            env_vars["ANTHROPIC_API_KEY"] = api_key
        if not is_json:
            typer.echo("Using Anthropic API")
    else:
        # Check other providers
        has_openrouter = any(
            p["id"] == "openrouter" and p["status"] == "configured" for p in providers
        )
        if has_openrouter:
            models = {
                "evaluator": "openrouter/anthropic/claude-sonnet-4-5",
                "drafter": "openrouter/anthropic/claude-sonnet-4-5",
                "gatekeeper": "openrouter/anthropic/claude-haiku-4-5",
            }
            if not is_json:
                typer.echo("Using OpenRouter API")
        else:
            if not is_json:
                typer.echo("No API key detected. Provide one with --key or set ANTHROPIC_API_KEY.")
            _error_exit("No LLM provider configured", is_json)

    # Write minimal config
    config_data: dict[str, Any] = {"models": models}

    # Default strategy — the setup wizard creates targets/accounts separately
    from social_hook.setup.templates import get_template

    template = get_template("building-public")
    if template:
        config_data["content_strategies"] = {
            "building-public": {
                "audience": template.defaults.audience,
                "post_when": template.defaults.post_when,
            }
        }
        config_data["content_strategy"] = "building-public"

    config_path = base / "config.yaml"
    config_path.write_text(yaml.dump(config_data, default_flow_style=False))

    # Write env if needed
    if env_vars:
        env_path = base / ".env"
        existing: dict[str, str] = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()
        existing.update(env_vars)
        env_path.write_text("\n".join(f"{k}={v}" for k, v in sorted(existing.items())) + "\n")

    if not is_json:
        typer.echo(f"Config written to {config_path}")


def _run_discovery(
    config: Any,
    conn: Any,
    project: Any,
    repo_path: str,
    dry_run: bool,
    verbose: bool,
    is_json: bool,
) -> str | None:
    """Run project discovery to generate summary. Returns summary text or None."""
    from social_hook.config.project import load_project_config
    from social_hook.db import operations as ops
    from social_hook.llm.dry_run import DryRunContext

    # Check if summary already exists
    existing = ops.get_project(conn, project.id)
    if existing and existing.summary:
        if not is_json:
            typer.echo(f"Project summary exists ({len(existing.summary)} chars)")
        return existing.summary

    from social_hook.cli._spinner import spinner

    project_config = load_project_config(repo_path)
    db = DryRunContext(conn, dry_run=dry_run)

    try:
        from social_hook.llm.discovery import discover_project
        from social_hook.llm.factory import create_client

        client = create_client(config.models.evaluator, config, verbose=verbose)
        with spinner("Discovering project...", quiet=is_json):
            summary, selected_files, file_summaries, prompt_docs = discover_project(
                client=client,
                repo_path=repo_path,
                project_docs=project_config.context.project_docs,
                max_discovery_tokens=project_config.context.max_discovery_tokens,
                max_file_size=project_config.context.max_file_size,
                db=db,
                project_id=project.id,
            )

        if summary and not dry_run:
            ops.update_project_summary(conn, project.id, summary)
            ops.update_discovery_files(conn, project.id, selected_files)
            if file_summaries:
                ops.upsert_file_summaries(conn, project.id, file_summaries)
            if prompt_docs:
                ops.update_prompt_docs(conn, project.id, prompt_docs)

        if not is_json:
            if summary:
                typer.echo(
                    f"  Discovery complete: {len(selected_files)} files, {len(summary)} char summary"
                )
            else:
                typer.echo("  Discovery produced no summary")

        return summary

    except Exception as e:
        if not is_json:
            typer.echo(f"  Discovery failed (non-fatal): {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        return None


def _run_summary_draft(
    config: Any,
    conn: Any,
    project: Any,
    summary: str,
    repo_path: str,
    verbose: bool,
    is_json: bool,
) -> dict[str, Any] | None:
    """Generate a summary-based first draft. Returns draft info dict or None."""
    from social_hook.cli._spinner import spinner
    from social_hook.llm.dry_run import DryRunContext

    db = DryRunContext(conn, dry_run=False)

    try:
        from social_hook.trigger import run_summary_trigger

        with spinner("Generating first draft...", quiet=is_json):
            draft_result = run_summary_trigger(
                config=config,
                conn=conn,
                db=db,
                project=project,
                summary=summary,
                repo_path=repo_path,
                verbose=verbose,
            )
        return draft_result

    except Exception as e:
        if not is_json:
            typer.echo(f"  Draft generation failed: {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        return None


def _run_batch_evaluate(
    config: Any,
    conn: Any,
    project: Any,
    repo_path: str,
    count: int,
    dry_run: bool,
    verbose: bool,
    is_json: bool,
) -> list[dict[str, Any]]:
    """Batch evaluate recent un-evaluated commits. Returns list of results."""
    if not is_json:
        typer.echo(f"Batch evaluating last {count} commits...")

    # Find imported/deferred_eval decisions (unevaluated commits)
    rows = conn.execute(
        """
        SELECT commit_hash FROM decisions
        WHERE project_id = ? AND decision IN ('imported', 'deferred_eval')
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (project.id, count),
    ).fetchall()

    unevaluated_hashes = [row["commit_hash"] for row in rows]

    if not unevaluated_hashes:
        if not is_json:
            typer.echo("  No unevaluated commits found")
        return []

    if not is_json:
        typer.echo(f"  Found {len(unevaluated_hashes)} unevaluated commit(s)")

    results: list[dict[str, Any]] = []
    from social_hook.cli._spinner import spinner
    from social_hook.trigger import run_trigger

    for commit_hash in unevaluated_hashes:
        try:
            with spinner(f"Evaluating commit {commit_hash[:8]}...", quiet=is_json):
                exit_code = run_trigger(
                    commit_hash=commit_hash,
                    repo_path=repo_path,
                    dry_run=dry_run,
                    verbose=verbose,
                    trigger_source="manual",
                )
            results.append(
                {
                    "commit_hash": commit_hash,
                    "exit_code": exit_code,
                    "status": "ok" if exit_code == 0 else "error",
                }
            )
        except Exception as e:
            results.append(
                {
                    "commit_hash": commit_hash,
                    "exit_code": 2,
                    "status": "error",
                    "error": str(e),
                }
            )

    if not is_json:
        ok_count = sum(1 for r in results if r["status"] == "ok")
        typer.echo(f"  Evaluated {ok_count}/{len(results)} commits")

    return results
