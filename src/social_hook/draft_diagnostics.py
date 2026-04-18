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
from social_hook.media_tokens import extract_tokens

draft_diagnostics_registry = DiagnosticRegistry()

INFO = DiagnosticSeverity.INFO
WARNING = DiagnosticSeverity.WARNING


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


@draft_diagnostics_registry.register("partial_media_failure")
def _check_partial_media_failure(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Flag drafts where any ``media_errors[i]`` is non-null.

    Pure function: reads ``media_errors`` only, never the full draft. Runs
    for every vehicle — partial failure is a generation-layer concern, not
    a content-vehicle concern.
    """
    errors = ctx.get("media_errors") or []
    failed = [i for i, e in enumerate(errors) if e]
    if not failed:
        return []
    return [
        Diagnostic(
            code="partial_media_failure",
            severity=WARNING,
            message=f"{len(failed)} of {len(errors)} media items failed to generate",
            suggestion="Regenerate failed items or remove them before approval.",
            context={"failed_indexes": failed},
        )
    ]


@draft_diagnostics_registry.register("media_token_reference")
def _check_media_token_reference(ctx: DiagnosticContext) -> list[Diagnostic]:
    """Article-only: flag orphaned specs and broken token refs independently.

    Emits two distinct diagnostic codes (``orphaned_media_spec`` and
    ``broken_media_reference``) from one registration entry — the
    registration key is a grouping label, not a diagnostic code. Non-article
    vehicles return ``[]`` unconditionally.
    """
    if ctx.get("vehicle") != "article":
        return []
    specs = ctx.get("media_specs") or []
    content = ctx.get("content") or ""
    spec_ids = {s["id"] for s in specs if isinstance(s, dict) and s.get("id")}
    token_ids = {t.media_id for t in extract_tokens(content)}

    diagnostics: list[Diagnostic] = []
    orphans = spec_ids - token_ids
    broken = token_ids - spec_ids

    if orphans:
        orphan_indexes = [
            i for i, s in enumerate(specs) if isinstance(s, dict) and s.get("id") in orphans
        ]
        diagnostics.append(
            Diagnostic(
                code="orphaned_media_spec",
                severity=WARNING,
                message=f"{len(orphans)} media item(s) generated but not referenced in content",
                suggestion="Insert the image(s) in the article or remove the media items.",
                context={
                    "orphan_indexes": orphan_indexes,
                    "orphan_ids": sorted(orphans),
                },
            )
        )
    if broken:
        diagnostics.append(
            Diagnostic(
                code="broken_media_reference",
                severity=WARNING,
                message=f"Content references {len(broken)} media item(s) that don't exist",
                suggestion="Remove the reference(s) or add the missing media.",
                context={"broken_ids": sorted(broken)},
            )
        )
    return diagnostics
