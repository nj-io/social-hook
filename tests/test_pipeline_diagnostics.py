"""Tests for pipeline-specific diagnostic checks."""

import social_hook.pipeline_diagnostics  # noqa: F401 — side-effect registration
from social_hook.diagnostics import DiagnosticSeverity, diagnostics_registry


def _run_check(code: str, ctx: dict) -> list:
    """Run a single check by code against the given context."""
    check_fn = diagnostics_registry._checks[code]
    return check_fn(ctx)


# =============================================================================
# draft_without_target
# =============================================================================


class TestDraftWithoutTarget:
    def test_draft_strategy_with_no_matching_target(self):
        ctx = {
            "strategies": {
                "building-public": {"action": "draft", "reason": "good commit"},
            },
            "config_targets": {
                "product-x": {"strategy": "brand-primary"},
            },
        }
        results = _run_check("draft_without_target", ctx)
        assert len(results) == 1
        assert results[0].severity == DiagnosticSeverity.INFO
        assert "building-public" in results[0].message
        assert "preview draft" in results[0].message

    def test_draft_strategy_with_matching_target(self):
        ctx = {
            "strategies": {
                "building-public": {"action": "draft"},
            },
            "config_targets": {
                "dev-x": {"strategy": "building-public"},
            },
        }
        results = _run_check("draft_without_target", ctx)
        assert results == []

    def test_skip_strategy_ignored(self):
        ctx = {
            "strategies": {
                "building-public": {"action": "skip"},
            },
            "config_targets": {},
        }
        results = _run_check("draft_without_target", ctx)
        assert results == []

    def test_enum_action_value(self):
        """Handle action as an enum-like object with .value."""

        class FakeAction:
            value = "draft"

        ctx = {
            "strategies": {
                "building-public": {"action": FakeAction()},
            },
            "config_targets": {},
        }
        results = _run_check("draft_without_target", ctx)
        assert len(results) == 1

    def test_empty_strategies(self):
        ctx = {"strategies": {}, "config_targets": {}}
        results = _run_check("draft_without_target", ctx)
        assert results == []


# =============================================================================
# no_platforms_enabled
# =============================================================================


class TestNoPlatformsEnabled:
    def test_empty_platforms(self):
        results = _run_check("no_platforms_enabled", {"config_platforms": {}})
        assert len(results) == 1
        assert results[0].severity == DiagnosticSeverity.ERROR

    def test_all_disabled(self):
        ctx = {
            "config_platforms": {
                "x": {"enabled": False},
                "linkedin": {"enabled": False},
            },
        }
        results = _run_check("no_platforms_enabled", ctx)
        assert len(results) == 1
        assert results[0].severity == DiagnosticSeverity.ERROR

    def test_one_enabled(self):
        ctx = {
            "config_platforms": {
                "x": {"enabled": True},
                "linkedin": {"enabled": False},
            },
        }
        results = _run_check("no_platforms_enabled", ctx)
        assert results == []

    def test_missing_key(self):
        results = _run_check("no_platforms_enabled", {})
        assert len(results) == 1


# =============================================================================
# no_strategies_defined
# =============================================================================


class TestNoStrategiesDefined:
    def test_targets_but_no_strategies(self):
        ctx = {"has_targets": True, "has_strategies": False}
        results = _run_check("no_strategies_defined", ctx)
        assert len(results) == 1
        assert results[0].severity == DiagnosticSeverity.WARNING

    def test_targets_with_strategies(self):
        ctx = {"has_targets": True, "has_strategies": True}
        results = _run_check("no_strategies_defined", ctx)
        assert results == []

    def test_no_targets(self):
        ctx = {"has_targets": False, "has_strategies": False}
        results = _run_check("no_strategies_defined", ctx)
        assert results == []


# =============================================================================
# target_checks (consolidated single-pass: preview_mode, unknown_account,
#                no_platform, unknown_strategy)
# =============================================================================


def _target_results_by_code(ctx: dict, code: str) -> list:
    """Run the consolidated target_checks and filter by diagnostic code."""
    return [r for r in _run_check("target_checks", ctx) if r.code == code]


class TestPreviewModeTargets:
    def test_target_without_account(self):
        ctx = {
            "config_targets": {
                "preview-x": {"strategy": "building-public"},
            },
        }
        results = _target_results_by_code(ctx, "preview_mode_targets")
        assert len(results) == 1
        assert results[0].severity == DiagnosticSeverity.INFO
        assert "preview-x" in results[0].message

    def test_target_with_account_and_creds(self):
        ctx = {
            "config_targets": {
                "prod-x": {"strategy": "brand", "account": "product"},
            },
            "accounts_with_creds": {"product"},
        }
        results = _target_results_by_code(ctx, "preview_mode_targets")
        assert results == []

    def test_target_with_account_no_creds(self):
        ctx = {
            "config_targets": {
                "prod-x": {"strategy": "brand", "account": "product"},
            },
            "accounts_with_creds": set(),
        }
        results = _target_results_by_code(ctx, "preview_mode_targets")
        assert len(results) == 1
        assert "no credentials" in results[0].message

    def test_empty_targets(self):
        results = _target_results_by_code({"config_targets": {}}, "preview_mode_targets")
        assert results == []


# =============================================================================
# hold_limit_reached
# =============================================================================


class TestHoldLimitReached:
    def test_forced(self):
        results = _run_check("hold_limit_reached", {"hold_limit_forced": True})
        assert len(results) == 1
        assert results[0].severity == DiagnosticSeverity.WARNING

    def test_not_forced(self):
        results = _run_check("hold_limit_reached", {"hold_limit_forced": False})
        assert results == []

    def test_missing_key(self):
        results = _run_check("hold_limit_reached", {})
        assert results == []


# =============================================================================
# all_strategies_skipped
# =============================================================================


class TestAllStrategiesSkipped:
    def test_all_skip(self):
        ctx = {
            "strategies": {
                "a": {"action": "skip"},
                "b": {"action": "skip"},
            },
        }
        results = _run_check("all_strategies_skipped", ctx)
        assert len(results) == 1
        assert results[0].severity == DiagnosticSeverity.INFO

    def test_one_draft(self):
        ctx = {
            "strategies": {
                "a": {"action": "skip"},
                "b": {"action": "draft"},
            },
        }
        results = _run_check("all_strategies_skipped", ctx)
        assert results == []

    def test_empty(self):
        results = _run_check("all_strategies_skipped", {"strategies": {}})
        assert results == []


# =============================================================================
# target_unknown_account
# =============================================================================


class TestTargetUnknownAccount:
    def test_unknown_account(self):
        ctx = {
            "config_targets": {
                "prod-x": {"strategy": "brand", "account": "missing-account"},
            },
            "config_accounts": {"product": {}},
        }
        results = _target_results_by_code(ctx, "target_unknown_account")
        assert len(results) == 1
        assert "missing-account" in results[0].message

    def test_known_account(self):
        ctx = {
            "config_targets": {
                "prod-x": {"strategy": "brand", "account": "product"},
            },
            "config_accounts": {"product": {}},
        }
        results = _target_results_by_code(ctx, "target_unknown_account")
        assert results == []

    def test_no_account_on_target(self):
        ctx = {
            "config_targets": {
                "preview-x": {"strategy": "brand"},
            },
            "config_accounts": {},
        }
        results = _target_results_by_code(ctx, "target_unknown_account")
        assert results == []


# =============================================================================
# target_no_platform
# =============================================================================


class TestTargetNoPlatform:
    def test_no_account_no_platform(self):
        ctx = {
            "config_targets": {
                "broken": {"strategy": "brand"},
            },
        }
        results = _target_results_by_code(ctx, "target_no_platform")
        assert len(results) == 1
        assert "broken" in results[0].message

    def test_has_account(self):
        ctx = {
            "config_targets": {
                "ok": {"strategy": "brand", "account": "prod"},
            },
        }
        results = _target_results_by_code(ctx, "target_no_platform")
        assert results == []

    def test_has_platform(self):
        ctx = {
            "config_targets": {
                "ok": {"strategy": "brand", "platform": "x"},
            },
        }
        results = _target_results_by_code(ctx, "target_no_platform")
        assert results == []


# =============================================================================
# target_unknown_strategy
# =============================================================================


class TestTargetUnknownStrategy:
    def test_unknown_strategy(self):
        ctx = {
            "config_targets": {
                "prod-x": {"strategy": "nonexistent"},
            },
            "strategies": {"building-public": {"action": "draft"}},
        }
        results = _target_results_by_code(ctx, "target_unknown_strategy")
        assert len(results) == 1
        assert "nonexistent" in results[0].message

    def test_known_strategy(self):
        ctx = {
            "config_targets": {
                "prod-x": {"strategy": "building-public"},
            },
            "strategies": {"building-public": {"action": "draft"}},
        }
        results = _target_results_by_code(ctx, "target_unknown_strategy")
        assert results == []

    def test_empty_strategies(self):
        ctx = {
            "config_targets": {
                "prod-x": {"strategy": "brand"},
            },
            "strategies": {},
        }
        results = _target_results_by_code(ctx, "target_unknown_strategy")
        assert len(results) == 1


# =============================================================================
# legacy_drafting_fallback
# =============================================================================


class TestLegacyDraftingFallback:
    def test_legacy_active(self):
        results = _run_check("legacy_drafting_fallback", {"legacy_fallback": True})
        assert len(results) == 1
        assert results[0].severity == DiagnosticSeverity.WARNING

    def test_not_legacy(self):
        results = _run_check("legacy_drafting_fallback", {"legacy_fallback": False})
        assert results == []

    def test_missing_key(self):
        results = _run_check("legacy_drafting_fallback", {})
        assert results == []


# =============================================================================
# Full registry run
# =============================================================================


class TestFullRegistryRun:
    def test_run_all_checks_with_empty_context(self):
        """All checks should handle missing/empty context gracefully."""
        results = diagnostics_registry.run({})
        # Should not crash — no_platforms_enabled fires on empty config
        assert isinstance(results, list)

    def test_run_with_typical_context(self):
        """A typical context produces the expected diagnostics."""
        ctx = {
            "strategies": {
                "building-public": {"action": "draft"},
                "brand-primary": {"action": "skip"},
            },
            "config_targets": {
                "product-x": {"strategy": "brand-primary", "account": "product"},
            },
            "config_strategies": {
                "building-public": {},
                "brand-primary": {},
            },
            "config_platforms": {"x": {"enabled": True}},
            "config_accounts": {"product": {}},
            "decision_type": "draft",
            "hold_limit_forced": False,
            "has_targets": True,
            "has_strategies": True,
            "legacy_fallback": False,
        }
        results = diagnostics_registry.run(ctx)
        codes = {r.code for r in results}
        # draft_without_target should fire: building-public drafts but no target uses it
        assert "draft_without_target" in codes

    def test_all_none_values(self):
        """Context with all None values doesn't crash."""
        ctx = {
            "strategies": None,
            "config_targets": None,
            "config_strategies": None,
            "config_platforms": None,
            "config_accounts": None,
            "decision_type": None,
            "hold_limit_forced": None,
            "has_targets": None,
            "has_strategies": None,
            "legacy_fallback": None,
        }
        results = diagnostics_registry.run(ctx)
        assert isinstance(results, list)
