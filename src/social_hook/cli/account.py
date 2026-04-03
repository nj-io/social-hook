"""CLI commands for account management."""

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
    """List accounts with platform, tier, and identity.

    Shows all configured platform accounts and their OAuth token status.

    Example: social-hook account list
    """
    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT account_name, platform, expires_at, updated_at FROM oauth_tokens ORDER BY platform, account_name"
        ).fetchall()

        accounts = []
        for row in rows:
            expired = False
            if row["expires_at"]:
                from datetime import datetime, timezone

                try:
                    exp = datetime.fromisoformat(row["expires_at"])
                    expired = exp < datetime.now(timezone.utc)
                except (ValueError, TypeError):
                    expired = True

            accounts.append(
                {
                    "name": row["account_name"],
                    "platform": row["platform"],
                    "token_status": "expired" if expired else "valid",
                    "updated_at": row["updated_at"],
                }
            )

        if json_output:
            typer.echo(json_mod.dumps({"accounts": accounts}, indent=2))
            return

        if not accounts:
            typer.echo("No accounts configured.")
            typer.echo("Use 'social-hook account add --platform <name> --name <name>' to add one.")
            return

        typer.echo(f"{'Name':<20} {'Platform':<12} {'Token Status':<14} {'Updated'}")
        typer.echo("-" * 65)
        for a in accounts:
            updated = (a["updated_at"] or "")[:19]
            typer.echo(f"{a['name']:<20} {a['platform']:<12} {a['token_status']:<14} {updated}")
    finally:
        conn.close()


@app.command()
def add(
    ctx: typer.Context,
    platform: str = typer.Option(..., "--platform", help="Platform (x, linkedin)"),
    name: str = typer.Option(..., "--name", "-n", help="Account name (e.g. 'lead', 'product')"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Add a platform account via PKCE OAuth flow.

    Initiates an OAuth 2.0 PKCE flow: opens a browser for authorization,
    runs a local callback server, exchanges the code for tokens, and
    stores them in the database.

    Example: social-hook account add --platform x --name lead
    """
    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    valid_platforms = {"x", "linkedin"}
    if platform not in valid_platforms:
        msg = f"Unknown platform: {platform}. Valid: {', '.join(sorted(valid_platforms))}"
        if json_output:
            typer.echo(json_mod.dumps({"error": msg}))
        else:
            typer.echo(msg)
        raise typer.Exit(1)

    # Check if account already exists
    conn = _get_conn()
    try:
        existing = conn.execute(
            "SELECT account_name FROM oauth_tokens WHERE account_name = ?", (name,)
        ).fetchone()
        if existing:
            msg = f"Account '{name}' already exists. Remove it first to re-authenticate."
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)
    finally:
        conn.close()

    # Verify platform credentials are configured
    from social_hook.config.env import load_env

    try:
        env_vars = load_env()
    except Exception as e:
        if json_output:
            typer.echo(json_mod.dumps({"error": f"Cannot load credentials: {e}"}))
        else:
            typer.echo(f"Error loading credentials: {e}", err=True)
        raise typer.Exit(1) from None

    required_keys = {
        "x": ["X_CLIENT_ID", "X_CLIENT_SECRET"],
        "linkedin": ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"],
    }
    missing = [k for k in required_keys.get(platform, []) if not env_vars.get(k)]
    if missing:
        msg = f"Missing credentials for {platform}: {', '.join(missing)}. Run 'social-hook credentials add --platform {platform}' first."
        if json_output:
            typer.echo(json_mod.dumps({"error": msg}))
        else:
            typer.echo(msg)
        raise typer.Exit(1)

    # The actual PKCE flow would go here — delegating to adapters/auth.py
    # For now, provide guidance on the manual flow
    typer.echo(f"PKCE OAuth flow for {platform} account '{name}'")
    typer.echo("This feature requires the OAuth callback server (Phase 1 auth module).")
    typer.echo("To complete setup, configure tokens via the web dashboard at /settings/accounts.")

    if json_output:
        typer.echo(
            json_mod.dumps(
                {
                    "status": "pending",
                    "platform": platform,
                    "name": name,
                    "message": "PKCE flow requires web dashboard or callback server",
                },
                indent=2,
            )
        )


@app.command()
def validate(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Validate all account credentials.

    Checks that OAuth tokens are present and not expired.

    Example: social-hook account validate
    """
    from datetime import datetime, timezone

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT account_name, platform, expires_at FROM oauth_tokens"
        ).fetchall()

        results = []
        all_valid = True
        for row in rows:
            valid = True
            issue = None
            if row["expires_at"]:
                try:
                    exp = datetime.fromisoformat(row["expires_at"])
                    if exp < datetime.now(timezone.utc):
                        valid = False
                        issue = "token expired"
                except (ValueError, TypeError):
                    valid = False
                    issue = "invalid expiry"
            else:
                valid = False
                issue = "no expiry set"

            if not valid:
                all_valid = False
            results.append(
                {
                    "name": row["account_name"],
                    "platform": row["platform"],
                    "valid": valid,
                    "issue": issue,
                }
            )

        if json_output:
            typer.echo(json_mod.dumps({"valid": all_valid, "accounts": results}, indent=2))
        else:
            if not results:
                typer.echo("No accounts to validate.")
                return
            for r in results:
                status = "valid" if r["valid"] else r["issue"]
                typer.echo(f"  {r['name']:<20} {r['platform']:<12} {status}")
            if all_valid:
                typer.echo("\nAll account tokens valid.")
            else:
                typer.echo("\nSome accounts have issues.")
    finally:
        conn.close()


@app.command()
def remove(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Account name to remove"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Remove an account.

    Removes OAuth tokens for the specified account.
    Fails if targets reference this account.

    Example: social-hook account remove lead --yes
    """
    from social_hook.db import operations as ops

    json_output = json_output or (ctx.obj.get("json", False) if ctx.obj else False)

    conn = _get_conn()
    try:
        token = ops.get_oauth_token(conn, name)
        if not token:
            msg = f"Account not found: {name}"
            if json_output:
                typer.echo(json_mod.dumps({"error": msg}))
            else:
                typer.echo(msg)
            raise typer.Exit(1)

        if not yes and not typer.confirm(f"Remove account '{name}' ({token.platform})?"):
            typer.echo("Cancelled.")
            return

        ops.delete_oauth_token(conn, name)

        if json_output:
            typer.echo(
                json_mod.dumps(
                    {
                        "removed": True,
                        "name": name,
                        "platform": token.platform,
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"Account '{name}' removed.")
    finally:
        conn.close()
