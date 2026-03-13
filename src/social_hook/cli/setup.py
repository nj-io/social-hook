"""CLI setup command."""

import typer

app = typer.Typer()


@app.callback(invoke_without_command=True)
def setup(
    ctx: typer.Context,
    validate: bool = typer.Option(False, "--validate", help="Validate existing configuration only"),
    only: str | None = typer.Option(
        None,
        "--only",
        help="Configure only a specific component (models, apikeys, voice, telegram, platforms, x, linkedin, image, scheduling, journey, web)",
    ),
    advanced: bool | None = typer.Option(
        None,
        "--advanced/--no-advanced",
        help="Include advanced sections (models, media, scheduling, etc.)",
    ),
):
    """Run the interactive setup wizard.

    Example: social-hook setup
    Example: social-hook setup --advanced
    Example: social-hook setup --only voice
    """
    if ctx.invoked_subcommand is not None:
        return
    from social_hook.setup.wizard import run_wizard

    success = run_wizard(validate=validate, only=only, advanced=advanced)
    if not success:
        raise typer.Exit(1)
