#!/usr/bin/env python3
"""OAuth 2.0 PKCE flow for X API — one-time setup to get user access token.

Usage:
    python scripts/oauth2_setup.py

Prerequisites:
    - X Developer App with OAuth 2.0 enabled
    - Callback URL set to http://localhost:3000/callback in X Developer Portal
    - Client ID in ~/.social-hook/.env as X_CLIENT_ID

The script will:
    1. Start a local server on port 3000
    2. Print an authorization URL — open it in your browser
    3. After you authorize, capture the redirect and exchange for tokens
    4. Save X_OAUTH2_ACCESS_TOKEN and X_OAUTH2_REFRESH_TOKEN to ~/.social-hook/.env
"""

import base64
import hashlib
import http.server
import os
import secrets
import sys
import threading
import urllib.parse

import requests
from dotenv import load_dotenv

ENV_PATH = os.path.expanduser("~/.social-hook/.env")
load_dotenv(ENV_PATH)

CLIENT_ID = os.environ.get("X_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("X_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:3000/callback"
PORT = 3000

SCOPES = "tweet.read tweet.write users.read media.write offline.access"

AUTH_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"


def generate_pkce():
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def build_auth_url(state, code_challenge):
    """Build the authorization URL."""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code, code_verifier):
    """Exchange authorization code for access token."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    }

    if CLIENT_SECRET:
        auth = (CLIENT_ID, CLIENT_SECRET)
    else:
        data["client_id"] = CLIENT_ID
        auth = None

    resp = requests.post(TOKEN_URL, data=data, auth=auth, timeout=30)
    return resp


def save_tokens(access_token, refresh_token=None):
    """Append OAuth 2.0 tokens to .env file."""
    # Read existing .env
    existing = ""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            existing = f.read()

    # Remove old token lines
    filtered = []
    for line in existing.splitlines():
        if not line.startswith("X_OAUTH2_ACCESS_TOKEN=") and not line.startswith(
            "X_OAUTH2_REFRESH_TOKEN="
        ):
            filtered.append(line)

    filtered.append(f"X_OAUTH2_ACCESS_TOKEN={access_token}")
    if refresh_token:
        filtered.append(f"X_OAUTH2_REFRESH_TOKEN={refresh_token}")

    with open(ENV_PATH, "w") as f:
        f.write("\n".join(filtered) + "\n")

    print(f"\nTokens saved to {ENV_PATH}")


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback."""

    code = None
    state = None
    error = None

    def do_GET(self):
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
                error_desc = params.get("error_description", ["Unknown error"])[0]
                self.wfile.write(f"<h1>Authorization failed</h1><p>{error_desc}</p>".encode())

            # Shutdown server after handling
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging


def main():
    if not CLIENT_ID:
        print("Error: X_CLIENT_ID not found in ~/.social-hook/.env")
        print("Add it: echo 'X_CLIENT_ID=your_client_id' >> ~/.social-hook/.env")
        sys.exit(1)

    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce()

    auth_url = build_auth_url(state, code_challenge)

    print("=" * 60)
    print("  X API OAuth 2.0 Setup (PKCE)")
    print("=" * 60)
    print()
    print("1. Open this URL in your browser:")
    print()
    print(f"   \033[4m{auth_url}\033[0m")
    print()
    print("2. Authorize the app when prompted")
    print("3. You'll be redirected to localhost:3000 — the script will capture it")
    print()
    print(f"   Listening on http://localhost:{PORT}/callback ...")
    print()

    # Start server
    server = http.server.HTTPServer(("", PORT), CallbackHandler)
    server.serve_forever()

    # Process result
    if CallbackHandler.error:
        print(f"\nAuthorization failed: {CallbackHandler.error}")
        sys.exit(1)

    if not CallbackHandler.code:
        print("\nNo authorization code received")
        sys.exit(1)

    if CallbackHandler.state != state:
        print("\nState mismatch — possible CSRF attack")
        sys.exit(1)

    print("Authorization code received! Exchanging for tokens...")

    resp = exchange_code(CallbackHandler.code, code_verifier)
    print(f"Token exchange: {resp.status_code}")

    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        sys.exit(1)

    tokens = resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    print(f"Access token: {access_token[:20]}...")
    if refresh_token:
        print(f"Refresh token: {refresh_token[:20]}...")
    print(f"Expires in: {tokens.get('expires_in')} seconds")
    print(f"Scopes: {tokens.get('scope')}")

    save_tokens(access_token, refresh_token)

    # Quick verification
    print("\nVerifying token with /2/users/me ...")
    me_resp = requests.get(
        "https://api.x.com/2/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if me_resp.status_code == 200:
        username = me_resp.json().get("data", {}).get("username", "unknown")
        print(f"Authenticated as: @{username}")
    else:
        print(f"Verification failed: {me_resp.status_code} {me_resp.text[:200]}")

    print("\nDone! You can now use media upload with the X adapter.")


if __name__ == "__main__":
    main()
