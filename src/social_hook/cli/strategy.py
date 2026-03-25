"""CLI commands for content strategy management."""

import json as json_mod
import logging

import typer

from social_hook.cli.utils import resolve_project
from social_hook.filesystem import get_config_path

app = typer.Typer(no_args_is_help=True)
logger = logging.getLogger(__name__)


def _get_conn():
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


def _resolve_proj(conn, project_path: str | None):
    """Resolve project from --project or cwd. Returns project or exits."""
    from social_hook.db import operations as ops

    repo_path = resolve_project(project_path)
    proj = ops.get_project_by_path(conn, repo_path)
    if not proj:
        typer.echo(f"No registered project at {repo_path}", err=True)
        raise typer.Exit(1)
    return proj


def _get_merged_strategies(repo_path: str) -> list[dict]:
    """Get built-in templates merged with project overrides."""
    from social_hook.config.project import load_project_config
    from social_hook.setup.templates import STRATEGY_TEMPLATES

    project_config = load_project_config(repo_path)
    overrides = project_config.content_config.get("strategies", {})

    result = []
    seen = set()

    # Built-in templates (merged with project overrides)
    for t in STRATEGY_TEMPLATES:
        if t.id == "custom":
            continue  # Skip the custom template placeholder
        entry = {
            "name": t.id,
            "label": t.name,
            "description": t.description,
            "template": True,
            "audience": t.defaults.audience,
            "voice": t.defaults.voice_tone,
            "angle": "",
            "post_when": t.defaults.post_when,
            "avoid": t.defaults.avoid,
            "format_preference": "",
            "media_preference": "",
        }
        # Apply project overrides
        if t.id in overrides:
            for key, value in overrides[t.id].items():
                if key in entry:
                    entry[key] = value
            entry["customized"] = True
        else:
            entry["customized"] = False

        result.append(entry)
        seen.add(t.id)

    # Project-only strategies (not built-in)
    for name, fields in overrides.items():
        if name not in seen:
            entry = {
                "name": name,
                "label": name,
                "description": fields.get("description", ""),
                "template": False,
                "customized": False,
                "audience": fields.get("audience", ""),
                "voice": fields.get("voice", ""),
                "angle": fields.get("angle", ""),
                "post_when": fields.get("post_when", ""),
                "avoid": fields.get("avoid", ""),
                "format_preference": fields.get("format_preference", ""),
                "media_preference": fields.get("media_preference", ""),
            }
            result.append(entry)

    return result


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List strategies: built-in templates + project overrides.

    Shows all content strategies available for the project, including
    built-in templates (building-public, product-news, etc.) merged
    with any project-level customizations.

    Example: social-hook strategy list
    """
    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        strategies = _get_merged_strategies(proj.repo_path)

        if json_output:
            typer.echo(json_mod.dumps({"strategies": strategies}, indent=2))
            return

        if not strategies:
            typer.echo("No strategies found.")
            return

        typer.echo(f"{'Name':<25} {'Type':<12} {'Audience'}")
        typer.echo("-" * 65)
        for s in strategies:
            type_label = "template" if s["template"] else "custom"
            if s.get("customized"):
                type_label += "*"
            audience = (s.get("audience") or "")[:30]
            typer.echo(f"{s['name']:<25} {type_label:<12} {audience}")
    finally:
        conn.close()


@app.command()
def show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Strategy name"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show full strategy definition (merges template + project override).

    Example: social-hook strategy show building-public
    """
    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        strategies = _get_merged_strategies(proj.repo_path)

        found = None
        for s in strategies:
            if s["name"] == name:
                found = s
                break

        if not found:
            available = ", ".join(s["name"] for s in strategies)
            msg = f"Strategy not found: {name}. Available: {available}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if json_output:
            typer.echo(json_mod.dumps(found, indent=2))
            return

        typer.echo(f"Strategy: {found['name']}")
        if found.get("label") and found["label"] != found["name"]:
            typer.echo(f"  Label:       {found['label']}")
        if found.get("description"):
            typer.echo(f"  Description: {found['description']}")
        typer.echo(f"  Type:        {'built-in template' if found['template'] else 'custom'}")
        if found.get("customized"):
            typer.echo("  Customized:  yes")
        for field in [
            "audience",
            "voice",
            "angle",
            "post_when",
            "avoid",
            "format_preference",
            "media_preference",
        ]:
            value = found.get(field, "")
            if value:
                label = field.replace("_", " ").title()
                typer.echo(f"  {label + ':':<17} {value}")
    finally:
        conn.close()


@app.command()
def edit(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Strategy name to edit"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Edit a strategy's fields in $EDITOR.

    Extracts the strategy's editable fields (audience, voice, angle,
    post_when, avoid, format_preference, media_preference) into a
    temporary YAML file, opens in $EDITOR, then writes changes back
    to the project's content-config.yaml.

    Example: social-hook strategy edit building-public
    """
    import os
    import subprocess
    import tempfile

    import yaml

    from social_hook.constants import CONFIG_DIR_NAME

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        strategies = _get_merged_strategies(proj.repo_path)

        found = None
        for s in strategies:
            if s["name"] == name:
                found = s
                break

        if not found:
            msg = f"Strategy not found: {name}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        # Find editor: VISUAL -> EDITOR -> vi
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"

        # Extract editable fields
        editable_fields = [
            "audience",
            "voice",
            "angle",
            "post_when",
            "avoid",
            "format_preference",
            "media_preference",
        ]
        edit_data = {f: found.get(f, "") for f in editable_fields}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", prefix=f"strategy-{name}-", delete=False
        ) as tmp:
            yaml.dump(edit_data, tmp, default_flow_style=False, allow_unicode=True)
            tmp_path = tmp.name

        try:
            result = subprocess.run([editor, tmp_path])
            if result.returncode != 0:
                msg = f"Editor exited with code {result.returncode}"
                if json_output:
                    typer.echo(json_mod.dumps({"error": msg}))
                else:
                    typer.echo(msg)
                raise typer.Exit(1)

            # Read back
            with open(tmp_path, encoding="utf-8") as f:
                new_data = yaml.safe_load(f) or {}

            # Check if unchanged
            if new_data == edit_data:
                typer.echo("No changes.")
                return
        finally:
            os.unlink(tmp_path)

        # Write back to content-config.yaml
        from pathlib import Path

        config_path = Path(proj.repo_path) / CONFIG_DIR_NAME / "content-config.yaml"
        if config_path.exists():
            config_content = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        else:
            config_content = {}

        strategies_section = config_content.setdefault("strategies", {})
        strategies_section[name] = {k: v for k, v in new_data.items() if v}

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.dump(config_content, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        if json_output:
            typer.echo(
                json_mod.dumps({"edited": True, "strategy": name, "fields": new_data}, indent=2)
            )
        else:
            typer.echo(f"Strategy '{name}' updated.")
    finally:
        conn.close()


@app.command()
def add(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Strategy name"),
    template: str | None = typer.Option(
        None, "--template", "-t", help="Built-in template ID to base on"
    ),
    audience: str | None = typer.Option(None, "--audience", help="Target audience"),
    voice: str | None = typer.Option(None, "--voice", help="Voice/tone"),
    angle: str | None = typer.Option(None, "--angle", help="Content angle"),
    post_when: str | None = typer.Option(None, "--post-when", help="When to post"),
    avoid: str | None = typer.Option(None, "--avoid", help="What to avoid"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create a new custom content strategy.

    Creates a strategy in the project's config. Optionally base it on a
    built-in template to inherit defaults, then override specific fields.

    Example: social-hook strategy add --name dev-community --audience "open-source developers" --voice casual
    """
    from social_hook.config.yaml import save_config

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)
        strategies = _get_merged_strategies(proj.repo_path)

        # Check for duplicate
        for s in strategies:
            if s["name"] == name:
                msg = f"Strategy '{name}' already exists"
                if json_output:
                    typer.echo(json_mod.dumps({"error": msg}))
                else:
                    typer.echo(msg)
                raise typer.Exit(1)

        fields: dict[str, str] = {}

        # If template, copy its defaults
        if template:
            found_template = None
            for s in strategies:
                if s["name"] == template and s.get("template"):
                    found_template = s
                    break
            if not found_template:
                msg = f"Template not found: {template}"
                if json_output:
                    typer.echo(json_mod.dumps({"error": msg}))
                else:
                    typer.echo(msg)
                raise typer.Exit(1)
            for field in ("audience", "voice", "angle", "post_when", "avoid"):
                if found_template.get(field):
                    fields[field] = found_template[field]

        # Override with explicit flags
        if audience is not None:
            fields["audience"] = audience
        if voice is not None:
            fields["voice"] = voice
        if angle is not None:
            fields["angle"] = angle
        if post_when is not None:
            fields["post_when"] = post_when
        if avoid is not None:
            fields["avoid"] = avoid

        save_config(
            {"content_strategies": {name: fields}},
            config_path=get_config_path(),
            deep_merge=True,
        )

        if json_output:
            typer.echo(
                json_mod.dumps({"created": True, "strategy": name, "fields": fields}, indent=2)
            )
        else:
            typer.echo(f"Strategy '{name}' created.")
    finally:
        conn.close()


@app.command()
def delete(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Strategy name to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Delete a custom strategy from the project config.

    Fails if any targets reference the strategy (409 Conflict).
    Built-in template strategies cannot be deleted — use 'reset' instead.

    Example: social-hook strategy delete dev-community --yes
    """

    from social_hook.constants import CONFIG_DIR_NAME

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        # Check strategy exists
        strategies = _get_merged_strategies(proj.repo_path)
        found = None
        for s in strategies:
            if s["name"] == name:
                found = s
                break

        if not found:
            msg = f"Strategy not found: {name}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        # Check if any targets reference this strategy
        from social_hook.config.yaml import load_full_config

        config = load_full_config()
        referencing = [tgt_name for tgt_name, tgt in config.targets.items() if tgt.strategy == name]
        if referencing:
            msg = f"Cannot delete strategy '{name}': referenced by targets {referencing}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if not yes and not typer.confirm(f"Delete strategy '{name}'?"):
            typer.echo("Cancelled.")
            return

        from pathlib import Path

        from social_hook.config.yaml import delete_config_key

        config_path = Path(proj.repo_path) / CONFIG_DIR_NAME / "content-config.yaml"
        delete_config_key(config_path, "content_strategies", name)

        if json_output:
            typer.echo(json_mod.dumps({"deleted": True, "strategy": name}, indent=2))
        else:
            typer.echo(f"Strategy '{name}' deleted.")
    finally:
        conn.close()


@app.command()
def reset(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Strategy name to reset"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    project_path: str | None = typer.Option(
        None, "--project", "-p", help="Repository path (default: cwd)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Reset a strategy to built-in template defaults.

    Removes the project-level override for the named strategy,
    restoring it to its built-in template values.

    Example: social-hook strategy reset building-public --yes
    """
    import yaml

    from social_hook.constants import CONFIG_DIR_NAME
    from social_hook.setup.templates import get_template_defaults

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    defaults = get_template_defaults(name)
    if defaults is None:
        msg = f"Strategy '{name}' is not a built-in template. Cannot reset."
        if json_output:
            typer.echo(json_mod.dumps({"error": msg}))
        else:
            typer.echo(msg)
        raise typer.Exit(1)

    conn = _get_conn()
    try:
        proj = _resolve_proj(conn, project_path)

        if not yes and not typer.confirm(f"Reset strategy '{name}' to built-in template defaults?"):
            typer.echo("Cancelled.")
            return

        from pathlib import Path

        config_path = Path(proj.repo_path) / CONFIG_DIR_NAME / "content-config.yaml"
        if config_path.exists():
            config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        else:
            config_data = {}

        strategies = config_data.get("strategies", {})
        if name in strategies:
            del strategies[name]
            config_data["strategies"] = strategies
            config_path.write_text(
                yaml.dump(config_data, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )

        if json_output:
            typer.echo(json_mod.dumps({"reset": True, "strategy": name}, indent=2))
        else:
            typer.echo(f"Strategy '{name}' reset to template defaults.")
    finally:
        conn.close()
