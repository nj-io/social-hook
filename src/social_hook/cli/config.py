"""CLI commands for configuration management."""

from pathlib import Path
from typing import Any

import typer
import yaml

app = typer.Typer(no_args_is_help=True)


def _parse_value(value: str):
    """Parse a string value into its most appropriate Python type."""
    lower = value.lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _build_nested(dotted_key: str, value) -> dict:
    """Build a nested dict from a dotted key path.

    Example: 'platforms.x.account_tier', 'premium' -> {'platforms': {'x': {'account_tier': 'premium'}}}
    """
    parts = dotted_key.split(".")
    result: dict[str, Any] = {}
    current: dict[str, Any] = result
    for part in parts[:-1]:
        current[part] = {}
        current = current[part]
    current[parts[-1]] = value
    return result


def _traverse(data: dict, dotted_key: str):
    """Traverse a dict with a dotted key path. Raises KeyError if not found."""
    parts = dotted_key.split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted_key)
        current = current[part]
    return current


def _resolve_content_config_path(project_path: str | None = None) -> Path:
    """Resolve content-config.yaml: {project}/.social-hook/ -> ~/.social-hook/ fallback."""
    from social_hook.constants import CONFIG_DIR_NAME

    if project_path:
        project_cfg = Path(project_path) / CONFIG_DIR_NAME / "content-config.yaml"
        if project_cfg.exists():
            return project_cfg
    global_cfg = Path.home() / CONFIG_DIR_NAME / "content-config.yaml"
    return global_cfg


def _deep_merge(base: dict, updates: dict) -> dict:
    """Recursively merge updates into base dict."""
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _get_content_config_with_defaults(overrides: dict) -> dict:
    """Build full content-config dict with all defaults, then merge overrides on top."""
    from dataclasses import asdict

    from social_hook.config.project import ContextConfig, StrategyConfig, SummaryConfig

    defaults: dict[str, Any] = {
        "context": asdict(ContextConfig()),
        "strategy": asdict(StrategyConfig()),
        "summary": asdict(SummaryConfig()),
    }
    return _deep_merge(defaults, overrides)


@app.command()
def show(
    content: bool = typer.Option(False, "--content", help="Show content-config.yaml instead of config.yaml. Example: social-hook config show --content"),
    project_path: str = typer.Option(None, "--project", "-p", help="Project path for project-specific config"),
):
    """Show the full configuration as YAML."""
    if content:
        config_path = _resolve_content_config_path(project_path)
        if config_path.exists():
            try:
                overrides = yaml.safe_load(config_path.read_text()) or {}
            except yaml.YAMLError:
                overrides = {}
        else:
            overrides = {}
        data = _get_content_config_with_defaults(overrides)
        typer.echo(yaml.dump(data, default_flow_style=False, sort_keys=False).rstrip())
        return

    from social_hook.filesystem import get_config_path

    config_path = get_config_path()
    if config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text()) or {}
        except yaml.YAMLError:
            data = {}
    else:
        from social_hook.config.yaml import DEFAULT_CONFIG

        data = DEFAULT_CONFIG.copy()

    typer.echo(yaml.dump(data, default_flow_style=False, sort_keys=False).rstrip())


@app.command("get")
def get_key(
    key: str = typer.Argument(help="Dotted key path (e.g. context.max_discovery_tokens)"),
    content: bool = typer.Option(False, "--content", help="Read from content-config.yaml. Example: social-hook config get context.max_discovery_tokens --content"),
    project_path: str = typer.Option(None, "--project", "-p", help="Project path"),
):
    """Get a single configuration value by dotted key path."""
    if content:
        config_path = _resolve_content_config_path(project_path)
        if config_path.exists():
            try:
                overrides = yaml.safe_load(config_path.read_text()) or {}
            except yaml.YAMLError:
                overrides = {}
        else:
            overrides = {}
        data = _get_content_config_with_defaults(overrides)
    else:
        from social_hook.filesystem import get_config_path

        config_path = get_config_path()
        if config_path.exists():
            try:
                data = yaml.safe_load(config_path.read_text()) or {}
            except yaml.YAMLError:
                data = {}
        else:
            from social_hook.config.yaml import DEFAULT_CONFIG

            data = DEFAULT_CONFIG.copy()

    try:
        value = _traverse(data, key)
    except KeyError:
        typer.echo(f"Key not found: {key}", err=True)
        raise typer.Exit(1) from None

    if isinstance(value, (dict, list)):
        typer.echo(yaml.dump(value, default_flow_style=False, sort_keys=False).rstrip())
    else:
        typer.echo(value)


@app.command("set")
def set_key(
    key: str = typer.Argument(help="Dotted key path (e.g. context.max_discovery_tokens)"),
    value: str = typer.Argument(help="Value to set (scalars only)"),
    content: bool = typer.Option(False, "--content", help="Write to content-config.yaml. Example: social-hook config set context.max_discovery_tokens 80000 --content"),
    project_path: str = typer.Option(None, "--project", "-p", help="Project path"),
):
    """Set a configuration value by dotted key path."""
    parsed = _parse_value(value)

    if content:
        config_path = _resolve_content_config_path(project_path)
        if config_path.exists():
            try:
                data = yaml.safe_load(config_path.read_text()) or {}
            except yaml.YAMLError:
                data = {}
        else:
            data = {}
        updates = _build_nested(key, parsed)
        _deep_merge(data, updates)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        typer.echo(f"Set {key} = {parsed}")
        return

    from social_hook.config.yaml import save_config
    from social_hook.errors import ConfigError
    from social_hook.filesystem import get_config_path

    updates = _build_nested(key, parsed)

    try:
        save_config(updates, config_path=get_config_path(), deep_merge=True)
    except ConfigError as e:
        typer.echo(f"Validation error: {e}", err=True)
        raise typer.Exit(1) from None

    typer.echo(f"Set {key} = {parsed}")
