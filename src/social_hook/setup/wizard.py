"""Interactive setup wizard for social-hook."""

import logging
import subprocess
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

WIZARD_TOTAL_SECTIONS = 9


# =============================================================================
# Progress tracker
# =============================================================================


class WizardProgress:
    """Tracks wizard progress with section and sub-step granularity."""

    def __init__(self, total_sections: int = WIZARD_TOTAL_SECTIONS):
        self.total = total_sections
        self.section = 0
        self.section_label = ""
        self.substep = 0
        self.substeps_total = 1

    def set_section(self, n: int, label: str, substeps: int = 1) -> None:
        self.section = n
        self.section_label = label
        self.substep = 0
        self.substeps_total = substeps

    def advance(self) -> None:
        self.substep = min(self.substep + 1, self.substeps_total)
        self._render()

    @property
    def fraction(self) -> float:
        if self.total == 0 or self.section == 0:
            return 0.0
        base = (self.section - 1) / self.total
        within = (self.substep / self.substeps_total) / self.total
        return min(base + within, 1.0)

    def _render(self) -> None:
        """No-op — progress is tracked but not drawn with escape codes."""

    def render_top(self) -> None:
        """No-op — progress is tracked but not drawn with escape codes."""


# =============================================================================
# Helper functions
# =============================================================================


def _obfuscate(secret: str, show_chars: int = 4) -> str:
    """Obfuscate middle of a secret, showing first and last N chars."""
    if not secret:
        return ""
    if len(secret) <= show_chars * 2:
        return "***"
    return f"{secret[:show_chars]}***{secret[-show_chars:]}"


def _validate_not_empty(val: str) -> bool | str:
    """Validate that input is not empty or trivially short."""
    stripped = val.strip()
    if not stripped:
        return "Input cannot be empty"
    if len(stripped) <= 1 and stripped.lower() in ("y", "n"):
        return "Please enter a valid value, not just 'y' or 'n'"
    return True


def _validate_positive_int(val: str) -> bool | str:
    """Validate that input is a positive integer."""
    try:
        n = int(val)
        if n <= 0:
            return "Must be a positive number"
        return True
    except ValueError:
        return "Must be a number"


def _section(title: str, description: str = "", step: int = 0, progress: Optional[WizardProgress] = None) -> None:
    """Display a section header with Rich Panel or plain fallback."""
    typer.echo()  # blank line before each section

    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        content = f"[bold]{title}[/bold]"
        if description:
            content += f"\n[dim]{description}[/dim]"
        if not progress and step > 0:
            filled = int((step / WIZARD_TOTAL_SECTIONS) * 20)
            bar = "━" * filled + "╺" + "─" * max(0, 19 - filled)
            content += f"\n\n[dim]Step {step}/{WIZARD_TOTAL_SECTIONS}[/dim]  [cyan]{bar}[/cyan]"
        console.print()
        console.print(Panel(content, border_style="cyan"))
    except Exception:
        typer.echo(f"\n{'=' * 50}")
        typer.echo(f"  {title}")
        if description:
            typer.echo(f"  {description}")
        if not progress and step > 0:
            filled = int((step / WIZARD_TOTAL_SECTIONS) * 20)
            bar = "#" * filled + "-" * (20 - filled)
            typer.echo(f"  Step {step}/{WIZARD_TOTAL_SECTIONS}  [{bar}]")
        typer.echo(f"{'=' * 50}")


def _success(msg: str) -> None:
    """Display a success message."""
    try:
        from rich.console import Console

        Console().print(f"  [green]✓[/green] {msg}")
    except Exception:
        typer.echo(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    """Display a warning message."""
    try:
        from rich.console import Console

        Console().print(f"  [yellow]![/yellow] {msg}")
    except Exception:
        typer.echo(f"  ! {msg}")


def _error(msg: str) -> None:
    """Display an error message."""
    try:
        from rich.console import Console

        Console().print(f"  [red]✗[/red] {msg}")
    except Exception:
        typer.echo(f"  ✗ {msg}")


# =============================================================================
# Input primitives
# =============================================================================


def _rich_prompt(text: str, password: bool = False, validate: Optional[Callable] = None) -> str:
    """Prompt user for input with Rich formatting."""
    # Use plain terminal I/O to avoid screen-clearing side effects from prompt_toolkit
    raise NotImplementedError("Use fallback")


def _rich_confirm(text: str, default: bool = True) -> bool:
    """Ask yes/no confirmation."""
    raise NotImplementedError("Use fallback")


def _rich_select(text: str, choices: list[str], default: Optional[str] = None) -> str:
    """Select from a list."""
    raise NotImplementedError("Use fallback")


def _spinner(text: str, fn: Callable) -> Any:
    """Run a function with a Rich spinner."""
    try:
        from rich.console import Console

        console = Console()
        with console.status(text):
            return fn()
    except Exception:
        return fn()


def _prompt(text: str, default: str = "", hide_default: bool = False) -> str:
    """Prompt user for input with plain terminal I/O.

    Args:
        text: Prompt label.
        default: Default value returned when user presses Enter without input.
        hide_default: If True, show '(Enter to keep current)' instead of the
            default value in brackets.  Useful for secrets/API keys.
    """
    while True:
        if default and hide_default:
            val = input(f"{text} (Enter to keep current): ").strip()
            if not val:
                return default
        elif default:
            val = input(f"{text} [{default}]: ").strip()
            if not val:
                return default
        else:
            val = input(f"{text}: ").strip()

        if not default:
            check = _validate_not_empty(val)
            if check is not True:
                print(check)
                continue
        return val


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
    """Select from a list with arrow keys (TTY) or numbered fallback."""
    if sys.stdout.isatty() and sys.stdin.isatty():
        return _select_arrows(text, choices, default=default)

    # Non-TTY fallback: numbered choice
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


def _select_arrows(text: str, choices: list[str], default: Optional[str] = None) -> str:
    """Arrow-key selector for TTY terminals."""
    import tty
    import termios

    # Find initial selection
    selected = 0
    if default:
        for i, c in enumerate(choices):
            if c == default:
                selected = i
                break

    total = len(choices)

    def _draw(sel: int) -> None:
        """Draw the choice list. Clears each line and repositions cursor to top."""
        for i, c in enumerate(choices):
            sys.stdout.write("\033[2K\r")  # clear line, carriage return
            if i == sel:
                sys.stdout.write(f"  \033[36m❯ {c}\033[0m")
            else:
                sys.stdout.write(f"    {c}")
            if i < total - 1:
                sys.stdout.write("\n")
        # Move cursor back to first choice line
        if total > 1:
            sys.stdout.write(f"\033[{total - 1}A\r")
        sys.stdout.flush()

    def _read_key() -> str:
        """Read a single keypress, handling arrow key escape sequences."""
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        return "up"
                    elif ch3 == "B":
                        return "down"
                return "escape"
            elif ch in ("\r", "\n"):
                return "enter"
            elif ch == "\x03":
                raise KeyboardInterrupt
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print(f"\n{text}  (↑/↓ to move, Enter to select)")
    _draw(selected)

    while True:
        key = _read_key()
        if key == "up" and selected > 0:
            selected -= 1
            _draw(selected)
        elif key == "down" and selected < total - 1:
            selected += 1
            _draw(selected)
        elif key == "enter":
            # Move cursor past the list before returning
            if total > 1:
                sys.stdout.write(f"\033[{total - 1}B")
            sys.stdout.write("\n")
            sys.stdout.flush()
            return choices[selected]


def _prompt_api_key(
    text: str,
    validate_fn: Callable[[str], tuple[bool, str]],
    existing: str = "",
) -> str | None:
    """Prompt for an API key, validate it, and re-prompt on failure.

    Returns the valid key, or None if user chooses to skip entirely.
    """
    while True:
        if existing:
            typer.echo(f"  Current: {_obfuscate(existing)}")
            key = _prompt(text, default=existing, hide_default=True)
        else:
            key = _prompt(text)

        success, msg = _spinner("Validating...", lambda: validate_fn(key))
        if success:
            _success(msg)
            return key

        _error(msg)
        if _confirm("Try again?"):
            continue
        _warn("Key saved without validation")
        return key


# =============================================================================
# Config loading
# =============================================================================


def _load_existing() -> tuple[dict[str, str], dict[str, Any]]:
    """Load existing configuration for pre-population.

    Returns:
        (existing_env, existing_yaml) — empty dicts if no config exists.
    """
    existing_env: dict[str, str] = {}
    existing_yaml: dict[str, Any] = {}

    try:
        from social_hook.config import load_full_config

        config = load_full_config()
        existing_env = dict(config.env) if config.env else {}
        existing_yaml = {
            "models": {
                "evaluator": config.models.evaluator,
                "drafter": config.models.drafter,
                "gatekeeper": config.models.gatekeeper,
            },
            "platforms": {
                "x": {
                    "enabled": config.platforms.x.enabled,
                    "account_tier": config.platforms.x.account_tier,
                },
            },
            "scheduling": {
                "timezone": config.scheduling.timezone,
                "max_posts_per_day": config.scheduling.max_posts_per_day,
                "min_gap_minutes": config.scheduling.min_gap_minutes,
            },
            "image_generation": {
                "enabled": config.image_generation.enabled,
                "service": config.image_generation.service,
            },
        }
    except Exception:
        pass  # No existing config — fresh setup

    return existing_env, existing_yaml


# =============================================================================
# Main wizard
# =============================================================================


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
        console.print()
        console.print(Panel(
            "[bold]Social Hook Setup[/bold]\n\n"
            "This wizard will walk you through:\n"
            "  1. API credentials (Anthropic, Telegram)\n"
            "  2. Voice & style configuration\n"
            "  3. Platform setup (X, LinkedIn)\n"
            "  4. Model selection\n"
            "  5. Scheduling preferences\n\n"
            "Press Ctrl+C at any time to cancel.\n"
            "[dim]Existing values shown as defaults.[/dim]",
            title="Welcome",
            border_style="cyan",
        ))
        console.print()
    except Exception:
        typer.echo("\n=== Social Hook Setup ===\n")
        typer.echo("This wizard will walk you through:")
        typer.echo("  1. API credentials (Anthropic, Telegram)")
        typer.echo("  2. Voice & style configuration")
        typer.echo("  3. Platform setup (X, LinkedIn)")
        typer.echo("  4. Model selection")
        typer.echo("  5. Scheduling preferences")
        typer.echo("\nPress Ctrl+C at any time to cancel.")
        typer.echo("Existing values shown as defaults.\n")

    try:
        # Initialize filesystem
        base = init_filesystem()

        # Load existing config for pre-population
        existing_env, existing_yaml = _load_existing()

        # Progress tracker
        progress = WizardProgress()

        env_vars: dict[str, str] = {}
        yaml_config: dict[str, Any] = {}

        def _save_progress() -> None:
            """Save whatever we have so far."""
            if env_vars:
                _save_env(base, env_vars)
            if yaml_config:
                _save_config_yaml(base, yaml_config)

        if only is None or only == "anthropic":
            _setup_anthropic(env_vars, existing_env, progress)
            _save_progress()

        if only is None or only == "voice":
            _setup_voice_style(base, progress)

        if only is None or only == "telegram":
            _setup_telegram(env_vars, existing_env, progress)
            _save_progress()

        if only is None or only == "x":
            _setup_x(env_vars, yaml_config, existing_env, existing_yaml, progress)
            _save_progress()

        if only is None or only == "linkedin":
            _setup_linkedin(env_vars, existing_env, progress)
            _save_progress()

        if only is None or only == "models":
            _setup_models(yaml_config, existing_yaml, progress)
            _save_progress()

        if only is None or only == "image":
            _setup_image_gen(env_vars, yaml_config, existing_env, progress)
            _save_progress()

        installed = False
        if only is None:
            _setup_scheduling(base, yaml_config, existing_yaml, progress)
            _save_progress()
            _show_summary(env_vars, yaml_config)
            installed = _setup_installations(progress)

        # --- Completion message with warnings ---
        warnings: list[str] = []
        if only is None:
            has_anthropic = "ANTHROPIC_API_KEY" in env_vars or existing_env.get("ANTHROPIC_API_KEY")
            has_telegram = "TELEGRAM_BOT_TOKEN" in env_vars or existing_env.get("TELEGRAM_BOT_TOKEN")
            has_voice = (base / "social-context.md").exists()
            has_x = "X_API_KEY" in env_vars or existing_env.get("X_API_KEY")

            if not has_anthropic:
                warnings.append("Anthropic API key not configured — AI features won't work")
            if not has_telegram:
                warnings.append("Telegram bot not configured — no draft notifications")
            if not has_voice:
                warnings.append("Voice & style not configured — run `social-hook setup --only voice`")
            if not has_x:
                warnings.append("X (Twitter) not configured — no auto-posting")
            if not installed:
                warnings.append("Installations skipped — run `social-hook setup` to install hook, cron, and bot")

        if warnings:
            typer.echo("")
            _warn("Setup complete with warnings:")
            for w in warnings:
                _warn(f"  • {w}")
            typer.echo("")
            _warn("Run `social-hook setup` to reconfigure.")
        else:
            _success("Setup complete!")

        return True

    except KeyboardInterrupt:
        typer.echo("\n\nSetup cancelled. Progress from completed sections has been saved.")
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


# =============================================================================
# Setup steps
# =============================================================================


def _setup_anthropic(env_vars: dict, existing_env: dict, progress: Optional[WizardProgress] = None) -> None:
    """Configure Anthropic API key."""
    if progress:
        progress.set_section(1, "Anthropic", substeps=1)
    _section("Anthropic API Key", "Powers all AI evaluation and content generation", progress=progress)

    from social_hook.setup.validation import validate_anthropic_key

    existing = existing_env.get("ANTHROPIC_API_KEY", "")
    key = _prompt_api_key("Anthropic API key", validate_anthropic_key, existing=existing)
    if key:
        env_vars["ANTHROPIC_API_KEY"] = key
    elif existing:
        env_vars["ANTHROPIC_API_KEY"] = existing
        _warn("Keeping existing key")
    else:
        _warn("No API key configured — AI features will not work")

    if progress:
        progress.advance()


def _setup_voice_style(base: Path, progress: Optional[WizardProgress] = None) -> None:
    """Configure voice and style (social-context.md)."""
    if progress:
        progress.set_section(2, "Voice & Style", substeps=8)
    _section("Voice & Style", "Define how your content sounds and who it's for", progress=progress)

    context_path = base / "social-context.md"

    # Show existing config if present
    if context_path.exists():
        try:
            from rich.console import Console
            from rich.panel import Panel

            console = Console()
            content = context_path.read_text()
            # Show a preview (first 500 chars)
            preview = content[:500] + ("..." if len(content) > 500 else "")
            console.print(Panel(preview, title="Current voice config", border_style="dim"))
        except Exception:
            typer.echo("  Current voice config exists.")

        if not _confirm("Update voice settings?", default=False):
            _success("Keeping existing voice config")
            return
    else:
        # Show intro explaining what this is
        try:
            from rich.console import Console
            from rich.panel import Panel

            Console().print(Panel(
                "Voice & style settings control how your social media content sounds.\n"
                "This creates a social-context.md file that guides the AI drafter.\n\n"
                "[dim]Example: 'Conversational, technically confident but not arrogant.\n"
                "Shares the journey honestly, including challenges.'[/dim]",
                border_style="dim",
            ))
        except Exception:
            typer.echo("  Voice & style settings control how your content sounds.")
            typer.echo("  This creates a social-context.md file that guides the AI drafter.")

        if not _confirm("Configure voice and style now?"):
            return

    # --- Voice ---
    typer.echo("")
    voice = _prompt(
        "Describe your voice/tone",
        default="Conversational, technically confident but not arrogant. Shares the journey honestly.",
    )
    if progress:
        progress.advance()

    sample1 = _prompt(
        "Writing sample (paste an example of your writing style, or press Enter to skip)",
        default="",
    )
    if progress:
        progress.advance()

    # --- Identity ---
    identity_choices = [
        "I (first person)",
        "We (team)",
        "Project voice",
    ]
    identity = _select("Who speaks in the content?", identity_choices, default="I (first person)")
    if progress:
        progress.advance()

    # --- Pet Peeves ---
    typer.echo("")
    try:
        from rich.console import Console
        from rich.panel import Panel

        Console().print(Panel(
            "[dim]Examples: 'Excited to announce...', 'Game-changing', 'Leverage',\n"
            "'Utilize', 'Revolutionary', 'It\\'s important to note that...',\n"
            "'Here\\'s the thing', 'Let\\'s be honest', 'This is huge',\n"
            "'Hot take:', 'Unpopular opinion:', em dash pivots (X — Y)[/dim]",
            title="Pet peeves reference",
            border_style="dim",
        ))
    except Exception:
        typer.echo("  Examples: 'Excited to announce...', 'Game-changing', 'Leverage',")
        typer.echo("  'Here's the thing', 'Hot take:', 'Unpopular opinion:', em dash pivots")

    pet_peeves = _prompt(
        "Words/phrases to never use (comma-separated)",
        default="Excited to announce, Game-changing, Revolutionary, Leverage, Utilize, Here's the thing, Let's be honest, This is huge, Hot take, Unpopular opinion, em dash pivots",
    )
    if progress:
        progress.advance()

    grammar = _prompt(
        "Grammar preferences",
        default="Oxford comma: yes, emoji: sparingly, exclamation marks: rare",
    )
    if progress:
        progress.advance()

    # --- Audience ---
    typer.echo("")
    audience = _prompt(
        "Primary audience",
        default="Developers, indie hackers, builders",
    )
    tech_level = _select("Audience technical level:", [
        "Beginner",
        "Intermediate",
        "Intermediate to advanced",
        "Advanced",
    ], default="Intermediate to advanced")
    audience_cares = _prompt(
        "What does your audience care about?",
        default="Practical tools, honest experiences, code they can learn from",
    )
    if progress:
        progress.advance()

    # --- Topics ---
    typer.echo("")
    topics_emphasize = _prompt(
        "Topics to emphasize (comma-separated)",
        default="Building in public, automation, developer tools",
    )
    topics_avoid = _prompt(
        "Topics to avoid (comma-separated)",
        default="AI doom debates, competitor criticism, politics",
    )
    if progress:
        progress.advance()

    # --- Generate social-context.md ---
    samples_section = ""
    if sample1:
        samples_section = f"""
### Writing Samples

**Sample 1:**
> "{sample1}"
"""

    context_content = f"""# Social Context

> Voice, style, and audience guidance for content generation.

---

## Author's Voice

### Voice Description
{voice}
{samples_section}
---

## Author's Pet Peeves

### Words/Phrases to Avoid
{chr(10).join(f'- "{p.strip()}"' for p in pet_peeves.split(',') if p.strip())}

### Grammar/Style Preferences
{chr(10).join(f'- {p.strip()}' for p in grammar.split(',') if p.strip())}

### Authenticity Rules
- Never claim something works if it doesn't yet
- Acknowledge limitations and trade-offs
- Show the messy parts, not just polished outcomes

---

## Writing/Narrative Strategy

### Identity
{identity.split(' (')[0]}

---

## Audience

### Primary Audience
- **Who:** {audience}
- **Technical level:** {tech_level}
- **What they care about:** {audience_cares}

---

## Themes & Topics

### Emphasize
{chr(10).join(f'- {t.strip()}' for t in topics_emphasize.split(',') if t.strip())}

### Avoid
{chr(10).join(f'- {t.strip()}' for t in topics_avoid.split(',') if t.strip())}

---

## Engagement Patterns

### Call-to-Action Usage
- **Often:** Questions to audience ("How do you handle X?")
- **Sometimes:** Follow for updates
- **Rarely:** Star the repo, check out the project
- **Never:** Aggressive sales, "link in bio" spam

### Hashtag Strategy
- **X:** Minimal. Only if genuinely discoverable (#buildinpublic). Never stuff.
- **LinkedIn:** Standard 3-5 relevant tags.
"""

    context_path.write_text(context_content)
    _success(f"Voice config saved to {context_path}")

    if progress:
        progress.advance()


def _setup_telegram(env_vars: dict, existing_env: dict, progress: Optional[WizardProgress] = None) -> None:
    """Configure Telegram bot."""
    if progress:
        progress.set_section(3, "Telegram", substeps=2)
    _section("Telegram Bot", "Review and approve posts via Telegram", progress=progress)
    if not _confirm("Set up Telegram bot?"):
        return

    from social_hook.setup.validation import validate_telegram_bot

    existing_token = existing_env.get("TELEGRAM_BOT_TOKEN", "")
    token = _prompt_api_key("Bot token (from @BotFather)", validate_telegram_bot, existing=existing_token)

    if not token:
        if existing_token:
            env_vars["TELEGRAM_BOT_TOKEN"] = existing_token
            _warn("Keeping existing token")
        else:
            _warn("No bot token configured — Telegram notifications will not work")
        return

    env_vars["TELEGRAM_BOT_TOKEN"] = token
    if progress:
        progress.advance()

    # Chat ID capture
    existing_chat_id = existing_env.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    typer.echo("\nSend any message to your bot to capture your chat ID...")

    from social_hook.setup.validation import capture_telegram_chat_id

    chat_id = capture_telegram_chat_id(token, timeout_seconds=30)
    if chat_id:
        env_vars["TELEGRAM_ALLOWED_CHAT_IDS"] = chat_id
        _success(f"Chat ID captured: {chat_id}")
    else:
        _warn("No message received. Enter chat ID manually.")
        default_chat = existing_chat_id or ""
        while True:
            if default_chat:
                chat_id = _prompt(f"Chat ID [{default_chat}]", default=default_chat)
            else:
                chat_id = _prompt("Chat ID")
            # Validate it's numeric
            if chat_id.lstrip("-").isdigit():
                env_vars["TELEGRAM_ALLOWED_CHAT_IDS"] = chat_id
                _success(f"Chat ID set: {chat_id}")
                break
            _error("Chat ID must be a number")

    if progress:
        progress.advance()


def _setup_x(env_vars: dict, yaml_config: dict, existing_env: dict, existing_yaml: dict,
             progress: Optional[WizardProgress] = None) -> None:
    """Configure X (Twitter) API."""
    if progress:
        progress.set_section(4, "X (Twitter)", substeps=5)
    _section("X (Twitter)", "Post to X automatically", progress=progress)
    if not _confirm("Set up X posting?", default=False):
        return

    # Show console.x.com link
    try:
        from rich.console import Console
        from rich.panel import Panel

        Console().print(Panel(
            "Get your API keys from the X Developer Console:\n"
            "[link=https://console.x.com]https://console.x.com[/link]\n\n"
            "[dim]You need 4 credentials (under OAuth 1.0a):\n"
            "API Key, API Secret, Access Token, Access Token Secret[/dim]",
            border_style="dim",
        ))
    except Exception:
        typer.echo("  Get your API keys from: https://console.x.com")
        typer.echo("  You need: API Key, API Secret, Access Token, Access Token Secret")

    # Collect all 4 credentials with pre-population
    existing_api_key = existing_env.get("X_API_KEY", "")
    existing_api_secret = existing_env.get("X_API_SECRET", "")
    existing_access_token = existing_env.get("X_ACCESS_TOKEN", "")
    existing_access_secret = existing_env.get("X_ACCESS_SECRET", "")

    def _prompt_x_field(label: str, existing: str) -> str:
        if existing:
            typer.echo(f"  Current {label}: {_obfuscate(existing)}")
            return _prompt(label, default=existing, hide_default=True)
        return _prompt(label)

    api_key = _prompt_x_field("API Key", existing_api_key)
    if progress:
        progress.advance()
    api_secret = _prompt_x_field("API Secret", existing_api_secret)
    if progress:
        progress.advance()
    access_token = _prompt_x_field("Access Token", existing_access_token)
    if progress:
        progress.advance()
    access_secret = _prompt_x_field("Access Token Secret", existing_access_secret)
    if progress:
        progress.advance()

    # Validate all 4 together
    from social_hook.setup.validation import validate_x_api

    while True:
        success, msg = _spinner(
            "Validating X credentials...",
            lambda: validate_x_api(api_key, api_secret, access_token, access_secret),
        )
        if success:
            _success(msg)
            break
        _error(msg)
        if not _confirm("Try again with new credentials?"):
            _warn("X credentials saved without validation")
            break
        api_key = _prompt_x_field("API Key", api_key)
        api_secret = _prompt_x_field("API Secret", api_secret)
        access_token = _prompt_x_field("Access Token", access_token)
        access_secret = _prompt_x_field("Access Token Secret", access_secret)

    env_vars["X_API_KEY"] = api_key
    env_vars["X_API_SECRET"] = api_secret
    env_vars["X_ACCESS_TOKEN"] = access_token
    env_vars["X_ACCESS_SECRET"] = access_secret

    # Tier selection
    existing_tier = existing_yaml.get("platforms", {}).get("x", {}).get("account_tier", "free")
    tier_choices = [
        "free (280 chars)",
        "basic (25,000 chars)",
        "premium (25,000 chars)",
        "premium_plus (25,000 chars)",
    ]
    # Set default to match existing tier
    default_tier = next((c for c in tier_choices if c.startswith(existing_tier)), tier_choices[0])
    tier_display = _select("X account tier:", tier_choices, default=default_tier)
    tier_value = tier_display.split(" ")[0]

    yaml_config.setdefault("platforms", {}).setdefault("x", {})
    yaml_config["platforms"]["x"]["enabled"] = True
    yaml_config["platforms"]["x"]["account_tier"] = tier_value

    _success("X configured")
    if progress:
        progress.advance()


def _setup_linkedin(env_vars: dict, existing_env: dict, progress: Optional[WizardProgress] = None) -> None:
    """Configure LinkedIn API."""
    if progress:
        progress.set_section(5, "LinkedIn", substeps=1)
    _section("LinkedIn", "Post to LinkedIn", progress=progress)
    if not _confirm("Set up LinkedIn posting?", default=False):
        return

    existing_token = existing_env.get("LINKEDIN_ACCESS_TOKEN", "")
    if existing_token:
        typer.echo(f"  Current: {_obfuscate(existing_token)}")
        token = _prompt("LinkedIn access token", default=existing_token, hide_default=True)
    else:
        token = _prompt("LinkedIn access token")

    env_vars["LINKEDIN_ACCESS_TOKEN"] = token
    _success("LinkedIn credentials saved")
    if progress:
        progress.advance()


def _setup_models(yaml_config: dict, existing_yaml: dict, progress: Optional[WizardProgress] = None) -> None:
    """Configure LLM models."""
    if progress:
        progress.set_section(6, "Models", substeps=3)
    _section("Model Selection", "Choose AI models for each role", progress=progress)
    if not _confirm("Customize models? (defaults: Opus for eval/draft, Haiku for gatekeeper)"):
        return

    existing_models = existing_yaml.get("models", {})

    # Evaluator
    eval_choices = ["claude-opus-4-5 (recommended)", "claude-sonnet-4-5", "claude-haiku-4-5"]
    existing_eval = existing_models.get("evaluator", "claude-opus-4-5")
    default_eval = next((c for c in eval_choices if c.startswith(existing_eval)), eval_choices[0])
    evaluator = _select("Evaluator model (decides post-worthiness):", eval_choices, default=default_eval)
    if progress:
        progress.advance()

    # Drafter
    draft_choices = ["claude-opus-4-5 (recommended)", "claude-sonnet-4-5", "claude-haiku-4-5"]
    existing_draft = existing_models.get("drafter", "claude-opus-4-5")
    default_draft = next((c for c in draft_choices if c.startswith(existing_draft)), draft_choices[0])
    drafter = _select("Drafter model (creates content):", draft_choices, default=default_draft)
    if progress:
        progress.advance()

    # Gatekeeper
    gate_choices = ["claude-haiku-4-5 (recommended)", "claude-sonnet-4-5", "claude-opus-4-5"]
    existing_gate = existing_models.get("gatekeeper", "claude-haiku-4-5")
    default_gate = next((c for c in gate_choices if c.startswith(existing_gate)), gate_choices[0])
    gatekeeper = _select("Gatekeeper model (Telegram interactions):", gate_choices, default=default_gate)
    if progress:
        progress.advance()

    # Strip "(recommended)" suffix
    yaml_config["models"] = {
        "evaluator": evaluator.split(" (")[0],
        "drafter": drafter.split(" (")[0],
        "gatekeeper": gatekeeper.split(" (")[0],
    }
    _success("Models configured")


def _setup_image_gen(env_vars: dict, yaml_config: dict, existing_env: dict,
                     progress: Optional[WizardProgress] = None) -> None:
    """Configure image generation."""
    if progress:
        progress.set_section(7, "Image Gen", substeps=2)
    _section("Image Generation", "AI-generated visuals for posts", progress=progress)
    if not _confirm("Enable AI image generation?"):
        yaml_config.setdefault("image_generation", {})["enabled"] = False
        return

    service_choices = ["nano_banana_pro"]
    service = _select("Image generation service:", service_choices, default="nano_banana_pro")

    yaml_config.setdefault("image_generation", {})["enabled"] = True
    yaml_config["image_generation"]["service"] = service
    if progress:
        progress.advance()

    if service == "nano_banana_pro":
        from social_hook.setup.validation import validate_image_gen

        existing_key = existing_env.get("GEMINI_API_KEY", "")
        key = _prompt_api_key(
            "Gemini API key (for Nano Banana Pro)",
            lambda k: validate_image_gen(service, k),
            existing=existing_key,
        )
        if key:
            env_vars["GEMINI_API_KEY"] = key
        elif existing_key:
            _warn("Keeping existing key")
        else:
            _warn("No Gemini key configured — image generation will not work")

    if progress:
        progress.advance()


def _setup_scheduling(base: Path, yaml_config: dict, existing_yaml: dict,
                      progress: Optional[WizardProgress] = None) -> None:
    """Configure scheduling settings."""
    if progress:
        progress.set_section(8, "Scheduling", substeps=3)
    _section("Scheduling", "When and how often to post", progress=progress)

    existing_sched = existing_yaml.get("scheduling", {})

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

    existing_tz = existing_sched.get("timezone", local_tz)
    if existing_tz not in tz_choices:
        tz_choices.insert(0, existing_tz)
    default_tz = existing_tz if existing_tz in tz_choices else "UTC"

    tz = _select("Timezone:", tz_choices, default=default_tz)
    if progress:
        progress.advance()

    # Max posts per day — selector with recommended + custom
    existing_max = str(existing_sched.get("max_posts_per_day", 3))
    max_choices = ["2", "3 (recommended)", "5", "Custom"]
    default_max = next((c for c in max_choices if c.startswith(existing_max)), "3 (recommended)")
    max_posts = _select("Max posts per day:", max_choices, default=default_max)
    if max_posts == "Custom":
        while True:
            max_posts = _prompt("Enter max posts per day", default=existing_max)
            check = _validate_positive_int(max_posts)
            if check is True:
                break
            _error(check)
    max_posts_val = int(max_posts.split(" ")[0])
    if progress:
        progress.advance()

    # Min gap — selector with recommended + custom
    existing_gap = str(existing_sched.get("min_gap_minutes", 30))
    gap_choices = ["15", "30 (recommended)", "60", "Custom"]
    default_gap = next((c for c in gap_choices if c.startswith(existing_gap)), "30 (recommended)")
    min_gap = _select("Min gap between posts (minutes):", gap_choices, default=default_gap)
    if min_gap == "Custom":
        while True:
            min_gap = _prompt("Enter min gap in minutes", default=existing_gap)
            check = _validate_positive_int(min_gap)
            if check is True:
                break
            _error(check)
    min_gap_val = int(min_gap.split(" ")[0])
    if progress:
        progress.advance()

    yaml_config.setdefault("scheduling", {})
    yaml_config["scheduling"]["timezone"] = tz
    yaml_config["scheduling"]["max_posts_per_day"] = max_posts_val
    yaml_config["scheduling"]["min_gap_minutes"] = min_gap_val
    yaml_config["scheduling"]["optimal_days"] = ["Tue", "Wed", "Thu"]
    yaml_config["scheduling"]["optimal_hours"] = [9, 12, 17]

    _success("Scheduling configured")


# =============================================================================
# Save, summary, install
# =============================================================================


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
    _success(f"Config saved to {config_path}")


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
            table.add_row("Anthropic API Key", _obfuscate(env_vars["ANTHROPIC_API_KEY"]))
        if "TELEGRAM_BOT_TOKEN" in env_vars:
            table.add_row("Telegram Bot", _obfuscate(env_vars["TELEGRAM_BOT_TOKEN"]))
        if "X_API_KEY" in env_vars:
            table.add_row("X (Twitter)", _obfuscate(env_vars["X_API_KEY"]))
        if "LINKEDIN_ACCESS_TOKEN" in env_vars:
            table.add_row("LinkedIn", _obfuscate(env_vars["LINKEDIN_ACCESS_TOKEN"]))
        if "GEMINI_API_KEY" in env_vars:
            table.add_row("Image Gen (Gemini)", _obfuscate(env_vars["GEMINI_API_KEY"]))

        models = yaml_config.get("models", {})
        if models:
            table.add_row("Evaluator Model", models.get("evaluator", "default"))
            table.add_row("Drafter Model", models.get("drafter", "default"))
            table.add_row("Gatekeeper Model", models.get("gatekeeper", "default"))

        platforms = yaml_config.get("platforms", {})
        x_config = platforms.get("x", {})
        if x_config.get("account_tier"):
            table.add_row("X Tier", x_config["account_tier"])

        scheduling = yaml_config.get("scheduling", {})
        if scheduling.get("timezone"):
            table.add_row("Timezone", scheduling["timezone"])
        if scheduling.get("max_posts_per_day"):
            table.add_row("Max Posts/Day", str(scheduling["max_posts_per_day"]))

        console.print()
        console.print(table)
    except Exception:
        typer.echo("\n--- Configuration Summary ---")
        for k, v in env_vars.items():
            if any(secret in k for secret in ("KEY", "TOKEN", "SECRET")):
                typer.echo(f"  {k}: {_obfuscate(v)}")
            else:
                typer.echo(f"  {k}: {v}")


def _setup_installations(progress: Optional[WizardProgress] = None) -> bool:
    """Install hook, cron, and start bot. Returns True if installed, False if skipped."""
    if progress:
        progress.set_section(9, "Installation", substeps=3)
    _section("Installation", "Set up hook, scheduler, and bot", progress=progress)

    try:
        from rich.console import Console
        from rich.panel import Panel

        Console().print(Panel(
            "The following components will be installed:\n\n"
            "  • Claude Code hook → ~/.claude/hooks.json\n"
            "    Triggers social-hook on git commit\n\n"
            "  • Scheduler cron job → runs every minute\n"
            "    Posts approved drafts at scheduled times\n\n"
            "  • Telegram bot → background daemon\n"
            "    Receives and processes draft reviews",
            border_style="dim",
        ))
    except Exception:
        typer.echo("  The following will be installed:")
        typer.echo("  • Claude Code hook (triggers on git commit)")
        typer.echo("  • Scheduler cron job (posts at scheduled times)")
        typer.echo("  • Telegram bot daemon (processes reviews)")

    if not _confirm("Install all components?"):
        _warn("Skipping installation. You can install manually later.")
        return False

    # Hook
    from social_hook.setup.install import install_hook, check_hook_installed

    if check_hook_installed():
        _success("Claude Code hook already installed")
    else:
        success, msg = install_hook()
        if success:
            _success(msg)
        else:
            _error(msg)
    if progress:
        progress.advance()

    # Cron
    from social_hook.setup.install import install_cron, check_cron_installed

    if check_cron_installed():
        _success("Scheduler cron already installed")
    else:
        success, msg = install_cron()
        if success:
            _success(msg)
        else:
            _error(msg)
    if progress:
        progress.advance()

    # Bot daemon
    from social_hook.bot.process import is_running

    if is_running():
        _success("Telegram bot already running")
    else:
        try:
            result = subprocess.run(
                ["social-hook", "bot", "start", "--daemon"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                _success("Telegram bot started")
            else:
                _error(f"Bot start failed: {result.stderr.strip() or result.stdout.strip()}")
        except FileNotFoundError:
            _warn("social-hook command not found — start bot manually: social-hook bot start --daemon")
        except Exception as e:
            _error(f"Bot start failed: {e}")
    if progress:
        progress.advance()

    return True


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
    _success(f"Environment saved to {env_file}")
