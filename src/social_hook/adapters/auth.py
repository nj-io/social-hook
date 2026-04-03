"""OAuth 2.0 token management with automatic refresh.

Reusable module — only stdlib + requests. No social-hook-specific imports.
Uses raw sqlite3 for oauth_tokens table operations.

Token refresh is serialized via SQLite BEGIN IMMEDIATE to prevent concurrent
refresh races. The write lock is held during the HTTP refresh call intentionally:
this prevents two processes from both reading an expired token and both attempting
to refresh (the second would fail because X invalidates the old refresh token).
Lock hold time is ~200-500ms for the token endpoint call, which is acceptable
given the 5s busy_timeout and infrequent refreshes (~every 2 hours).
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

# ISO 8601 UTC format used for expires_at and updated_at
_DT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class TokenRefreshError(Exception):
    """Raised when token refresh fails."""


def get_tokens(db_path: str, account_name: str) -> dict | None:
    """Read current tokens from oauth_tokens table.

    Returns:
        Dict with access_token, refresh_token, expires_at keys, or None if not found.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM oauth_tokens WHERE account_name = ?",
            (account_name,),
        ).fetchone()
        if row is None:
            return None
        return {
            "access_token": row["access_token"],
            "refresh_token": row["refresh_token"],
            "expires_at": row["expires_at"],
        }
    finally:
        conn.close()


def save_tokens(
    db_path: str,
    account_name: str,
    platform: str,
    access_token: str,
    refresh_token: str,
    expires_at: str,
) -> None:
    """Write/update tokens in oauth_tokens table.

    Uses INSERT OR REPLACE. Explicitly sets updated_at to current UTC
    (INSERT OR REPLACE does not trigger DEFAULT clauses).
    """
    now = datetime.now(timezone.utc).strftime(_DT_FORMAT)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO oauth_tokens
               (account_name, platform, access_token, refresh_token, expires_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_name, platform, access_token, refresh_token, expires_at, now),
        )
        conn.commit()
    finally:
        conn.close()


def delete_tokens(db_path: str, account_name: str) -> bool:
    """Delete tokens for an account. Returns True if a row was deleted."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM oauth_tokens WHERE account_name = ?",
            (account_name,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def is_expired(expires_at: str, buffer_seconds: int = 60) -> bool:
    """Check if token is expired (with safety buffer).

    Args:
        expires_at: ISO 8601 UTC datetime string.
        buffer_seconds: Seconds before actual expiry to consider expired.
    """
    try:
        expiry = datetime.strptime(expires_at, _DT_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        # If we can't parse, treat as expired to force refresh
        logger.warning("Could not parse expires_at: %s", expires_at)
        return True
    now = datetime.now(timezone.utc)
    return now >= (expiry - timedelta(seconds=buffer_seconds))


def refresh_and_get_token(
    db_path: str,
    account_name: str,
    platform: str,
    *,
    client_id: str,
    client_secret: str,
    token_url: str,
) -> str:
    """Get a valid access token, refreshing if expired.

    Uses a two-phase approach: optimistic read without a write lock (common case),
    then BEGIN IMMEDIATE only when refresh is needed (serializes concurrent refreshers).

    Args:
        db_path: Path to SQLite database.
        account_name: Account identifier (pre-targets: platform name).
        platform: Platform name (e.g., "x", "linkedin").
        client_id: OAuth 2.0 client ID (app credential).
        client_secret: OAuth 2.0 client secret (app credential).
        token_url: Token endpoint URL for refresh.

    Returns:
        Valid access token string.

    Raises:
        TokenRefreshError: If no tokens exist, refresh fails, or token is revoked.
    """
    # Phase 1: optimistic read (no write lock — common case)
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM oauth_tokens WHERE account_name = ?",
            (account_name,),
        ).fetchone()
        if row is None:
            raise TokenRefreshError(
                f"No tokens found for account '{account_name}'. Run: python scripts/oauth2_setup.py"
            )
        if not is_expired(row["expires_at"]):
            return str(row["access_token"])
    finally:
        conn.close()

    # Phase 2: token expired — serialize refresh via BEGIN IMMEDIATE
    # The write lock prevents two processes from both refreshing (second would
    # invalidate the first's refresh token). Lock is held during the HTTP call.
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Re-read under lock (another process may have refreshed while we waited)
        row = conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM oauth_tokens WHERE account_name = ?",
            (account_name,),
        ).fetchone()
        if row is not None and not is_expired(row["expires_at"]):
            conn.execute("COMMIT")
            return str(row["access_token"])

        current_refresh_token = str(row["refresh_token"]) if row else ""

        logger.info("Token expired for %s, refreshing...", account_name)
        try:
            # Use Basic Auth for confidential clients (client_secret present).
            # Matches the initial code exchange in setup/oauth.py._exchange_code.
            # X rejects refresh requests with client_id/secret as form data.
            refresh_data: dict = {
                "grant_type": "refresh_token",
                "refresh_token": current_refresh_token,
            }
            if client_secret:
                refresh_auth: tuple | None = (client_id, client_secret)
            else:
                refresh_data["client_id"] = client_id
                refresh_auth = None
            response = requests.post(
                token_url,
                data=refresh_data,
                auth=refresh_auth,
                timeout=15,
            )
        except requests.RequestException as e:
            conn.execute("COMMIT")
            raise TokenRefreshError(
                f"Network error refreshing token for '{account_name}': {e}"
            ) from e

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError as e:
                conn.execute("COMMIT")
                raise TokenRefreshError(
                    f"Invalid JSON in refresh response for '{account_name}'"
                ) from e

            new_access_token: str = data.get("access_token", "")
            new_refresh_token: str = data.get("refresh_token", current_refresh_token)
            expires_in: int = data.get("expires_in", 7200)

            new_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).strftime(
                _DT_FORMAT
            )
            now = datetime.now(timezone.utc).strftime(_DT_FORMAT)

            conn.execute(
                """UPDATE oauth_tokens
                   SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = ?
                   WHERE account_name = ?""",
                (new_access_token, new_refresh_token, new_expires_at, now, account_name),
            )
            conn.execute("COMMIT")
            logger.info("Token refreshed for %s, expires %s", account_name, new_expires_at)
            return new_access_token

        # Refresh failed
        if response.status_code == 400:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {}
            error_type = error_data.get("error", "")

            if error_type == "invalid_grant":
                conn.execute(
                    "DELETE FROM oauth_tokens WHERE account_name = ?",
                    (account_name,),
                )
                conn.execute("COMMIT")
                raise TokenRefreshError(
                    f"Token revoked for account '{account_name}'. "
                    f"Re-run: python scripts/oauth2_setup.py"
                )

        # Other HTTP errors — don't delete tokens (may be transient)
        conn.execute("COMMIT")
        raise TokenRefreshError(
            f"Token refresh failed for '{account_name}': "
            f"HTTP {response.status_code} — {response.text[:200]}"
        )

    except TokenRefreshError:
        raise
    except Exception as e:
        import contextlib

        with contextlib.suppress(Exception):
            conn.execute("ROLLBACK")
        raise TokenRefreshError(
            f"Unexpected error refreshing token for '{account_name}': {e}"
        ) from e
    finally:
        conn.close()
