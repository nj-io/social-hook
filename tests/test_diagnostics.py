"""Tests for the reusable diagnostics registry."""

from social_hook.diagnostics import (
    ACTIONABLE_SEVERITIES,
    Diagnostic,
    DiagnosticContext,
    DiagnosticRegistry,
    DiagnosticSeverity,
    filter_actionable,
    flex_get,
    flex_get_action,
    format_diagnostic_warnings,
)

# =============================================================================
# Registry basics
# =============================================================================


class TestRegistryRegisterAndRun:
    def test_register_and_run_returns_results(self):
        reg = DiagnosticRegistry()

        @reg.register("test_check")
        def check(ctx: DiagnosticContext) -> list[Diagnostic]:
            return [
                Diagnostic(
                    code="test_check",
                    severity=DiagnosticSeverity.WARNING,
                    message="something is wrong",
                )
            ]

        results = reg.run({})
        assert len(results) == 1
        assert results[0].code == "test_check"
        assert results[0].severity == DiagnosticSeverity.WARNING

    def test_empty_registry_returns_empty_list(self):
        reg = DiagnosticRegistry()
        results = reg.run({"key": "value"})
        assert results == []

    def test_check_receives_context(self):
        reg = DiagnosticRegistry()
        received = {}

        @reg.register("ctx_check")
        def check(ctx: DiagnosticContext) -> list[Diagnostic]:
            received.update(ctx)
            return []

        reg.run({"foo": "bar", "num": 42})
        assert received == {"foo": "bar", "num": 42}

    def test_check_returning_empty_list(self):
        reg = DiagnosticRegistry()

        @reg.register("noop")
        def check(ctx: DiagnosticContext) -> list[Diagnostic]:
            return []

        results = reg.run({})
        assert results == []

    def test_multiple_checks_combined(self):
        reg = DiagnosticRegistry()

        @reg.register("a")
        def check_a(ctx: DiagnosticContext) -> list[Diagnostic]:
            return [Diagnostic(code="a", severity=DiagnosticSeverity.INFO, message="a")]

        @reg.register("b")
        def check_b(ctx: DiagnosticContext) -> list[Diagnostic]:
            return [Diagnostic(code="b", severity=DiagnosticSeverity.WARNING, message="b")]

        results = reg.run({})
        assert len(results) == 2
        codes = {r.code for r in results}
        assert codes == {"a", "b"}


# =============================================================================
# Exception isolation
# =============================================================================


class TestExceptionIsolation:
    def test_bad_check_does_not_break_others(self):
        reg = DiagnosticRegistry()

        @reg.register("good_before")
        def good_before(ctx: DiagnosticContext) -> list[Diagnostic]:
            return [
                Diagnostic(
                    code="good_before",
                    severity=DiagnosticSeverity.INFO,
                    message="ok",
                )
            ]

        @reg.register("bad")
        def bad(ctx: DiagnosticContext) -> list[Diagnostic]:
            raise ValueError("broken check")

        @reg.register("good_after")
        def good_after(ctx: DiagnosticContext) -> list[Diagnostic]:
            return [
                Diagnostic(
                    code="good_after",
                    severity=DiagnosticSeverity.WARNING,
                    message="also ok",
                )
            ]

        results = reg.run({})
        codes = {r.code for r in results}
        assert "good_before" in codes
        assert "good_after" in codes
        assert len(results) == 2


# =============================================================================
# Severity sorting
# =============================================================================


class TestSeveritySorting:
    def test_errors_before_warnings_before_info(self):
        reg = DiagnosticRegistry()

        @reg.register("mixed")
        def check(ctx: DiagnosticContext) -> list[Diagnostic]:
            return [
                Diagnostic(code="i", severity=DiagnosticSeverity.INFO, message="info"),
                Diagnostic(code="e", severity=DiagnosticSeverity.ERROR, message="err"),
                Diagnostic(code="w", severity=DiagnosticSeverity.WARNING, message="warn"),
            ]

        results = reg.run({})
        severities = [r.severity for r in results]
        assert severities == [
            DiagnosticSeverity.ERROR,
            DiagnosticSeverity.WARNING,
            DiagnosticSeverity.INFO,
        ]


# =============================================================================
# Decorator syntax
# =============================================================================


class TestDecoratorSyntax:
    def test_decorator_returns_original_function(self):
        reg = DiagnosticRegistry()

        @reg.register("deco_test")
        def my_check(ctx: DiagnosticContext) -> list[Diagnostic]:
            return []

        # The decorated function should be the same object
        assert callable(my_check)
        assert my_check({}) == []


# =============================================================================
# Diagnostic dataclass
# =============================================================================


class TestDiagnosticDataclass:
    def test_defaults(self):
        d = Diagnostic(
            code="test",
            severity=DiagnosticSeverity.INFO,
            message="msg",
        )
        assert d.suggestion is None
        assert d.context == {}

    def test_with_all_fields(self):
        d = Diagnostic(
            code="test",
            severity=DiagnosticSeverity.ERROR,
            message="msg",
            suggestion="fix it",
            context={"key": "val"},
        )
        assert d.suggestion == "fix it"
        assert d.context == {"key": "val"}


# =============================================================================
# flex_get helper
# =============================================================================


class TestFlexGet:
    def test_dict_access(self):
        assert flex_get({"foo": "bar"}, "foo") == "bar"

    def test_dict_missing_returns_default(self):
        assert flex_get({"foo": "bar"}, "baz") is None
        assert flex_get({"foo": "bar"}, "baz", "default") == "default"

    def test_object_access(self):
        class Obj:
            foo = "bar"

        assert flex_get(Obj(), "foo") == "bar"

    def test_object_missing_returns_default(self):
        class Obj:
            pass

        assert flex_get(Obj(), "baz") is None
        assert flex_get(Obj(), "baz", "default") == "default"


class TestFlexGetAction:
    def test_dict_with_string_action(self):
        assert flex_get_action({"action": "draft"}) == "draft"

    def test_dict_with_enum_action(self):
        class FakeEnum:
            value = "skip"

        assert flex_get_action({"action": FakeEnum()}) == "skip"

    def test_dict_with_no_action(self):
        assert flex_get_action({}) is None

    def test_object_with_action(self):
        class Obj:
            action = "hold"

        assert flex_get_action(Obj()) == "hold"


# =============================================================================
# filter_actionable / format_diagnostic_warnings
# =============================================================================


class TestFilterActionable:
    def test_filters_info(self):
        items = [
            {"severity": "info", "message": "a"},
            {"severity": "warning", "message": "b"},
            {"severity": "error", "message": "c"},
        ]
        result = filter_actionable(items)
        assert len(result) == 2
        assert all(d["severity"] in ACTIONABLE_SEVERITIES for d in result)

    def test_empty_list(self):
        assert filter_actionable([]) == []


class TestFormatDiagnosticWarnings:
    def test_empty_returns_empty_string(self):
        assert format_diagnostic_warnings([]) == ""

    def test_info_only_returns_empty_string(self):
        items = [{"severity": "info", "message": "ok"}]
        assert format_diagnostic_warnings(items) == ""

    def test_formats_warning_with_suggestion(self):
        items = [
            {"severity": "warning", "message": "bad config", "suggestion": "fix it"},
        ]
        result = format_diagnostic_warnings(items)
        assert "Warnings:" in result
        assert "bad config" in result
        assert "fix it" in result

    def test_formats_without_suggestion(self):
        items = [
            {"severity": "error", "message": "broken"},
        ]
        result = format_diagnostic_warnings(items)
        assert "broken" in result
