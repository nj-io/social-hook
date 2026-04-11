"""CLI commands for Development Journey capture."""

import shutil

import typer
import yaml

from social_hook.filesystem import get_config_path, get_narratives_path

app = typer.Typer()


@app.command("on")
def journey_on():
    """Enable Development Journey capture.

    Installs a Claude Code session hook that records development
    narratives (reasoning, decisions, context) to JSONL files.
    These narratives enrich the LLM's understanding of your work.
    Restart any running Claude Code sessions for the hook to take effect.

    Example: social-hook journey on
    """
    from social_hook.setup.install import install_narrative_hook

    config_path = get_config_path()
    data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    data.setdefault("journey_capture", {})["enabled"] = True
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(data, default_flow_style=False))

    success, msg = install_narrative_hook()
    if not success:
        typer.echo(f"Warning: Could not install narrative hook: {msg}")
    else:
        typer.echo(f"Claude Code narrative hook: {msg}")

    typer.echo("Development Journey capture enabled.")
    typer.echo("Restart Claude Code sessions for the hook to take effect.")


@app.command("off")
def journey_off():
    """Disable Development Journey capture.

    Removes the Claude Code session hook and stops recording
    narratives. Existing narrative files are preserved.

    Example: social-hook journey off
    """
    from social_hook.setup.install import uninstall_narrative_hook

    config_path = get_config_path()
    data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    data.setdefault("journey_capture", {})["enabled"] = False
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(data, default_flow_style=False))

    success, msg = uninstall_narrative_hook()
    if not success:
        typer.echo(f"Warning: Could not uninstall narrative hook: {msg}")
    else:
        typer.echo(f"Claude Code narrative hook: {msg}")

    typer.echo("Development Journey capture disabled.")


@app.command("status")
def journey_status():
    """Show Development Journey status.

    Displays: whether capture is enabled, hook installation state,
    Claude CLI detection, and number of narrative files recorded.

    Example: social-hook journey status
    """
    from social_hook.config.yaml import load_full_config
    from social_hook.setup.install import check_narrative_hook_installed

    config = load_full_config()

    enabled = config.journey_capture.enabled
    hook_installed = check_narrative_hook_installed()
    claude_detected = shutil.which("claude") is not None

    typer.echo(f"  Enabled:        {'yes' if enabled else 'no'}")
    typer.echo(f"  Hook installed: {'yes' if hook_installed else 'no'}")
    typer.echo(f"  Claude CLI:     {'detected' if claude_detected else 'not found'}")

    # Count narratives
    narratives_dir = get_narratives_path()
    count = 0
    if narratives_dir.exists():
        count = len(list(narratives_dir.glob("*.jsonl")))
    typer.echo(f"  Narrative files: {count}")
