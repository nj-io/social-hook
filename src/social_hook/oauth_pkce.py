"""Generic OAuth 2.0 PKCE flow utilities.

Provides PKCE verifier/challenge generation, authorization URL building,
code-for-token exchange, and a local HTTP callback server for CLI flows.
Platform-agnostic — pass endpoint URLs and scopes as parameters.

REUSABILITY: This file has zero project-specific imports.
Only stdlib + requests. Copy-paste safe.
"""

from __future__ import annotations

import base64
import hashlib
import html
import http.server
import logging
import secrets
import threading
import urllib.parse
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class OAuthEndpoints:
    """Endpoint configuration for an OAuth 2.0 PKCE flow."""

    auth_url: str
    token_url: str
    scopes: str


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256).

    Returns:
        Tuple of (code_verifier, code_challenge).
    """
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def build_auth_url(
    endpoints: OAuthEndpoints,
    client_id: str,
    state: str,
    code_challenge: str,
    redirect_uri: str,
) -> str:
    """Build the OAuth 2.0 authorization URL with PKCE.

    Args:
        endpoints: OAuth endpoint configuration.
        client_id: OAuth client ID.
        state: Random state string for CSRF protection.
        code_challenge: PKCE S256 code challenge.
        redirect_uri: Callback URL (e.g., http://localhost:4000/callback).

    Returns:
        Full authorization URL with query parameters.
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": endpoints.scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{endpoints.auth_url}?{urllib.parse.urlencode(params)}"


def exchange_code(
    endpoints: OAuthEndpoints,
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    *,
    timeout: int = 30,
) -> requests.Response:
    """Exchange an authorization code for an access token.

    Uses HTTP Basic Auth when client_secret is provided (confidential
    client). Falls back to client_id in the body for public clients.

    Args:
        endpoints: OAuth endpoint configuration.
        code: Authorization code from the callback.
        code_verifier: PKCE code verifier.
        client_id: OAuth client ID.
        client_secret: OAuth client secret (empty string for public clients).
        redirect_uri: Same redirect_uri used in the auth request.
        timeout: HTTP request timeout in seconds.

    Returns:
        Response from the token endpoint.
    """
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

    return requests.post(endpoints.token_url, data=data, auth=auth, timeout=timeout)


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures an OAuth callback.

    Class attributes ``code``, ``state``, and ``error`` are populated
    when the callback arrives at ``/callback``. The server shuts itself
    down after handling the request.

    Reset class attributes before each flow to avoid stale state.
    """

    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/callback":
            CallbackHandler.code = params.get("code", [None])[0]
            CallbackHandler.state = params.get("state", [None])[0]
            CallbackHandler.error = params.get("error", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()

            if CallbackHandler.code:
                self.wfile.write(
                    b"<h1>Authorization successful!</h1>"
                    b"<p>You can close this tab and return to the terminal.</p>"
                )
            else:
                error_desc = html.escape(params.get("error_description", ["Unknown error"])[0])
                self.wfile.write(f"<h1>Authorization failed</h1><p>{error_desc}</p>".encode())

            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress default request logging


def start_callback_server(
    port: int,
    handler_class: type[http.server.BaseHTTPRequestHandler] | None = None,
) -> tuple[http.server.HTTPServer, threading.Thread]:
    """Start a local HTTP server for the OAuth callback.

    Args:
        port: Port to listen on.
        handler_class: Custom handler class (defaults to CallbackHandler).

    Returns:
        Tuple of (server, thread). Call server.server_close() when done.
    """
    if handler_class is None:
        handler_class = CallbackHandler

    server = http.server.HTTPServer(("", port), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
