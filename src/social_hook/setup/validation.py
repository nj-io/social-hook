"""API credential validation for setup wizard."""

import logging
import subprocess
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def validate_anthropic_key(api_key: str) -> tuple[bool, str]:
    """Validate an Anthropic API key by making a minimal request.

    Returns:
        (success, message) tuple
    """
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=15,
        )
        if response.status_code == 200:
            return True, "API key is valid"
        elif response.status_code == 401:
            return False, "Invalid API key"
        else:
            return False, f"API returned status {response.status_code}"
    except requests.RequestException as e:
        return False, f"Connection error: {e}"


def validate_telegram_bot(token: str) -> tuple[bool, str]:
    """Validate a Telegram Bot API token.

    Returns:
        (success, message) tuple with bot username on success
    """
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            username = data.get("result", {}).get("username", "unknown")
            return True, f"Bot @{username} is valid"
        return False, "Invalid bot token"
    except requests.RequestException as e:
        return False, f"Connection error: {e}"


def validate_x_api(
    api_key: str,
    api_secret: str,
    access_token: str,
    access_secret: str,
) -> tuple[bool, str]:
    """Validate X (Twitter) API credentials.

    Returns:
        (success, message) tuple
    """
    try:
        from requests_oauthlib import OAuth1

        auth = OAuth1(api_key, api_secret, access_token, access_secret)
        response = requests.get(
            "https://api.x.com/2/users/me",
            auth=auth,
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            username = data.get("data", {}).get("username", "unknown")
            return True, f"X account @{username} is valid"
        elif response.status_code == 401:
            return False, "Invalid X API credentials"
        else:
            return False, f"X API returned status {response.status_code}"
    except ImportError:
        return False, "requests-oauthlib not installed"
    except requests.RequestException as e:
        return False, f"Connection error: {e}"


def capture_telegram_chat_id(token: str, timeout_seconds: int = 60) -> Optional[str]:
    """Poll for a message to capture the chat ID.

    Instructs user to send a message to the bot, then captures
    the chat_id from the first incoming message.

    Returns:
        Chat ID as string, or None on timeout
    """
    import time

    start = time.time()
    offset = 0

    while time.time() - start < timeout_seconds:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 5},
                timeout=10,
            )
            if response.status_code != 200:
                continue

            data = response.json()
            results = data.get("result", [])
            for update in results:
                offset = update.get("update_id", 0) + 1
                message = update.get("message", {})
                chat_id = message.get("chat", {}).get("id")
                if chat_id:
                    return str(chat_id)
        except requests.RequestException:
            time.sleep(2)

    return None


def validate_media_gen(service: str, api_key: str) -> tuple[bool, str]:
    """Validate image generation service credentials.

    Args:
        service: Service name (e.g., "nano_banana_pro")
        api_key: API key for the service

    Returns:
        (success, message) tuple
    """
    if service == "nano_banana_pro":
        # Validate Gemini API key with a minimal request
        try:
            response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                params={"key": api_key},
                json={
                    "contents": [{"parts": [{"text": "hi"}]}],
                    "generationConfig": {"maxOutputTokens": 1},
                },
                timeout=15,
            )
            if response.status_code == 200:
                return True, "Connected"
            elif response.status_code == 400 and "API_KEY_INVALID" in response.text:
                return False, "Invalid Gemini API key"
            elif response.status_code == 403:
                return False, "API key not authorized"
            else:
                return False, f"API returned status {response.status_code}"
        except requests.RequestException as e:
            return False, f"Connection error: {e}"

    return False, f"Unknown service: {service}"


def validate_claude_cli() -> tuple[bool, str]:
    """Validate Claude CLI is installed and functional."""
    import os
    try:
        result = subprocess.run(
            ["claude", "-p", "Reply with ok",
             "--output-format", "json",
             "--json-schema", '{"type":"object","properties":{"status":{"type":"string"}},"required":["status"]}',
             "--tools", "",
             "--no-session-persistence",
             "--model", "haiku"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != "CLAUDECODE"},
        )
        if result.returncode != 0:
            return False, f"Claude CLI error: {result.stderr.strip()}"
        import json
        envelope = json.loads(result.stdout)
        if "structured_output" not in envelope:
            return False, "Claude CLI returned unexpected response format"
        return True, "Claude CLI working"
    except FileNotFoundError:
        return False, "Claude CLI not found in PATH. Install Claude Code first."
    except subprocess.TimeoutExpired:
        return False, "Claude CLI timed out (30s)"
    except Exception as e:
        return False, f"Claude CLI validation error: {e}"


def get_linkedin_auth_url(client_id: str, redirect_uri: str) -> str:
    """Generate LinkedIn OAuth authorization URL.

    Returns:
        Authorization URL for user to visit
    """
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "w_member_social openid profile",
    }
    return f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}"


def exchange_linkedin_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> tuple[bool, str]:
    """Exchange LinkedIn OAuth code for access token.

    Returns:
        (success, access_token_or_error) tuple
    """
    try:
        response = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=15,
        )
        if response.status_code == 200:
            token = response.json().get("access_token", "")
            return True, token
        return False, f"LinkedIn returned status {response.status_code}"
    except requests.RequestException as e:
        return False, f"Connection error: {e}"
