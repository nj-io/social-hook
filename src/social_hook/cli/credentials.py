"""CLI commands for platform credential management."""

import json as json_mod
import logging

import typer

app = typer.Typer(no_args_is_help=True)
logger = logging.getLogger(__name__)


def _get_conn():
    from social_hook.db.connection import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List platform credential entries.

    Shows configured platform credentials (X, LinkedIn, etc.) and their status.

    Example: social-hook credentials list
    """
    from social_hook.config.env import load_env

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    try:
        env_vars = load_env()
    except Exception as e:
        if json_output:
            typer.echo(json_mod.dumps({"error": str(e)}))
        else:
            typer.echo(f"Error loading credentials: {e}", err=True)
        raise typer.Exit(1) from None

    # Group credentials by platform
    platforms = {
        "x": {
            "keys": ["X_CLIENT_ID", "X_CLIENT_SECRET"],
            "label": "X (Twitter)",
        },
        "linkedin": {
            "keys": ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_ACCESS_TOKEN"],
            "label": "LinkedIn",
        },
        "telegram": {
            "keys": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS"],
            "label": "Telegram",
        },
    }

    entries = []
    for platform_id, info in platforms.items():
        configured_keys = [k for k in info["keys"] if env_vars.get(k)]
        total_keys = len(info["keys"])
        status = (
            "configured"
            if len(configured_keys) == total_keys
            else ("partial" if configured_keys else "not_configured")
        )
        entries.append(
            {
                "platform": platform_id,
                "label": info["label"],
                "status": status,
                "configured_keys": len(configured_keys),
                "total_keys": total_keys,
            }
        )

    if json_output:
        typer.echo(json_mod.dumps({"credentials": entries}, indent=2))
        return

    if not entries:
        typer.echo("No platform credentials found.")
        return

    typer.echo(f"{'Platform':<15} {'Status':<16} {'Keys'}")
    typer.echo("-" * 45)
    for entry in entries:
        typer.echo(
            f"{entry['label']:<15} {entry['status']:<16} {entry['configured_keys']}/{entry['total_keys']}"
        )


@app.command()
def add(
    ctx: typer.Context,
    platform: str = typer.Option(..., "--platform", help="Platform name (x, linkedin, telegram)"),
    name: str = typer.Option(
        None, "--name", "-n", help="Credential entry name (default: platform name)"
    ),
    set_values: list[str] = typer.Option(
        [],
        "--set",
        help="Set a key non-interactively (KEY=VALUE). Repeat for multiple keys.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Add or update a platform credential entry.

    Prompts for the required API keys for the specified platform.
    Static app credentials are stored in the .env file.
    Use --set to bypass prompts for agent/CI use.

    Example: social-hook credentials add --platform x --name x-main
    Example: social-hook credentials add --platform x --set X_CLIENT_ID=abc --set X_CLIENT_SECRET=xyz
    """
    from social_hook.config.env import load_env
    from social_hook.filesystem import get_env_path

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)
    name = name or platform

    platform_keys = {
        "x": ["X_CLIENT_ID", "X_CLIENT_SECRET"],
        "linkedin": ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"],
        "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS"],
    }

    if platform not in platform_keys:
        valid = ", ".join(sorted(platform_keys.keys()))
        if json_output:
            typer.echo(json_mod.dumps({"error": f"Unknown platform: {platform}. Valid: {valid}"}))
        else:
            typer.echo(f"Unknown platform: {platform}. Valid platforms: {valid}")
        raise typer.Exit(1)

    keys = platform_keys[platform]
    env_path = get_env_path()

    # Parse --set values
    set_map: dict[str, str] = {}
    for item in set_values:
        if "=" not in item:
            msg = f"Invalid --set format: {item!r}. Use KEY=VALUE."
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)
        k, v = item.split("=", 1)
        if k not in keys:
            valid = ", ".join(keys)
            msg = f"Unknown key {k!r} for {platform}. Valid: {valid}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)
        set_map[k] = v

    # Load existing env
    try:
        existing = load_env()
    except Exception:
        existing = {}

    # Use --set values if provided, otherwise prompt interactively
    new_values = {}
    if set_map:
        new_values = set_map
    else:
        for key in keys:
            current = existing.get(key, "")
            masked = (
                f"{'*' * (len(current) - 4)}{current[-4:]}" if len(current) > 4 else "(not set)"
            )
            value = typer.prompt(f"{key} [{masked}]", default="", show_default=False)
            if value:
                new_values[key] = value

    if not new_values:
        typer.echo("No changes made.")
        return

    # Write to .env file
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_content = env_path.read_text() if env_path.exists() else ""
    for key, value in new_values.items():
        import re

        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, env_content, re.MULTILINE):
            env_content = re.sub(pattern, replacement, env_content, flags=re.MULTILINE)
        else:
            env_content = env_content.rstrip() + f"\n{replacement}\n"
    env_path.write_text(env_content)

    if json_output:
        typer.echo(
            json_mod.dumps(
                {
                    "added": True,
                    "platform": platform,
                    "name": name,
                    "keys_updated": list(new_values.keys()),
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"Updated {len(new_values)} key(s) for {platform}.")


@app.command()
def validate(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Validate all platform credential entries.

    Checks that required API keys are present and non-empty.

    Example: social-hook credentials validate
    """
    from social_hook.config.env import load_env

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    try:
        env_vars = load_env()
    except Exception as e:
        if json_output:
            typer.echo(json_mod.dumps({"error": str(e)}))
        else:
            typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None

    platform_keys = {
        "x": ["X_CLIENT_ID", "X_CLIENT_SECRET"],
        "linkedin": ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"],
        "telegram": ["TELEGRAM_BOT_TOKEN"],
    }

    results = []
    all_valid = True
    for platform, keys in platform_keys.items():
        missing = [k for k in keys if not env_vars.get(k)]
        valid = len(missing) == 0
        if not valid:
            all_valid = False
        results.append(
            {
                "platform": platform,
                "valid": valid,
                "missing_keys": missing,
            }
        )

    if json_output:
        typer.echo(json_mod.dumps({"valid": all_valid, "platforms": results}, indent=2))
    else:
        for platform, keys in platform_keys.items():
            missing = [k for k in keys if not env_vars.get(k)]
            status = "valid" if not missing else f"missing: {', '.join(missing)}"
            typer.echo(f"  {platform:<12} {status}")
        if all_valid:
            typer.echo("\nAll credentials valid.")
        else:
            typer.echo("\nSome credentials are missing.")


@app.command()
def remove(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Credential entry name (platform name)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Remove a platform credential entry.

    Removes API keys for the specified platform from the .env file.
    Fails if accounts reference this credential.

    Example: social-hook credentials remove x --yes
    """
    from social_hook.filesystem import get_env_path

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    platform_keys = {
        "x": ["X_CLIENT_ID", "X_CLIENT_SECRET"],
        "linkedin": ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_ACCESS_TOKEN"],
        "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS"],
    }

    if name not in platform_keys:
        valid = ", ".join(sorted(platform_keys.keys()))
        if json_output:
            typer.echo(json_mod.dumps({"error": f"Unknown credential: {name}. Valid: {valid}"}))
        else:
            typer.echo(f"Unknown credential: {name}. Valid: {valid}")
        raise typer.Exit(1)

    # Check if accounts reference this credential
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT account_name FROM oauth_tokens WHERE platform = ?", (name,)
        ).fetchall()
        if rows:
            account_names = [r["account_name"] for r in rows]
            msg = f"Cannot remove: accounts reference this credential: {', '.join(account_names)}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg, "accounts": account_names}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)
    finally:
        conn.close()

    if not yes and not typer.confirm(f"Remove all credentials for {name}?"):
        typer.echo("Cancelled.")
        return

    env_path = get_env_path()
    if not env_path.exists():
        typer.echo("No .env file found.")
        return

    import re

    keys = platform_keys[name]
    content = env_path.read_text()
    removed = 0
    for key in keys:
        new_content = re.sub(rf"^{re.escape(key)}=.*\n?", "", content, flags=re.MULTILINE)
        if new_content != content:
            removed += 1
            content = new_content
    env_path.write_text(content)

    if json_output:
        typer.echo(
            json_mod.dumps(
                {
                    "removed": True,
                    "name": name,
                    "keys_removed": removed,
                },
                indent=2,
            )
        )
    else:
        typer.echo(f"Removed {removed} key(s) for {name}.")
