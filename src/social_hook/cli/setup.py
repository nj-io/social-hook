"""CLI setup command."""

from typing import Optional

import typer

app = typer.Typer()


@app.callback(invoke_without_command=True)
def setup(
    ctx: typer.Context,
    validate: bool = typer.Option(False, "--validate", help="Validate existing configuration only"),
    only: Optional[str] = typer.Option(None, "--only", help="Configure only a specific component (models, apikeys, voice, telegram, x, linkedin, image, scheduling)"),
):
    """Run the interactive setup wizard."""
    if ctx.invoked_subcommand is not None:
        return
    from social_hook.setup.wizard import run_wizard

    success = run_wizard(validate=validate, only=only)
    if not success:
        raise typer.Exit(1)
