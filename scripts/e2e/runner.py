"""E2E test runner — runs scenarios and collects results."""

import time
import traceback
from pathlib import Path

from e2e.constants import rate_limit_cooldown


def file_link(path: str) -> str:
    """Return an OSC 8 clickable file:// hyperlink for terminal emulators."""
    p = Path(path)
    uri = p.as_uri() if p.is_absolute() else Path.cwd().joinpath(p).as_uri()
    return f"\033]8;;{uri}\033\\{p.name}\033]8;;\033\\"


class E2ERunner:
    """Runs E2E scenarios and collects results."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[tuple[str, str, bool, str]] = []  # (id, name, passed, detail)
        self.review_items: list[dict] = []  # For human review report
        self.total_cost = 0.0
        self.start_time = 0.0
        self._harness = None
        self._only_scenario: str | None = None  # e.g. "C13" to run only that scenario
        self._fixture_loaded: str | None = None  # Name of auto-loaded fixture

    def run_scenario(
        self,
        scenario_id: str,
        name: str,
        fn,
        *args,
        llm_call: bool = False,
        isolate: bool = False,
        **kwargs,
    ):
        """Run a single scenario, catching exceptions."""
        if self._only_scenario and scenario_id.upper() != self._only_scenario.upper():
            return
        if isolate and self._harness:
            self._harness.clean_scenario_state()
        print(f"\n  [{scenario_id}] {name}")
        passed = True
        try:
            detail = fn(*args, **kwargs)
            if detail is None:
                detail = ""
            self.results.append((scenario_id, name, True, detail))
            print(f"       OK  {detail}" if detail else "       OK")
        except AssertionError as e:
            detail = str(e)
            self.results.append((scenario_id, name, False, detail))
            print(f"       FAIL  {detail}")
            if self.verbose:
                traceback.print_exc()
            passed = False
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            self.results.append((scenario_id, name, False, detail))
            print(f"       FAIL  {detail}")
            if self.verbose:
                traceback.print_exc()
            passed = False
        if llm_call and passed:
            rate_limit_cooldown()

    def add_review_item(self, scenario_id: str, **kwargs):
        """Add an item for human review."""
        self.review_items.append({"scenario_id": scenario_id, **kwargs})

    def print_summary(self):
        """Print results summary."""
        elapsed = time.time() - self.start_time
        passed = sum(1 for _, _, ok, _ in self.results if ok)
        total = len(self.results)

        print("\n" + "=" * 60)
        print("  Results:")
        for sid, name, ok, detail in self.results:
            status = "PASS" if ok else "FAIL"
            print(f"    {status}  [{sid}] {name}")
            if not ok and detail:
                print(f"           {detail}")

        print("=" * 60)
        if passed == total:
            print(f"  All checks passed: {passed}/{total}  |  Time: {elapsed:.0f}s")
        else:
            print(f"  {passed}/{total} passed, {total - passed} failed  |  Time: {elapsed:.0f}s")
        print("=" * 60)

    def print_review_report(self):
        """Print human review report."""
        if not self.review_items:
            return

        print("\n" + "=" * 60)
        print("  HUMAN REVIEW REPORT")
        print("  Review these for quality — structural checks passed.")
        print("=" * 60)

        for item in self.review_items:
            print(f"\n  [{item['scenario_id']}] {item.get('title', '')}")
            if "decision" in item:
                print(f"       Decision: {item['decision']}")
            if "episode_type" in item:
                print(
                    f"       Episode: {item['episode_type']} | Category: {item.get('post_category', 'N/A')}"
                )
            if "reasoning" in item:
                print("       Reasoning:")
                for line in item["reasoning"].split("\n"):
                    print(f"         {line}")
            if "draft_content" in item:
                content = item["draft_content"]
                print("       Draft:")
                print("       " + "-" * 40)
                for line in content.split("\n"):
                    print(f"       {line}")
                print("       " + "-" * 40)
            if "decisions" in item:
                for di, dec in enumerate(item["decisions"]):
                    print(
                        f"       Decision {di + 1}: {dec.get('decision', '?')} "
                        f"(category={dec.get('post_category', 'N/A')}, "
                        f"episode={dec.get('episode_type', 'N/A')})"
                    )
                    if dec.get("reasoning"):
                        print("         Reasoning:")
                        for line in dec["reasoning"].split("\n"):
                            print(f"           {line}")
            if "response" in item:
                resp = item["response"]
                if len(resp) > 200:
                    print("       Response:")
                    for line in resp.split("\n"):
                        print(f"         {line}")
                else:
                    print(f'       Response: "{resp}"')
            if "media_paths" in item and item["media_paths"]:
                print("       Media:")
                for mp in item["media_paths"]:
                    if Path(mp).exists():
                        print(f"         {file_link(mp)}")
                    else:
                        print(f"         {mp} (cleaned up)")
            if "review_question" in item:
                print(f"       ^ {item['review_question']}")

        print("\n" + "=" * 60)
        print(f"  Review items: {len(self.review_items)}")
        print("=" * 60)

    @property
    def all_passed(self) -> bool:
        return all(ok for _, _, ok, _ in self.results)
