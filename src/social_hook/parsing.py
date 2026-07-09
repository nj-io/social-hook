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


def extract_json_object(text: str) -> dict:
    """Extract a JSON object from model text output.

    Handles raw JSON, markdown code-fenced JSON, or JSON embedded in
    surrounding text. Always returns a dict — if the parsed value is a list
    or scalar, falls through to brace-extraction to find the enclosing object.

    Used at the LLM boundary to recover structured output when a provider
    returns prose/JSON in the message body instead of a native tool call.

    Args:
        text: Raw model text output.

    Returns:
        The extracted JSON object as a dict.

    Raises:
        MalformedResponseError: If no JSON object can be extracted.
    """
    import re

    from social_hook.errors import MalformedResponseError

    text = text.strip()

    # 1. Try direct parse (must be a dict)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from a markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 3. Find outermost { ... } boundaries
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            result = json.loads(text[first_brace : last_brace + 1])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise MalformedResponseError(f"Could not extract JSON object from text: {text[:200]}")


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
    """Extract .value from an enum, or return x unchanged.

    Use at system boundaries when a value may be either an enum member
    or a plain string (e.g., LLM tool call outputs, config values).

    Args:
        x: An enum member (returns x.value) or any other value (returned as-is).

    Returns:
        The extracted value.
    """
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
