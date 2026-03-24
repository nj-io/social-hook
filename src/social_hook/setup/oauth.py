"""OAuth 2.0 PKCE flow — multi-platform.

Reusable module that can be called from the setup wizard or standalone script.
Starts a local callback server, opens browser to authorization,
waits for callback, exchanges code for tokens, saves to DB.

The OAUTH_PLATFORMS registry is the single source of truth for which platforms
support OAuth 2.0 PKCE and their endpoint configuration.
"""

import base64
import hashlib
import http.server
import secrets
import threading
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from social_hook.adapters.auth import _DT_FORMAT
from social_hook.adapters.auth import save_tokens as save_tokens_to_db
from social_hook.db.connection import init_database
from social_hook.filesystem import get_db_path

# ---------------------------------------------------------------------------
# Platform registry
# ---------------------------------------------------------------------------


@dataclass
class OAuthPlatformConfig:
    """Configuration for a platform's OAuth 2.0 PKCE endpoints."""

    auth_url: str
    token_url: str
    scopes: str
    default_port: int  # for CLI callback server


OAUTH_PLATFORMS: dict[str, OAuthPlatformConfig] = {
    "x": OAuthPlatformConfig(
        auth_url="https://x.com/i/oauth2/authorize",
        token_url="https://api.x.com/2/oauth2/token",
        scopes="tweet.read tweet.write users.read media.write offline.access",
        default_port=4000,
    ),
    "linkedin": OAuthPlatformConfig(
        auth_url="https://www.linkedin.com/oauth/v2/authorization",
        token_url="https://www.linkedin.com/oauth/v2/accessToken",
        scopes="openid profile w_member_social",
        default_port=4001,
    ),
}

# Legacy module-level constants (kept for any direct importers)
SCOPES = OAUTH_PLATFORMS["x"].scopes
AUTH_URL = OAUTH_PLATFORMS["x"].auth_url
TOKEN_URL = OAUTH_PLATFORMS["x"].token_url


# ---------------------------------------------------------------------------
# Token validation per platform
# ---------------------------------------------------------------------------

_VALIDATION_ENDPOINTS: dict[str, dict] = {
    "x": {
        "url": "https://api.x.com/2/users/me",
        "extract_username": lambda data: data.get("data", {}).get("username", ""),
    },
    "linkedin": {
        "url": "https://api.linkedin.com/v2/userinfo",
        "extract_username": lambda data: data.get("name", "") or data.get("email", ""),
    },
}


def validate_token(platform: str, access_token: str) -> str:
    """Validate an access token by calling the platform's user-info endpoint.

    Returns:
        Username/display-name string on success, empty string on failure.
    """
    endpoint = _VALIDATION_ENDPOINTS.get(platform)
    if not endpoint:
        return ""
    try:
        resp = requests.get(
            endpoint["url"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return str(endpoint["extract_username"](resp.json()))
    except Exception:
        pass  # Non-fatal
    return ""


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def _build_auth_url(
    client_id: str,
    state: str,
    code_challenge: str,
    redirect_uri: str,
    *,
    platform: str = "x",
) -> str:
    """Build the authorization URL for the given platform."""
    config = OAUTH_PLATFORMS.get(platform)
    if config is None:
        raise ValueError(f"Unknown OAuth platform: {platform}")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": config.scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{config.auth_url}?{urllib.parse.urlencode(params)}"


def _exchange_code(
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    *,
    platform: str = "x",
) -> requests.Response:
    """Exchange authorization code for access token."""
    config = OAUTH_PLATFORMS.get(platform)
    if config is None:
        raise ValueError(f"Unknown OAuth platform: {platform}")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    if client_secret:
        auth = (client_id, client_secret)
    else:
        data["client_id"] = client_id
        auth = None

    return requests.post(config.token_url, data=data, auth=auth, timeout=30)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback."""

    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/callback":
            _CallbackHandler.code = params.get("code", [None])[0]
            _CallbackHandler.state = params.get("state", [None])[0]
            _CallbackHandler.error = params.get("error", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()

            if _CallbackHandler.code:
                self.wfile.write(
                    b"<h1>Authorization successful!</h1>"
                    b"<p>You can close this tab and return to the terminal.</p>"
                )
            else:
                error_desc = params.get("error_description", ["Unknown error"])[0]
                self.wfile.write(f"<h1>Authorization failed</h1><p>{error_desc}</p>".encode())

            # Shutdown server after handling
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress default logging


def _save_tokens(
    access_token: str,
    refresh_token: str | None = None,
    expires_in: int = 7200,
    *,
    platform: str = "x",
) -> None:
    """Save OAuth 2.0 tokens to the social-hook database."""
    db_path = get_db_path()
    init_database(db_path)

    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).strftime(_DT_FORMAT)
    save_tokens_to_db(
        str(db_path), platform, platform, access_token, refresh_token or "", expires_at
    )


def run_pkce_flow(
    platform: str,
    client_id: str,
    client_secret: str,
    port: int | None = None,
) -> dict:
    """Run the full OAuth 2.0 PKCE flow for any supported platform.

    Starts a local callback server, opens browser to authorization,
    waits for callback, exchanges code for tokens, saves to DB.

    Args:
        platform: Platform key (must be in OAUTH_PLATFORMS).
        client_id: OAuth 2.0 client ID.
        client_secret: OAuth 2.0 client secret.
        port: Local callback server port (defaults to platform's default_port).

    Returns:
        Dict with access_token, refresh_token, expires_in, username.

    Raises:
        ValueError: If platform is not in OAUTH_PLATFORMS.
        RuntimeError: On authorization or token exchange failure.
    """
    config = OAUTH_PLATFORMS.get(platform)
    if config is None:
        raise ValueError(f"Unknown OAuth platform: {platform}")

    if port is None:
        port = config.default_port

    redirect_uri = f"http://localhost:{port}/callback"

    # Reset handler state (in case of re-use)
    _CallbackHandler.code = None
    _CallbackHandler.state = None
    _CallbackHandler.error = None

    # 1. Generate PKCE verifier/challenge
    code_verifier, code_challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)

    # 2. Build the auth URL
    auth_url = _build_auth_url(client_id, state, code_challenge, redirect_uri, platform=platform)

    # 3. Print the URL with copy support
    from social_hook.terminal import copy_to_clipboard

    try:
        from rich.console import Console
        from rich.panel import Panel

        Console().print(
            Panel(
                f"Open this URL in your browser to authorize:\n[link={auth_url}]{auth_url}[/link]",
                border_style="cyan",
            )
        )
    except Exception:
        print("\n  Open this URL in your browser to authorize:\n")
        print(f"  \033[4m{auth_url}\033[0m\n")

    # 4. Start HTTP callback server in background thread
    server = http.server.HTTPServer(("", port), _CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # 5. Wait for callback — user can press [c] to copy URL while waiting
    import select
    import sys
    import termios
    import time
    import tty

    prompt = "  [c] copy URL  — Waiting for browser authorization..."
    print(prompt, end="", flush=True)

    if sys.stdin.isatty():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)  # cbreak mode: keypresses delivered immediately, no echo
            while server_thread.is_alive():
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if ready:
                    ch = sys.stdin.read(1)
                    if ch == "c":
                        if copy_to_clipboard(auth_url):
                            print("\r\033[2K  Copied to clipboard!", end="", flush=True)
                        else:
                            print("\r\033[2K  (clipboard not available)", end="", flush=True)
                        time.sleep(0.8)
                        print(f"\r\033[2K{prompt}", end="", flush=True)
                    elif ch == "\x03":  # Ctrl+C
                        raise KeyboardInterrupt
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    else:
        # Non-TTY: just wait
        server_thread.join(timeout=300)

    print("\r\033[2K", end="")  # clear the waiting line
    server.server_close()

    # Process result
    if _CallbackHandler.error:
        raise RuntimeError(f"Authorization failed: {_CallbackHandler.error}")

    if not _CallbackHandler.code:
        raise RuntimeError("No authorization code received")

    if _CallbackHandler.state != state:
        raise RuntimeError("State mismatch — possible CSRF attack")

    # 6. Exchange code for tokens
    resp = _exchange_code(
        _CallbackHandler.code,
        code_verifier,
        client_id,
        client_secret,
        redirect_uri,
        platform=platform,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed: HTTP {resp.status_code} — {resp.text[:200]}")

    tokens = resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 7200)

    # 7. Save tokens to DB
    _save_tokens(access_token, refresh_token, expires_in, platform=platform)

    # 8. Validate token
    username = validate_token(platform, access_token) or "unknown"

    # 9. Return the result dict
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "username": username,
    }


# Backward-compat wrapper
def run_x_pkce_flow(client_id: str, client_secret: str, port: int = 4000) -> dict:
    """Run OAuth 2.0 PKCE flow for X. Thin wrapper around run_pkce_flow."""
    return run_pkce_flow("x", client_id, client_secret, port)
