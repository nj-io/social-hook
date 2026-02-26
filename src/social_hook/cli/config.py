"""CLI commands for configuration management."""

from typing import Optional

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
    result = {}
    current = result
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


@app.command()
def show():
    """Show the full configuration as YAML."""
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
def get_key(key: str = typer.Argument(help="Dotted key path (e.g. platforms.x.account_tier)")):
    """Get a single configuration value by dotted key path."""
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
        raise typer.Exit(1)

    if isinstance(value, (dict, list)):
        typer.echo(yaml.dump(value, default_flow_style=False, sort_keys=False).rstrip())
    else:
        typer.echo(value)


@app.command("set")
def set_key(
    key: str = typer.Argument(help="Dotted key path (e.g. platforms.x.account_tier)"),
    value: str = typer.Argument(help="Value to set (scalars only; use web UI for lists/arrays)"),
):
    """Set a configuration value by dotted key path.

    Only scalar values (strings, numbers, booleans) are supported.
    For lists/arrays, edit the YAML directly or use the web UI.
    """
    from social_hook.errors import ConfigError
    from social_hook.filesystem import get_config_path
    from social_hook.config.yaml import save_config

    parsed = _parse_value(value)
    updates = _build_nested(key, parsed)

    try:
        save_config(updates, config_path=get_config_path(), deep_merge=True)
    except ConfigError as e:
        typer.echo(f"Validation error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Set {key} = {parsed}")
