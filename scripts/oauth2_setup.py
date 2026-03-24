#!/usr/bin/env python3
"""OAuth 2.0 PKCE flow for X API — one-time setup to get user access token.

Usage:
    python scripts/oauth2_setup.py

Prerequisites:
    - X Developer App with OAuth 2.0 enabled
    - Callback URL set to http://localhost:4000/callback in X Developer Portal
    - Client ID in ~/.social-hook/.env as X_CLIENT_ID

The script will:
    1. Start a local server on port 4000
    2. Print an authorization URL — open it in your browser
    3. After you authorize, capture the redirect and exchange for tokens
    4. Save tokens to the social-hook database (oauth_tokens table)
"""

import os
import sys

from dotenv import load_dotenv

ENV_PATH = os.path.expanduser("~/.social-hook/.env")
load_dotenv(ENV_PATH)

CLIENT_ID = os.environ.get("X_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("X_CLIENT_SECRET", "")


def main():
    if not CLIENT_ID:
        print("Error: X_CLIENT_ID not found in ~/.social-hook/.env")
        print("Add it: echo 'X_CLIENT_ID=your_client_id' >> ~/.social-hook/.env")
        sys.exit(1)

    from social_hook.setup.oauth import run_x_pkce_flow

    print("=" * 60)
    print("  X API OAuth 2.0 Setup (PKCE)")
    print("=" * 60)

    try:
        result = run_x_pkce_flow(CLIENT_ID, CLIENT_SECRET)
    except RuntimeError as exc:
        print(f"\nError: {exc}")
        sys.exit(1)

    print(f"\nAccess token: {result['access_token'][:20]}...")
    if result.get("refresh_token"):
        print(f"Refresh token: {result['refresh_token'][:20]}...")
    print(f"Expires in: {result['expires_in']} seconds")
    print(f"Authenticated as: @{result['username']}")
    print("\nDone! You can now use media upload with the X adapter.")


if __name__ == "__main__":
    main()
