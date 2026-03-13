#!/usr/bin/env python3
"""Generate CLI reference documentation from the Typer app.

Introspects the Click command tree and writes markdown files to docs/cli/.
Run from repo root: python scripts/generate_cli_docs.py

Output structure:
  docs/cli/index.md          — overview with global options and command list
  docs/cli/<group>.md        — one page per command group (draft, project, etc.)
  docs/cli/root-commands.md  — top-level commands (version, init, trigger, etc.)
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import click
import typer.main

from social_hook.cli import app
from social_hook.constants import PROJECT_SLUG

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "cli"

# Commands to exclude from docs (internal hooks)
HIDDEN_COMMANDS = {"commit-hook", "git-hook", "narrative-capture"}


def get_click_app() -> click.Group:
    return typer.main.get_command(app)


def format_type(param: click.Parameter) -> str:
    """Human-readable type string."""
    type_name = getattr(param.type, "name", str(param.type))
    mapping = {
        "TEXT": "string",
        "INT": "integer",
        "FLOAT": "number",
        "BOOL": "boolean",
        "PATH": "path",
        "FILENAME": "path",
    }
    return mapping.get(type_name.upper(), type_name.lower())


def format_default(param: click.Parameter) -> str:
    """Format default value for display."""
    if param.default is None:
        return ""
    if isinstance(param.default, bool):
        return str(param.default).lower()
    if param.default == ():
        return ""
    return str(param.default)


def option_flags(param: click.Option) -> str:
    """Format option flags like --name, -n."""
    parts = []
    for opt in param.opts:
        parts.append(f"`{opt}`")
    for opt in param.secondary_opts:
        parts.append(f"`{opt}`")
    return ", ".join(parts)


def render_params(cmd: click.Command) -> str:
    """Render arguments and options as markdown tables."""
    lines = []
    skip = {"install_completion", "show_completion", "help", "ctx"}

    # Arguments
    args = [p for p in cmd.params if isinstance(p, click.Argument)]
    if args:
        lines.append("**Arguments:**")
        lines.append("")
        lines.append("| Name | Required | Description |")
        lines.append("|------|----------|-------------|")
        for arg in args:
            name = arg.name or ""
            req = "yes" if arg.required else "no"
            help_text = getattr(arg, "help", "") or ""
            # Click arguments don't always have help; try type info
            if not help_text:
                help_text = f"({format_type(arg)})"
            lines.append(f"| `{name}` | {req} | {help_text} |")
        lines.append("")

    # Options
    opts = [p for p in cmd.params if isinstance(p, click.Option) and p.name not in skip]
    if opts:
        lines.append("**Options:**")
        lines.append("")
        lines.append("| Flag | Type | Default | Description |")
        lines.append("|------|------|---------|-------------|")
        for opt in opts:
            flags = option_flags(opt)
            typ = format_type(opt)
            default = format_default(opt)
            help_text = opt.help or ""
            lines.append(f"| {flags} | {typ} | {default} | {help_text} |")
        lines.append("")

    return "\n".join(lines)


def render_command(cmd: click.Command, name: str, prefix: str) -> str:
    """Render a single command as markdown."""
    lines = []
    full_name = f"{prefix} {name}"
    lines.append(f"### `{full_name}`")
    lines.append("")

    if cmd.help:
        # First line is summary, rest is detail
        help_lines = cmd.help.strip().split("\n")
        summary = help_lines[0].strip()
        lines.append(summary)
        lines.append("")

        if len(help_lines) > 1:
            detail = textwrap.dedent("\n".join(help_lines[1:])).strip()
            if detail:
                lines.append(detail)
                lines.append("")

    params = render_params(cmd)
    if params:
        lines.append(params)

    return "\n".join(lines)


def render_group_page(group: click.Group, group_name: str) -> str:
    """Render a command group as a full markdown page."""
    lines = []
    prefix = f"{PROJECT_SLUG} {group_name}"
    lines.append(f"# {PROJECT_SLUG} {group_name}")
    lines.append("")

    if group.help:
        lines.append(group.help.strip())
        lines.append("")

    # If the group itself is invokable (invoke_without_command)
    group_params = render_params(group)
    if group_params:
        lines.append("**Group options:**")
        lines.append("")
        lines.append(group_params)

    # Subcommands
    if hasattr(group, "commands") and group.commands:
        lines.append("---")
        lines.append("")
        for cmd_name in sorted(group.commands):
            cmd = group.commands[cmd_name]
            if getattr(cmd, "hidden", False):
                continue
            lines.append(render_command(cmd, cmd_name, prefix))
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def render_root_commands(click_app: click.Group) -> str:
    """Render top-level (non-group) commands."""
    lines = []
    lines.append(f"# {PROJECT_SLUG} commands")
    lines.append("")
    lines.append("Top-level commands that are not part of a command group.")
    lines.append("")

    for cmd_name in sorted(click_app.commands):
        cmd = click_app.commands[cmd_name]
        if getattr(cmd, "hidden", False) or cmd_name in HIDDEN_COMMANDS:
            continue
        # Skip groups — they get their own pages
        if hasattr(cmd, "commands") and cmd.commands:
            continue
        lines.append(render_command(cmd, cmd_name, PROJECT_SLUG))
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def render_index(click_app: click.Group, groups: list[str]) -> str:
    """Render the index page with global options and navigation."""
    lines = []
    lines.append(f"# {PROJECT_SLUG} CLI Reference")
    lines.append("")
    lines.append(click_app.help or "")
    lines.append("")

    # Global options
    lines.append("## Global Options")
    lines.append("")
    lines.append("These options can be placed before any command.")
    lines.append("")
    lines.append(render_params(click_app))

    # Command groups
    lines.append("## Command Groups")
    lines.append("")
    lines.append("| Group | Description |")
    lines.append("|-------|-------------|")
    for name in sorted(groups):
        cmd = click_app.commands[name]
        help_text = cmd.help.split("\n")[0].strip() if cmd.help else ""
        lines.append(f"| [`{name}`]({name}.md) | {help_text} |")
    lines.append("")

    # Root commands
    root_cmds = []
    for cmd_name in sorted(click_app.commands):
        cmd = click_app.commands[cmd_name]
        if getattr(cmd, "hidden", False) or cmd_name in HIDDEN_COMMANDS:
            continue
        if hasattr(cmd, "commands") and cmd.commands:
            continue
        root_cmds.append((cmd_name, cmd))

    if root_cmds:
        lines.append("## Commands")
        lines.append("")
        lines.append("| Command | Description |")
        lines.append("|---------|-------------|")
        for cmd_name, cmd in root_cmds:
            help_text = cmd.help.split("\n")[0].strip() if cmd.help else ""
            lines.append(
                f"| [`{cmd_name}`](root-commands.md#{PROJECT_SLUG}-{cmd_name}) | {help_text} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    click_app = get_click_app()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    groups = []
    for cmd_name in sorted(click_app.commands):
        cmd = click_app.commands[cmd_name]
        if getattr(cmd, "hidden", False) or cmd_name in HIDDEN_COMMANDS:
            continue
        if hasattr(cmd, "commands") and cmd.commands:
            groups.append(cmd_name)
            page = render_group_page(cmd, cmd_name)
            out_path = DOCS_DIR / f"{cmd_name}.md"
            out_path.write_text(page)
            print(f"  wrote {out_path.relative_to(DOCS_DIR.parent.parent)}")

    # Root commands page
    root_page = render_root_commands(click_app)
    root_path = DOCS_DIR / "root-commands.md"
    root_path.write_text(root_page)
    print(f"  wrote {root_path.relative_to(DOCS_DIR.parent.parent)}")

    # Index
    index_page = render_index(click_app, groups)
    index_path = DOCS_DIR / "index.md"
    index_path.write_text(index_page)
    print(f"  wrote {index_path.relative_to(DOCS_DIR.parent.parent)}")

    print(f"\nGenerated {len(groups) + 2} files in docs/cli/")


if __name__ == "__main__":
    main()
