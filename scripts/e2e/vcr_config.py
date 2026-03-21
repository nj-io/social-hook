"""VCR.py configuration for platform adapter E2E tests.

Provides credential filtering and cassette management for recording/replaying
real API interactions with platform adapters (X, LinkedIn).
"""

import re
from contextlib import contextmanager
from pathlib import Path

# Try to import vcrpy; provide helpful error if missing
try:
    import vcr
except ImportError:
    vcr = None  # type: ignore[assignment]

CASSETTE_DIR = Path(__file__).parent / "cassettes"

# Headers to scrub from recorded interactions
SENSITIVE_HEADERS = [
    "Authorization",
    "X-API-Key",
    "X-Access-Token",
]

# Patterns to scrub from response bodies
BODY_SCRUB_PATTERNS = [
    "access_token",
    "refresh_token",
    "client_secret",
]


def _scrub_headers(response):
    """Remove sensitive headers from recorded responses."""
    headers = response.get("headers", {})
    for header in SENSITIVE_HEADERS:
        # VCR stores headers as lists of values
        if header in headers:
            headers[header] = ["REDACTED"]
        if header.lower() in headers:
            headers[header.lower()] = ["REDACTED"]
    return response


def _scrub_request_headers(request):
    """Remove sensitive headers from recorded requests."""
    # Scrub OAuth/Bearer with format-preserving redaction first
    auth = request.headers.get("Authorization", "")
    auth_handled = False
    if auth.startswith("OAuth "):
        request.headers["Authorization"] = (
            "OAuth oauth_consumer_key=REDACTED, oauth_token=REDACTED, oauth_signature=REDACTED"
        )
        auth_handled = True
    elif auth.startswith("Bearer "):
        request.headers["Authorization"] = "Bearer REDACTED"
        auth_handled = True
    # Generic scrub for all sensitive headers (skip Authorization if already handled)
    for header in SENSITIVE_HEADERS:
        skip = auth_handled and header.lower() == "authorization"
        if header in request.headers and not skip:
            request.headers[header] = "REDACTED"
        if header.lower() in request.headers and not skip:
            request.headers[header.lower()] = "REDACTED"
    return request


def _scrub_response_body(response):
    """Scrub sensitive patterns from response bodies."""
    body = response.get("body", {}).get("string", b"")
    body_str = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)

    for pattern in BODY_SCRUB_PATTERNS:
        # Simple scrub: replace "access_token":"value" patterns
        body_str = re.sub(
            rf'"{pattern}"\s*:\s*"[^"]*"',
            f'"{pattern}": "REDACTED"',
            body_str,
        )

    if isinstance(response.get("body", {}).get("string"), bytes):
        response["body"]["string"] = body_str.encode("utf-8")
    elif "body" in response and "string" in response["body"]:
        response["body"]["string"] = body_str

    return response


def _before_record_response(response):
    """Process response before recording to cassette."""
    response = _scrub_headers(response)
    response = _scrub_response_body(response)
    return response


def get_record_mode(live: bool) -> str:
    """Get VCR record mode based on --live flag.

    Args:
        live: If True, record new interactions. If False, replay only.

    Returns:
        VCR record mode string.
    """
    if live:
        return "new_episodes"
    return "none"


@contextmanager
def vcr_context(platform: str, scenario_name: str, live: bool = False):
    """Context manager for VCR cassette recording/playback.

    Args:
        platform: Platform name (e.g., "x", "linkedin") -- used as subdirectory.
        scenario_name: Scenario identifier for cassette filename.
        live: If True, record new API interactions. If False, replay from cassette.

    Yields:
        VCR cassette context (or no-op if vcrpy not installed and not live).

    Raises:
        ImportError: If live=True and vcrpy is not installed.
    """
    if vcr is None:
        if live:
            raise ImportError(
                "vcrpy is required for --live mode. Install with: pip install 'social-hook[dev]'"
            )
        # In replay mode without vcrpy, warn and run without cassette replay
        import warnings

        warnings.warn(
            f"vcrpy not installed — {scenario_name} will make real API calls. "
            "Install with: pip install 'social-hook[dev]'",
            stacklevel=2,
        )
        yield None
        return

    cassette_dir = CASSETTE_DIR / platform
    cassette_dir.mkdir(parents=True, exist_ok=True)
    cassette_path = cassette_dir / f"{scenario_name}.yaml"

    record_mode = get_record_mode(live)

    my_vcr = vcr.VCR()
    my_vcr.register_matcher("method", lambda r1, r2: r1.method == r2.method)

    with my_vcr.use_cassette(
        str(cassette_path),
        record_mode=record_mode,
        before_record_request=_scrub_request_headers,
        before_record_response=_before_record_response,
        filter_headers=SENSITIVE_HEADERS,
        match_on=["method", "scheme", "host", "port", "path", "query"],
    ) as cass:
        yield cass
