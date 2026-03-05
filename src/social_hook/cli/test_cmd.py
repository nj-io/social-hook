"""CLI test command for dry-run evaluation of commits."""

import json as json_mod
import subprocess
from pathlib import Path

import typer

app = typer.Typer(invoke_without_command=True)


@app.callback()
def test_commits(
    ctx: typer.Context,
    repo: str = typer.Option(..., "--repo", help="Repository path"),
    commit: str | None = typer.Option(None, "--commit", help="Single commit hash"),
    last: int = typer.Option(0, "--last", help="Test N most recent commits"),
    from_hash: str | None = typer.Option(None, "--from", help="Start of commit range"),
    to_hash: str | None = typer.Option(None, "--to", help="End of commit range"),
    compare: Path | None = typer.Option(
        None, "--compare", help="Compare results to golden JSON file"
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Save results to JSON file"),
    show_prompt: bool = typer.Option(
        False, "--show-prompt", help="Print the full LLM prompt to stderr"
    ),
):
    """Test commit evaluation with real LLM calls, no DB writes."""
    from social_hook.trigger import run_trigger

    commits = []

    if commit:
        commits.append(commit)
    elif from_hash and to_hash:
        result = subprocess.run(
            ["git", "-C", repo, "log", "--format=%H", f"{from_hash}..{to_hash}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(f"Error reading git log: {result.stderr}")
            raise typer.Exit(1)
        commits = [h.strip() for h in result.stdout.strip().splitlines() if h.strip()]
        if not commits:
            typer.echo(f"No commits found in range {from_hash[:8]}..{to_hash[:8]}")
            raise typer.Exit(1)
    elif last > 0:
        result = subprocess.run(
            ["git", "-C", repo, "log", f"-{last}", "--format=%H"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(f"Error reading git log: {result.stderr}")
            raise typer.Exit(1)
        commits = [h.strip() for h in result.stdout.strip().splitlines() if h.strip()]
    else:
        typer.echo("Specify --commit, --last N, or --from/--to range")
        raise typer.Exit(1)

    config_path = ctx.obj.get("config") if ctx.obj else None
    verbose = ctx.obj.get("verbose", False) if ctx.obj else False
    repo = str(Path(repo).resolve())

    results = []
    for c in commits:
        typer.echo(f"Testing {c[:8]}...")
        exit_code = run_trigger(
            commit_hash=c,
            repo_path=repo,
            dry_run=True,
            config_path=str(config_path) if config_path else None,
            verbose=verbose,
            show_prompt=show_prompt,
        )
        results.append({"commit": c, "exit_code": exit_code})
        typer.echo(f"  Exit code: {exit_code}")

    if output:
        output.write_text(json_mod.dumps(results, indent=2))
        typer.echo(f"\nResults saved to {output}")

    if compare:
        _compare_results(results, compare)

    typer.echo(f"\nTested {len(results)} commit(s)")


def _compare_results(results: list[dict], golden_path: Path) -> None:
    """Compare results against a golden file and show diffs."""
    if not golden_path.exists():
        typer.echo(f"\nGolden file not found: {golden_path}")
        return

    golden = json_mod.loads(golden_path.read_text())
    golden_map = {r["commit"]: r["exit_code"] for r in golden}

    diffs = []
    for r in results:
        expected = golden_map.get(r["commit"])
        if expected is not None and expected != r["exit_code"]:
            diffs.append(f"  {r['commit'][:8]}: expected={expected}, got={r['exit_code']}")

    if diffs:
        typer.echo(f"\nDifferences from {golden_path.name}:")
        for d in diffs:
            typer.echo(d)
    else:
        typer.echo(f"\nAll results match {golden_path.name}")
