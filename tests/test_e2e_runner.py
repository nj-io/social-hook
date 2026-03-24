"""Tests for E2E runner scenario filtering."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# The runner lives under scripts/ and imports from e2e.constants.
# Add scripts/ to sys.path so the import chain works.
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from e2e.runner import E2ERunner  # noqa: E402


class TestScenarioFilter:
    def test_scenario_filter_none_runs_all(self):
        """No filter set — run_scenario calls the function."""
        runner = E2ERunner()
        fn = MagicMock(return_value="ok")
        runner.run_scenario("U-x-post", "Post to X", fn)
        fn.assert_called_once()
        assert len(runner.results) == 1
        assert runner.results[0][2] is True  # passed

    def test_scenario_filter_match_runs(self):
        """Filter includes the scenario ID — function runs."""
        runner = E2ERunner()
        runner._scenario_filter = {"U-x-post", "U-x-quote"}
        fn = MagicMock(return_value="ok")
        runner.run_scenario("U-x-post", "Post to X", fn)
        fn.assert_called_once()
        assert len(runner.results) == 1

    def test_scenario_filter_no_match_skips(self):
        """Filter excludes the scenario ID — function is NOT called."""
        runner = E2ERunner()
        runner._scenario_filter = {"U-x-quote"}
        fn = MagicMock(return_value="ok")
        runner.run_scenario("U-x-post", "Post to X", fn)
        fn.assert_not_called()
        assert len(runner.results) == 0
