"""Interactive setup wizard for social-hook."""

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

import typer

logger = logging.getLogger(__name__)

# Common timezones for selector
COMMON_TIMEZONES = [
    "US/Eastern",
    "US/Central",
    "US/Mountain",
    "US/Pacific",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Paris",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Australia/Sydney",
    "UTC",
]


def _rich_prompt(text: str, password: bool = False, validate: Optional[Callable] = None) -> str:
    """Prompt user for input with Rich/InquirerPy.

    Args:
        text: Prompt text
        password: If True, mask input
        validate: Optional validation function returning True/error string
    """
    from InquirerPy import inquirer

    def _validator(val):
        if validate:
            result = validate(val)
            if result is not True:
                return result
        return True

    if password:
        result = inquirer.secret(
            message=text,
            validate=_validator if validate else None,
        ).execute()
    else:
        result = inquirer.text(
            message=text,
            validate=_validator if validate else None,
        ).execute()
    return result


def _rich_confirm(text: str, default: bool = True) -> bool:
    """Ask yes/no confirmation with InquirerPy."""
    from InquirerPy import inquirer

    return inquirer.confirm(message=text, default=default).execute()


def _rich_select(text: str, choices: list[str], default: Optional[str] = None) -> str:
    """Select from a list with InquirerPy."""
    from InquirerPy import inquirer

    return inquirer.select(
        message=text,
        choices=choices,
        default=default,
    ).execute()


def _spinner(text: str, fn: Callable) -> Any:
    """Run a function with a Rich spinner.

    Args:
        text: Status text to display
        fn: Function to execute

    Returns:
        Function result
    """
    from rich.console import Console

    console = Console()
    with console.status(text):
        return fn()


def _validate_not_empty(val: str) -> bool | str:
    """Validate that input is not empty or trivially short."""
    stripped = val.strip()
    if not stripped:
        return "Input cannot be empty"
    if len(stripped) <= 1 and stripped.lower() in ("y", "n"):
        return "Please enter a valid value, not just 'y' or 'n'"
    return True


def _prompt(text: str, default: str = "", password: bool = False) -> str:
    """Prompt user for input — Rich/InquirerPy wrapper with fallback."""
    try:
        return _rich_prompt(text, password=password, validate=_validate_not_empty if not default else None)
    except Exception:
        # Fallback to plain input
        if password:
            import getpass
            return getpass.getpass(f"{text}: ")
        if default:
            result = input(f"{text} [{default}]: ").strip()
            return result or default
        return input(f"{text}: ").strip()


def _confirm(text: str, default: bool = True) -> bool:
    """Ask yes/no confirmation — Rich/InquirerPy wrapper with fallback."""
    try:
        return _rich_confirm(text, default=default)
    except Exception:
        suffix = " [Y/n]: " if default else " [y/N]: "
        answer = input(f"{text}{suffix}").strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes")


def _select(text: str, choices: list[str], default: Optional[str] = None) -> str:
    """Select from a list — Rich/InquirerPy wrapper with fallback."""
    try:
        return _rich_select(text, choices, default=default)
    except Exception:
        # Fallback to numbered choice
        print(f"\n{text}")
        for i, c in enumerate(choices, 1):
            marker = " (default)" if c == default else ""
            print(f"  {i}. {c}{marker}")
        while True:
            raw = input(f"Choice [1-{len(choices)}]: ").strip()
            if not raw and default:
                return default
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
            except ValueError:
                pass


def run_wizard(
    validate: bool = False,
    only: Optional[str] = None,
) -> bool:
    """Run the interactive setup wizard.

    Args:
        validate: If True, only validate existing config (no changes)
        only: If set, only configure this component (e.g., 'telegram', 'x')

    Returns:
        True if setup completed successfully
    """
    from social_hook.filesystem import get_base_path, init_filesystem

    if validate:
        return _validate_existing()

    # Welcome panel
    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        console.print(Panel(
            "[bold]Social Hook Setup[/bold]\n\n"
            "This wizard will configure social-hook for your system.\n"
            "Press Ctrl+C at any time to cancel.",
            title="Welcome",
            border_style="cyan",
        ))
    except Exception:
        typer.echo("\n=== Social Hook Setup ===\n")
        typer.echo("This wizard will configure social-hook for your system.")
        typer.echo("Press Ctrl+C at any time to cancel.\n")

    try:
        # Initialize filesystem
        base = init_filesystem()

        env_vars: dict[str, str] = {}
        yaml_config: dict[str, Any] = {}

        if only is None or only == "anthropic":
            _setup_anthropic(env_vars)

        if only is None or only == "voice":
            _setup_voice_style(base)

        if only is None or only == "telegram":
            _setup_telegram(env_vars)

        if only is None or only == "x":
            _setup_x(env_vars, yaml_config)

        if only is None or only == "linkedin":
            _setup_linkedin(env_vars)

        if only is None or only == "models":
            _setup_models(yaml_config)

        if only is None or only == "image":
            _setup_image_gen(env_vars, yaml_config)

        # Save .env file
        if env_vars:
            _save_env(base, env_vars)

        if only is None:
            _setup_scheduling(base, yaml_config)
            _save_config_yaml(base, yaml_config)
            _show_summary(env_vars, yaml_config)
            _setup_installations()

        typer.echo("\nSetup complete!")
        return True

    except KeyboardInterrupt:
        typer.echo("\n\nSetup cancelled. No changes were saved.")
        return False


def _validate_existing() -> bool:
    """Validate existing configuration."""
    from social_hook.config import load_full_config
    from social_hook.filesystem import get_base_path

    typer.echo("Validating existing configuration...\n")
    errors = []

    try:
        config = load_full_config()
    except Exception as e:
        typer.echo(f"Config error: {e}")
        return False

    base = get_base_path()
    env_file = base / ".env"
    if not env_file.exists():
        errors.append(".env file not found")

    if not config.env.get("ANTHROPIC_API_KEY"):
        errors.append("ANTHROPIC_API_KEY not set")

    if not config.env.get("TELEGRAM_BOT_TOKEN"):
        errors.append("TELEGRAM_BOT_TOKEN not set")

    if errors:
        typer.echo("Issues found:")
        for e in errors:
            typer.echo(f"  - {e}")
        return False

    typer.echo("Configuration looks good!")
    return True


def _setup_anthropic(env_vars: dict) -> None:
    """Configure Anthropic API key."""
    typer.echo("--- Anthropic API Key ---")
    key = _prompt("Enter your Anthropic API key", password=True)
    if key:
        env_vars["ANTHROPIC_API_KEY"] = key

        # Validate with spinner
        from social_hook.setup.validation import validate_anthropic_key

        success, msg = _spinner("Validating API key...", lambda: validate_anthropic_key(key))
        if success:
            typer.echo(f"  {msg}\n")
        else:
            typer.echo(f"  Warning: {msg}\n")


def _setup_voice_style(base: Path) -> None:
    """Configure voice and style (social-context.md)."""
    typer.echo("--- Voice & Style ---")
    if not _confirm("Configure voice and style now?"):
        return

    tone = _prompt("Describe your tone (e.g., 'Technical but approachable')")
    audience = _prompt("Target audience (e.g., 'Developers, tech leads')")
    topics = _prompt("Main topics (e.g., 'Python, automation, devtools')")
    pet_peeves = _prompt("Pet peeves to avoid (e.g., 'Hype language, emoji overuse')")

    context_content = f"""# Social Context

## Voice
{tone}

## Audience
{audience}

## Topics
{topics}

## Pet Peeves
{pet_peeves}
"""
    context_path = base / "social-context.md"
    context_path.write_text(context_content)
    typer.echo(f"  Voice config saved to {context_path}\n")


def _setup_telegram(env_vars: dict) -> None:
    """Configure Telegram bot."""
    typer.echo("--- Telegram Bot ---")
    if not _confirm("Set up Telegram bot?"):
        return

    token = _prompt("Bot token (from @BotFather)")
    if token:
        env_vars["TELEGRAM_BOT_TOKEN"] = token

        # Validate with spinner
        from social_hook.setup.validation import validate_telegram_bot

        success, msg = _spinner("Validating bot token...", lambda: validate_telegram_bot(token))
        if success:
            typer.echo(f"  {msg}")
        else:
            typer.echo(f"  Warning: {msg}")

        typer.echo("\nSend any message to your bot to capture your chat ID...")
        from social_hook.setup.validation import capture_telegram_chat_id

        chat_id = capture_telegram_chat_id(token, timeout_seconds=30)
        if chat_id:
            env_vars["TELEGRAM_ALLOWED_CHAT_IDS"] = chat_id
            typer.echo(f"Chat ID captured: {chat_id}\n")
        else:
            chat_id = _prompt("Chat ID (manual entry)")
            if chat_id:
                env_vars["TELEGRAM_ALLOWED_CHAT_IDS"] = chat_id


def _setup_x(env_vars: dict, yaml_config: dict) -> None:
    """Configure X (Twitter) API."""
    typer.echo("--- X (Twitter) ---")
    if not _confirm("Set up X posting?", default=False):
        return

    env_vars["X_API_KEY"] = _prompt("API Key")
    env_vars["X_API_SECRET"] = _prompt("API Secret", password=True)
    env_vars["X_ACCESS_TOKEN"] = _prompt("Access Token")
    env_vars["X_ACCESS_SECRET"] = _prompt("Access Token Secret", password=True)

    # Tier selection
    tier_choices = [
        "free (280 chars)",
        "basic (25,000 chars)",
        "premium (25,000 chars)",
        "premium_plus (25,000 chars)",
    ]
    tier_display = _select("X account tier:", tier_choices, default=tier_choices[0])
    tier_value = tier_display.split(" ")[0]  # Extract tier name

    yaml_config.setdefault("platforms", {}).setdefault("x", {})
    yaml_config["platforms"]["x"]["enabled"] = True
    yaml_config["platforms"]["x"]["account_tier"] = tier_value

    typer.echo("X credentials saved.\n")


def _setup_linkedin(env_vars: dict) -> None:
    """Configure LinkedIn API."""
    typer.echo("--- LinkedIn ---")
    if not _confirm("Set up LinkedIn posting?", default=False):
        return

    access_token = _prompt("LinkedIn access token")
    if access_token:
        env_vars["LINKEDIN_ACCESS_TOKEN"] = access_token
    typer.echo("LinkedIn credentials saved.\n")


def _setup_models(yaml_config: dict) -> None:
    """Configure LLM models."""
    typer.echo("--- Model Selection ---")
    if not _confirm("Customize models? (defaults: Opus for eval/draft, Haiku for gatekeeper)"):
        return

    model_choices = ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"]

    evaluator = _select("Evaluator model:", model_choices, default="claude-opus-4-5")
    drafter = _select("Drafter model:", model_choices, default="claude-opus-4-5")
    gatekeeper = _select("Gatekeeper model:", model_choices, default="claude-haiku-4-5")

    yaml_config["models"] = {
        "evaluator": evaluator,
        "drafter": drafter,
        "gatekeeper": gatekeeper,
    }
    typer.echo("Models configured.\n")


def _setup_image_gen(env_vars: dict, yaml_config: dict) -> None:
    """Configure image generation."""
    typer.echo("--- Image Generation ---")
    if not _confirm("Enable AI image generation?"):
        yaml_config.setdefault("image_generation", {})["enabled"] = False
        return

    service_choices = ["nano_banana_pro"]
    service = _select("Image generation service:", service_choices, default="nano_banana_pro")

    yaml_config.setdefault("image_generation", {})["enabled"] = True
    yaml_config["image_generation"]["service"] = service

    if service == "nano_banana_pro":
        api_key = _prompt("Gemini API key (for Nano Banana Pro)", password=True)
        if api_key:
            env_vars["GEMINI_API_KEY"] = api_key

            from social_hook.setup.validation import validate_image_gen

            success, msg = _spinner(
                "Validating image gen...",
                lambda: validate_image_gen(service, api_key),
            )
            if success:
                typer.echo(f"  {msg}\n")
            else:
                typer.echo(f"  Warning: {msg}\n")


def _setup_scheduling(base: Path, yaml_config: dict) -> None:
    """Configure scheduling settings."""
    typer.echo("--- Scheduling ---")

    # Detect system timezone
    try:
        import zoneinfo
        local_tz = str(zoneinfo.ZoneInfo("localtime"))
    except Exception:
        local_tz = "UTC"

    # Use selector with common timezones, system detected as default
    tz_choices = list(COMMON_TIMEZONES)
    if local_tz not in tz_choices:
        tz_choices.insert(0, local_tz)
    default_tz = local_tz if local_tz in tz_choices else "UTC"

    tz = _select("Timezone:", tz_choices, default=default_tz)
    max_posts = _prompt("Max posts per day", default="3")
    min_gap = _prompt("Min gap between posts (minutes)", default="30")

    yaml_config.setdefault("scheduling", {})
    yaml_config["scheduling"]["timezone"] = tz
    yaml_config["scheduling"]["max_posts_per_day"] = int(max_posts)
    yaml_config["scheduling"]["min_gap_minutes"] = int(min_gap)
    yaml_config["scheduling"]["optimal_days"] = ["Tue", "Wed", "Thu"]
    yaml_config["scheduling"]["optimal_hours"] = [9, 12, 17]


def _save_config_yaml(base: Path, yaml_config: dict) -> None:
    """Save YAML config if we have settings to save."""
    if not yaml_config:
        return

    import yaml

    config_path = base / "config.yaml"

    # Merge with existing if present
    existing = {}
    if config_path.exists():
        try:
            existing = yaml.safe_load(config_path.read_text()) or {}
        except Exception:
            pass

    # Deep merge
    for key, val in yaml_config.items():
        if isinstance(val, dict) and isinstance(existing.get(key), dict):
            existing[key].update(val)
        else:
            existing[key] = val

    config_path.write_text(yaml.dump(existing, default_flow_style=False))
    typer.echo(f"Config saved to {config_path}\n")


def _show_summary(env_vars: dict, yaml_config: dict) -> None:
    """Show configuration summary."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Configuration Summary")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        if "ANTHROPIC_API_KEY" in env_vars:
            table.add_row("Anthropic API Key", "***configured***")
        if "TELEGRAM_BOT_TOKEN" in env_vars:
            table.add_row("Telegram Bot", "***configured***")
        if "X_API_KEY" in env_vars:
            table.add_row("X (Twitter)", "***configured***")

        models = yaml_config.get("models", {})
        if models:
            table.add_row("Evaluator Model", models.get("evaluator", "default"))
            table.add_row("Drafter Model", models.get("drafter", "default"))

        platforms = yaml_config.get("platforms", {})
        x_config = platforms.get("x", {})
        if x_config.get("account_tier"):
            table.add_row("X Tier", x_config["account_tier"])

        scheduling = yaml_config.get("scheduling", {})
        if scheduling.get("timezone"):
            table.add_row("Timezone", scheduling["timezone"])

        console.print(table)
    except Exception:
        typer.echo("\n--- Configuration Summary ---")
        for k, v in env_vars.items():
            typer.echo(f"  {k}: ***set***")


def _setup_installations() -> None:
    """Install hook and cron."""
    typer.echo("--- Installation ---")

    if _confirm("Install Claude Code hook?"):
        from social_hook.setup.install import install_hook

        success, msg = install_hook()
        typer.echo(f"  {msg}")

    if _confirm("Install scheduler cron job?"):
        from social_hook.setup.install import install_cron

        success, msg = install_cron()
        typer.echo(f"  {msg}")

    if _confirm("Start Telegram bot?", default=False):
        typer.echo("  Run: social-hook bot start --daemon")


def _save_env(base: Path, env_vars: dict) -> None:
    """Save environment variables to .env file."""
    env_file = base / ".env"

    # Load existing
    existing = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()

    # Merge
    existing.update(env_vars)

    # Write
    lines = [f"{k}={v}" for k, v in sorted(existing.items())]
    env_file.write_text("\n".join(lines) + "\n")
    typer.echo(f"Environment saved to {env_file}")
