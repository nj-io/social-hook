"""Pipeline diagnostics — structured check results for pipeline health.

Reusable component: zero project-specific imports. Stdlib only.
Registry pattern with decorator-based check registration.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


class DiagnosticSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @classmethod
    def actionable(cls) -> frozenset[str]:
        """Severity values considered actionable (warning+)."""
        return frozenset({cls.WARNING.value, cls.ERROR.value})


@dataclass
class Diagnostic:
    """A single diagnostic check result."""

    code: str
    severity: DiagnosticSeverity
    message: str
    suggestion: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "suggestion": self.suggestion,
            "context": self.context,
        }


DiagnosticContext = dict[str, Any]
CheckFn = Callable[[DiagnosticContext], list["Diagnostic"]]


class DiagnosticRegistry:
    """Registry of diagnostic check functions.

    Checks are registered via decorator and run against a context dict.
    Each check is isolated — one failure never breaks others.
    """

    def __init__(self) -> None:
        self._checks: dict[str, CheckFn] = {}

    def register(self, code: str) -> Callable[[CheckFn], CheckFn]:
        """Decorator that registers a check function under the given code.

        Usage:
            @registry.register("my_check")
            def my_check(ctx: DiagnosticContext) -> list[Diagnostic]:
                ...
        """

        def decorator(fn: CheckFn) -> CheckFn:
            self._checks[code] = fn
            return fn

        return decorator

    def run(self, context: DiagnosticContext) -> list[Diagnostic]:
        """Run all registered checks against the context.

        Each check is wrapped in try/except — a failing check is logged
        but never prevents other checks from running.

        Returns results sorted by severity (error first, then warning, then info).
        """
        results: list[Diagnostic] = []

        for code, check_fn in self._checks.items():
            try:
                diagnostics = check_fn(context)
                results.extend(diagnostics)
            except Exception:
                logger.warning("Diagnostic check '%s' failed", code, exc_info=True)

        results.sort(key=lambda d: _SEVERITY_ORDER.get(d.severity.value, 99))

        logger.info(
            "Ran %d diagnostics, found %d issues",
            len(self._checks),
            len(results),
        )

        return results


def flex_get(obj: Any, key: str, default: Any = None) -> Any:
    """Get a value from a dict or an object attribute.

    Diagnostic checks receive context values that may be plain dicts (from
    serialized JSON) or dataclass/config objects. This helper unifies access
    so each check doesn't need an inline isinstance guard.
    """
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def flex_get_action(obj: Any) -> str | None:
    """Get a strategy action value, unwrapping enums if needed."""
    action = flex_get(obj, "action")
    result = getattr(action, "value", action)
    return str(result) if result is not None else None


def filter_actionable(diagnostics: list[dict]) -> list[dict]:
    """Return only warning+ severity diagnostics from a serialized list."""
    return [d for d in diagnostics if d.get("severity") in DiagnosticSeverity.actionable()]


def format_diagnostic_warnings(diagnostics: list[dict]) -> str:
    """Format actionable diagnostics as a text block for notifications.

    Returns an empty string if there are no actionable diagnostics.
    """
    warnings = filter_actionable(diagnostics)
    if not warnings:
        return ""
    lines = ["\n\n\u26a0\ufe0f Warnings:"]
    for d in warnings:
        lines.append(f"  \u2022 {d['message']}")
        if d.get("suggestion"):
            lines.append(f"    \u2192 {d['suggestion']}")
    return "".join(f"\n{line}" if i > 0 else line for i, line in enumerate(lines))


# Backward-compat alias — prefer DiagnosticSeverity.actionable()
ACTIONABLE_SEVERITIES = DiagnosticSeverity.actionable()

diagnostics_registry = DiagnosticRegistry()
