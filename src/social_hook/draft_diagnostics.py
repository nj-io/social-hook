"""Draft-specific diagnostic checks — computed at read time, not stored.

Registers checks on a separate DiagnosticRegistry instance. These run
when the API serves a draft and are injected into the response. Unlike
pipeline diagnostics (stored on evaluation_cycles), draft diagnostics
are always current because draft state changes through its lifecycle.

Import this module for side-effect registration.
"""

from social_hook.diagnostics import (
    Diagnostic,
    DiagnosticContext,
    DiagnosticRegistry,
    DiagnosticSeverity,
)

draft_diagnostics_registry = DiagnosticRegistry()

INFO = DiagnosticSeverity.INFO


@draft_diagnostics_registry.register("manual_posting_required")
def _check_manual_posting(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Non-auto-postable vehicle that hasn't been sent to advisory yet."""
    if not ctx.get("auto_postable") and ctx.get("status") != "advisory":
        vehicle = ctx.get("vehicle", "content")
        return [
            Diagnostic(
                code="manual_posting_required",
                severity=INFO,
                message=f"This {vehicle} requires manual posting.",
                suggestion="An advisory item will be created when approved. Review the Advisory page for next steps.",
            )
        ]
    return []


@draft_diagnostics_registry.register("advisory_created")
def _check_advisory_created(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Draft has been moved to advisory status."""
    if ctx.get("status") == "advisory":
        return [
            Diagnostic(
                code="advisory_created",
                severity=INFO,
                message="Advisory item created — this draft requires manual posting.",
                suggestion="Review the Advisory page to track and complete this item.",
            )
        ]
    return []
