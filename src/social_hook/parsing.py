"""Safe parsing utilities for boundary data."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_json_loads(
    text: str,
    context: str,
    default: Any = None,
) -> Any:
    """Parse JSON with contextual logging on failure.

    Args:
        text: JSON string to parse
        context: Human-readable description for error messages
            (e.g., "decision.platforms column", "web_events.data row 42")
        default: Value to return on parse failure (None if not specified)

    Returns:
        Parsed JSON value, or default on failure
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning(
            "JSON parse failed (%s): %s — %r",
            context,
            exc,
            text[:200] if isinstance(text, str) else text,
        )
        return default


def safe_int(
    value: Any,
    default: int,
    context: str,
) -> int:
    """Parse an integer from untrusted input with contextual logging.

    Args:
        value: Value to convert (string, float, etc.)
        default: Value to return on failure
        context: Human-readable description for error messages

    Returns:
        Parsed integer, or default on failure
    """
    try:
        return int(value)
    except (ValueError, TypeError) as exc:
        logger.warning("int() parse failed (%s): %s — value=%r", context, exc, value)
        return default


def enum_value(x: Any) -> Any:
    """Extract .value from enums or return unchanged. Use instead of inline _val() helpers."""
    return x.value if hasattr(x, "value") else x


def check_unknown_keys(
    data: dict,
    known_keys: set[str],
    section: str,
    *,
    strict: bool = False,
) -> None:
    """Warn about unrecognized keys in a config dict.

    Call after extracting all known keys from a config section.
    Catches typos (e.g., "scheduleing") that would otherwise be
    silently ignored with default values.

    Args:
        data: The config dict to check
        known_keys: Set of recognized key names
        section: Config section name for the warning message
        strict: If True, raise ConfigError instead of logging a warning.
            Use strict=True in API endpoints to reject invalid input.
    """
    from social_hook.errors import ConfigError

    unknown = set(data.keys()) - known_keys
    if unknown:
        msg = f"Unknown keys in {section} (typo?): {', '.join(sorted(unknown))}"
        if strict:
            raise ConfigError(msg)
        logger.warning(
            "Unknown keys in %s config (typo?): %s",
            section,
            ", ".join(sorted(unknown)),
        )
