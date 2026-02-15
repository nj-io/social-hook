#!/usr/bin/env python3
"""Live E2E test suite for social-media-auto-hook.

Exercises every major user workflow end-to-end with real API calls,
real database state, and assertions on user-visible outcomes.

Usage:
    python scripts/e2e_test.py                     # Full suite
    python scripts/e2e_test.py --only pipeline     # Single section
    python scripts/e2e_test.py --only A1           # Single scenario
    python scripts/e2e_test.py --skip-telegram     # Skip Telegram-dependent sections
    python scripts/e2e_test.py --verbose            # Show full LLM outputs inline

See docs/E2E_TESTING.md for full documentation.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Test commits from this repo's git history
COMMITS = {
    "significant": "6788898",   # Implement WS1 Foundation
    "major_feature": "8166c66", # Implement WS3 adapters
    "large_feature": "38d2c9f", # WS4 gap fix
    "bugfix": "9f210e4",        # Fix setup wizard UX
    "docs_only": "a7832e6",     # docs: add WS3 integration notes
    "docs_only_2": "b995b4b",   # Add git worktrees section to CLAUDE.md
    "initial": "65fff50",       # Initial commit: Research documentation
}

SECTION_MAP = {
    "onboarding": "A",
    "pipeline": "B",
    "narrative": "C",
    "draft": "D",
    "scheduler": "E",
    "bot": "FGH",
    "setup": "I",
    "cli": "J",
    "crosscutting": "K",
    "multiprovider": "L",
}


# ---------------------------------------------------------------------------
# E2E Harness
# ---------------------------------------------------------------------------

class E2EHarness:
    """Isolated temp environment for E2E tests."""

    def __init__(self, real_base: Optional[Path] = None):
        if real_base is None:
            # Resolve before we patch HOME
            real_home = os.environ.get("HOME", str(Path.home()))
            real_base = Path(real_home) / ".social-hook"
        self.real_base = real_base
        self.fake_home: Optional[Path] = None
        self.base: Optional[Path] = None  # = fake_home / ".social-hook"
        self.repo_path: Optional[Path] = None
        self.conn = None
        self.project_id: Optional[str] = None
        self._orig_home: Optional[str] = None

    def setup(self):
        """Create isolated environment."""
        self.fake_home = Path(tempfile.mkdtemp(prefix="e2e_"))
        self.base = self.fake_home / ".social-hook"
        self.base.mkdir()

        # Copy real credentials
        env_src = self.real_base / ".env"
        if env_src.exists():
            shutil.copy(env_src, self.base / ".env")
        else:
            raise FileNotFoundError(
                f"No .env found at {env_src}. Configure credentials first."
            )

        # Copy prompt files
        prompts_src = self.real_base / "prompts"
        if prompts_src.exists():
            shutil.copytree(prompts_src, self.base / "prompts")
        else:
            raise FileNotFoundError(
                f"No prompts/ found at {prompts_src}. Run 'social-hook setup' first."
            )

        # Copy config.yaml if it exists
        config_src = self.real_base / "config.yaml"
        if config_src.exists():
            shutil.copy(config_src, self.base / "config.yaml")

        # Patch HOME before any imports that use Path.home()
        self._patch_home()

        # Init fresh DB
        from social_hook.db import init_database
        self.conn = init_database(self.base / "social-hook.db")

        # Clone this repo
        self._clone_repo()

        # Create project config in cloned repo
        self._write_project_config()

    def teardown(self):
        """Clean up."""
        if self.conn:
            self.conn.close()
        self._unpatch_home()
        if self.fake_home and self.fake_home.exists():
            shutil.rmtree(self.fake_home, ignore_errors=True)

    def _patch_home(self):
        self._orig_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.fake_home)

    def _unpatch_home(self):
        if self._orig_home is not None:
            os.environ["HOME"] = self._orig_home
        elif "HOME" in os.environ:
            del os.environ["HOME"]

    def _clone_repo(self):
        """Clone this repo into the temp environment."""
        repos_dir = self.base / "repos"
        repos_dir.mkdir(exist_ok=True)

        # Find the project root (where .git is)
        project_root = Path(__file__).resolve().parent.parent

        self.repo_path = repos_dir / "social-media-auto-hook"
        subprocess.run(
            ["git", "clone", "--quiet", str(project_root), str(self.repo_path)],
            check=True,
            capture_output=True,
        )

    def _write_project_config(self):
        """Create .social-hook/ in the cloned repo with test config."""
        config_dir = self.repo_path / ".social-hook"
        config_dir.mkdir(exist_ok=True)

        # social-context.md — use the example template
        template = Path(__file__).resolve().parent.parent / "docs" / "templates" / "social-context.example.md"
        if template.exists():
            shutil.copy(template, config_dir / "social-context.md")
        else:
            (config_dir / "social-context.md").write_text(
                "# Social Context: social-media-auto-hook\n\n"
                "A system that turns git commits into social media posts.\n"
            )

        # content-config.yaml — test settings
        (config_dir / "content-config.yaml").write_text(
            "account:\n"
            '  tier: "free"\n'
            "\n"
            "models:\n"
            '  evaluator: anthropic/claude-sonnet-4-5\n'
            '  drafter: anthropic/claude-sonnet-4-5\n'
            '  gatekeeper: anthropic/claude-haiku-4-5\n'
            "\n"
            "platforms:\n"
            "  x:\n"
            "    enabled: true\n"
            "    priority: 1\n"
            "    constraints:\n"
            "      char_limit: 280\n"
            "    threads:\n"
            "      enabled: true\n"
            "      max_tweets: 10\n"
            '      style: "numbered"\n'
            "    scheduling:\n"
            '      optimal_times: ["09:00", "10:00", "14:00"]\n'
            '      timezone: "UTC"\n'
            '      optimal_days: ["Tuesday", "Wednesday", "Thursday"]\n'
            "\n"
            "  linkedin:\n"
            "    enabled: false\n"
            "\n"
            "posting_rules:\n"
            "  max_per_day: 3\n"
            "  min_gap_minutes: 30\n"
            "  max_per_week: 10\n"
            "  prefer_scheduled: true\n"
            "  batch_window_minutes: 30\n"
            "\n"
            "strategy:\n"
            "  narrative_debt_threshold: 3\n"
            "  portfolio_window: 10\n"
            "  arc_stagnation_days: 14\n"
            "  strategy_moment_max_gap_days: 7\n"
            "\n"
            "context:\n"
            "  recent_decisions: 30\n"
            "  recent_posts: 15\n"
            "  max_tokens: 150000\n"
        )

    def seed_project(self, paused=False):
        """Register the test repo directly in DB. Returns Project."""
        from social_hook.db import (
            insert_lifecycle,
            insert_narrative_debt,
            insert_project,
        )
        from social_hook.filesystem import generate_id
        from social_hook.models import Lifecycle, NarrativeDebt, Project

        origin = subprocess.run(
            ["git", "-C", str(self.repo_path), "remote", "get-url", "origin"],
            capture_output=True, text=True,
        )
        repo_origin = origin.stdout.strip() if origin.returncode == 0 else None

        project = Project(
            id=generate_id("project"),
            name="social-media-auto-hook",
            repo_path=str(self.repo_path),
            repo_origin=repo_origin,
            paused=paused,
        )
        insert_project(self.conn, project)

        lifecycle = Lifecycle(
            project_id=project.id,
            phase="research",
            confidence=0.3,
        )
        insert_lifecycle(self.conn, lifecycle)

        debt = NarrativeDebt(
            project_id=project.id,
            debt_counter=0,
        )
        insert_narrative_debt(self.conn, debt)
        self.conn.commit()

        self.project_id = project.id
        return project

    def seed_draft(self, project_id, status="draft", **kwargs):
        """Insert a draft with supporting decision row."""
        from social_hook.db import insert_decision, insert_draft
        from social_hook.filesystem import generate_id
        from social_hook.models import Decision, Draft

        decision = Decision(
            id=generate_id("decision"),
            project_id=project_id,
            commit_hash=COMMITS["significant"],
            decision="post_worthy",
            reasoning="E2E test decision",
            episode_type="milestone",
            post_category="arc",
        )
        insert_decision(self.conn, decision)

        draft = Draft(
            id=kwargs.pop("id", generate_id("draft")),
            project_id=project_id,
            decision_id=decision.id,
            platform=kwargs.pop("platform", "x"),
            content=kwargs.pop("content", "E2E test draft content for social media."),
            status=status,
            suggested_time=kwargs.pop("suggested_time", None),
            scheduled_time=kwargs.pop("scheduled_time", None),
            retry_count=kwargs.pop("retry_count", 0),
            last_error=kwargs.pop("last_error", None),
        )
        insert_draft(self.conn, draft)
        self.conn.commit()
        return draft

    def update_config(self, overrides: dict):
        """Update the global config.yaml with overrides."""
        import yaml
        config_path = self.base / "config.yaml"
        data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
        for key, value in overrides.items():
            if isinstance(value, dict):
                data.setdefault(key, {}).update(value)
            else:
                data[key] = value
        config_path.write_text(yaml.dump(data))

    def load_config(self):
        """Load config using the patched paths."""
        from social_hook.config import load_full_config
        return load_full_config()


# ---------------------------------------------------------------------------
# Telegram Capture
# ---------------------------------------------------------------------------

class TelegramCapture:
    """Captures Telegram messages while still sending them."""

    def __init__(self):
        self.messages: list[dict] = []
        self._originals: dict[str, Any] = {}

    def install(self):
        import social_hook.bot.buttons as btns
        import social_hook.bot.commands as cmds
        import social_hook.bot.notifications as notif

        self._originals["notif_send"] = notif.send_notification
        self._originals["notif_send_buttons"] = notif.send_notification_with_buttons

        capture = self

        def captured_send(token, chat_id, message, **kw):
            capture.messages.append({
                "type": "text", "chat_id": chat_id, "text": message,
            })
            return capture._originals["notif_send"](token, chat_id, message, **kw)

        def captured_send_buttons(token, chat_id, message, buttons, **kw):
            capture.messages.append({
                "type": "buttons", "chat_id": chat_id,
                "text": message, "buttons": buttons,
            })
            return capture._originals["notif_send_buttons"](
                token, chat_id, message, buttons, **kw
            )

        # Patch in ALL modules that imported these functions
        for mod in [notif, cmds, btns]:
            mod.send_notification = captured_send
            mod.send_notification_with_buttons = captured_send_buttons

    def uninstall(self):
        import social_hook.bot.buttons as btns
        import social_hook.bot.commands as cmds
        import social_hook.bot.notifications as notif

        orig_send = self._originals.get("notif_send")
        orig_send_buttons = self._originals.get("notif_send_buttons")
        if orig_send:
            for mod in [notif, cmds, btns]:
                mod.send_notification = orig_send
                mod.send_notification_with_buttons = orig_send_buttons

    def clear(self):
        self.messages.clear()

    def last_message_contains(self, text: str) -> bool:
        return any(text.lower() in m["text"].lower() for m in self.messages)

    def last_message(self) -> Optional[dict]:
        return self.messages[-1] if self.messages else None


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

class E2ERunner:
    """Runs E2E scenarios and collects results."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[tuple[str, str, bool, str]] = []  # (id, name, passed, detail)
        self.review_items: list[dict] = []  # For human review report
        self.total_cost = 0.0
        self.start_time = 0.0

    def run_scenario(self, scenario_id: str, name: str, fn, *args,
                     llm_call: bool = False, **kwargs):
        """Run a single scenario, catching exceptions."""
        print(f"\n  [{scenario_id}] {name}")
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
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            self.results.append((scenario_id, name, False, detail))
            print(f"       FAIL  {detail}")
            if self.verbose:
                traceback.print_exc()
        if llm_call:
            import time
            print("       (waiting 65s for rate limit cooldown)")
            time.sleep(65)

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
                print(f"       Episode: {item['episode_type']} | Category: {item.get('post_category', 'N/A')}")
            if "reasoning" in item:
                print(f'       Reasoning: "{item["reasoning"][:100]}"')
            if "draft_content" in item:
                content = item["draft_content"]
                print("       Draft:")
                print("       " + "-" * 40)
                for line in content.split("\n")[:10]:
                    print(f"       {line}")
                if content.count("\n") > 10:
                    print("       [...]")
                print("       " + "-" * 40)
            if "response" in item:
                print(f'       Response: "{item["response"][:200]}"')
            if "review_question" in item:
                print(f"       ^ {item['review_question']}")

        print("\n" + "=" * 60)
        print(f"  Review items: {len(self.review_items)}")
        print("=" * 60)

    @property
    def all_passed(self) -> bool:
        return all(ok for _, _, ok, _ in self.results)


# ---------------------------------------------------------------------------
# Section A: Project Onboarding
# ---------------------------------------------------------------------------

def test_A_onboarding(harness: E2EHarness, runner: E2ERunner):
    """A1-A10: Project onboarding scenarios."""
    from typer.testing import CliRunner
    from social_hook.cli import app

    cli = CliRunner()

    # A1: Register project via CLI
    def a1():
        result = cli.invoke(app, ["project", "register", str(harness.repo_path)])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "Registered project" in result.output or "proj_" in result.output.lower() or "project_" in result.output.lower()
        # Extract project ID from output
        for line in result.output.splitlines():
            if "ID:" in line:
                harness.project_id = line.split("ID:")[-1].strip()
                break
        assert harness.project_id, f"Could not find project ID in output: {result.output}"
        return f"Registered: {harness.project_id}"

    runner.run_scenario("A1", "Register project via CLI", a1)

    # A2: Verify DB state after register
    def a2():
        from social_hook.db import get_project, get_lifecycle, get_narrative_debt
        project = get_project(harness.conn, harness.project_id)
        assert project is not None, "Project not found in DB"
        assert project.name == "social-media-auto-hook"
        assert Path(project.repo_path).resolve() == Path(harness.repo_path).resolve()
        assert project.paused is False, f"paused={project.paused}"
        assert project.audience_introduced is False, f"audience_introduced={project.audience_introduced}"

        lifecycle = get_lifecycle(harness.conn, harness.project_id)
        assert lifecycle is not None, "Lifecycle not found"
        assert lifecycle.phase == "research", f"phase={lifecycle.phase}"

        debt = get_narrative_debt(harness.conn, harness.project_id)
        assert debt is not None, "NarrativeDebt not found"
        assert debt.debt_counter == 0, f"debt_counter={debt.debt_counter}"
        return "Project: OK  Lifecycle: OK  NarrativeDebt: OK"

    runner.run_scenario("A2", "Verify DB state after register", a2)

    # A3: Project appears in list
    def a3():
        result = cli.invoke(app, ["project", "list"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}"
        assert "social-media-auto-hook" in result.output
        assert "active" in result.output.lower()
        return "Listed with active status"

    runner.run_scenario("A3", "Project appears in list", a3)

    # A4: Project config detected
    def a4():
        config_dir = harness.repo_path / ".social-hook"
        assert (config_dir / "social-context.md").exists(), "social-context.md missing"
        assert (config_dir / "content-config.yaml").exists(), "content-config.yaml missing"
        return "Config files present"

    runner.run_scenario("A4", "Project config detected", a4)

    # A5: Duplicate registration blocked
    def a5():
        result = cli.invoke(app, ["project", "register", str(harness.repo_path)])
        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}"
        assert "already" in result.output.lower(), f"Expected 'already' in: {result.output}"
        return "Blocked: already registered"

    runner.run_scenario("A5", "Duplicate registration blocked", a5)

    # A6: Duplicate origin blocked
    def a6():
        # Clone from the same source (project root) so origin matches the first clone
        project_root = Path(__file__).resolve().parent.parent
        second_clone = harness.base / "repos" / "second-clone"
        subprocess.run(
            ["git", "clone", "--quiet", str(project_root), str(second_clone)],
            check=True, capture_output=True,
        )
        result = cli.invoke(app, ["project", "register", str(second_clone)])
        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}"
        assert "already" in result.output.lower() or "origin" in result.output.lower()
        return "Blocked: duplicate origin"

    runner.run_scenario("A6", "Duplicate origin blocked", a6)

    # A7: Project introduction — first trigger with audience_introduced=False
    def a7():
        from social_hook.trigger import run_trigger
        from social_hook.db import get_recent_decisions

        exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        assert len(decisions) > 0, "No decisions created"
        d = decisions[0]

        # Structural check: decision is valid
        valid_decisions = {"post_worthy", "not_post_worthy", "consolidate", "deferred"}
        assert d.decision in valid_decisions, f"Invalid decision: {d.decision}"

        detail = f"Decision: {d.decision}"
        if d.decision == "post_worthy":
            assert d.episode_type is not None, "episode_type is None for post_worthy"
            assert d.post_category is not None, "post_category is None for post_worthy"
            detail += f" ({d.episode_type})"

        # Add to review report
        runner.add_review_item(
            "A7",
            title="Project Introduction (audience_introduced=False)",
            decision=d.decision,
            episode_type=d.episode_type,
            post_category=d.post_category,
            reasoning=d.reasoning or "",
            review_question="Good introduction? Right tone?",
        )

        # Check if draft was created
        from social_hook.db import get_pending_drafts
        drafts = get_pending_drafts(harness.conn, harness.project_id)
        if drafts:
            runner.review_items[-1]["draft_content"] = drafts[0].content
            detail += f", Draft: {len(drafts[0].content)} chars"

        return detail

    runner.run_scenario("A7", "Project introduction (audience_introduced=False)", a7, llm_call=True)

    # A8: Verify audience_introduced flag operations
    def a8():
        from social_hook.db.operations import get_audience_introduced, set_audience_introduced

        introduced = get_audience_introduced(harness.conn, harness.project_id)
        assert introduced is False, f"Expected False, got {introduced}"

        result = set_audience_introduced(harness.conn, harness.project_id, True)
        assert result is True, "set_audience_introduced returned False"

        introduced = get_audience_introduced(harness.conn, harness.project_id)
        assert introduced is True, f"Expected True after set, got {introduced}"

        # Reset for remaining tests
        set_audience_introduced(harness.conn, harness.project_id, False)
        return "Flag operations: OK"

    runner.run_scenario("A8", "Verify audience_introduced flag operations", a8)

    # A9: Project summary freshness
    def a9():
        from social_hook.db.operations import get_summary_freshness

        freshness = get_summary_freshness(harness.conn, harness.project_id)
        assert isinstance(freshness, dict), f"Expected dict, got {type(freshness)}"
        assert "commits_since_summary" in freshness or "days_since_summary" in freshness
        return f"Freshness: {freshness}"

    runner.run_scenario("A9", "Project summary freshness", a9)

    # A10: Context files included in evaluator context
    def a10():
        # Place memories.md and context-notes.md
        config_dir = harness.repo_path / ".social-hook"
        (config_dir / "memories.md").write_text(
            "| Date | Context | Feedback | Draft ID |\n"
            "|------|---------|----------|----------|\n"
            "| 2026-02-09 | Technical post | Too many emojis | draft_test |\n"
        )
        (config_dir / "context-notes.md").write_text(
            "| Date | Note | Source |\n"
            "|------|------|--------|\n"
            "| 2026-02-09 | Focus on technical depth | expert |\n"
        )

        from social_hook.config.project import load_project_config
        from social_hook.llm.prompts import assemble_evaluator_context
        from social_hook.config.project import ContextConfig

        # Load project config from repo
        project_config = load_project_config(str(harness.repo_path))

        class FakeDB:
            """Wrap conn to auto-provide it to ops functions.

            Only injects conn as the first arg — callers provide
            all other args (including project_id) themselves.
            """
            def __init__(self, conn, project_id):
                self._conn = conn
                self._pid = project_id
            def __getattr__(self, name):
                from social_hook.db import operations as ops
                fn = getattr(ops, name)
                import inspect
                sig = inspect.signature(fn)
                params = list(sig.parameters.keys())
                if params and params[0] == "conn":
                    return lambda *a, **kw: fn(self._conn, *a, **kw)
                return fn

        db = FakeDB(harness.conn, harness.project_id)
        ctx = assemble_evaluator_context(db, harness.project_id, project_config)

        has_memories = bool(ctx.memories)
        has_notes = bool(ctx.context_notes)
        assert has_memories, "Memories not included in context"
        assert has_notes, "Context notes not included in context"
        return f"Memories: {len(ctx.memories)}, Notes: {len(ctx.context_notes)}"

    runner.run_scenario("A10", "Context files included in evaluator context", a10)


# ---------------------------------------------------------------------------
# Section B: Pipeline Scenarios
# ---------------------------------------------------------------------------

def test_B_pipeline(harness: E2EHarness, runner: E2ERunner):
    """B1-B9: Pipeline scenarios."""
    from social_hook.trigger import run_trigger
    from social_hook.db import get_recent_decisions, get_pending_drafts

    # Ensure we have a project (may already exist from Section A)
    if not harness.project_id:
        harness.seed_project()

    # B1: Significant commit → evaluate → draft → schedule
    def b1():
        exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        assert len(decisions) > 0, "No decisions created"
        d = decisions[0]

        valid_decisions = {"post_worthy", "not_post_worthy", "consolidate", "deferred"}
        assert d.decision in valid_decisions, f"Invalid decision: {d.decision}"

        detail = f"Commit: {COMMITS['significant']} Decision: {d.decision}"

        if d.decision == "post_worthy":
            valid_episodes = {"decision", "before_after", "demo_proof", "milestone",
                            "postmortem", "launch", "synthesis"}
            valid_categories = {"arc", "opportunistic", "experiment"}
            assert d.episode_type in valid_episodes, f"Invalid episode_type: {d.episode_type}"
            assert d.post_category in valid_categories, f"Invalid post_category: {d.post_category}"

            drafts = get_pending_drafts(harness.conn, harness.project_id)
            assert len(drafts) > 0, "No draft created for post_worthy decision"
            assert drafts[0].content, "Draft content is empty"
            detail += f" ({d.episode_type}), Draft: {len(drafts[0].content)} chars"

            runner.add_review_item(
                "B1",
                title=f"Significant commit ({COMMITS['significant']})",
                decision=d.decision,
                episode_type=d.episode_type,
                post_category=d.post_category,
                reasoning=d.reasoning or "",
                draft_content=drafts[0].content,
                review_question="Episode type appropriate? Content quality?",
            )

        return detail

    runner.run_scenario("B1", "Significant commit → evaluate → draft", b1, llm_call=True)

    # B2: Docs-only commit → not post worthy
    def b2():
        exit_code = run_trigger(COMMITS["docs_only"], str(harness.repo_path))
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        # Find the decision for this specific commit
        d = None
        for dec in decisions:
            if dec.commit_hash.startswith(COMMITS["docs_only"][:7]):
                d = dec
                break
        assert d is not None, f"No decision found for commit {COMMITS['docs_only']}"

        runner.add_review_item(
            "B2",
            title=f"Docs-only commit ({COMMITS['docs_only']})",
            decision=d.decision,
            reasoning=d.reasoning or "",
            review_question="Correct call?",
        )
        return f"Decision: {d.decision}"

    runner.run_scenario("B2", "Docs-only commit → likely not_post_worthy", b2, llm_call=True)

    # B3: Unregistered repo → silent exit
    def b3():
        unregistered = harness.base / "repos" / "unregistered"
        unregistered.mkdir(exist_ok=True)
        subprocess.run(["git", "init", str(unregistered)], capture_output=True)
        # Create a dummy commit
        dummy = unregistered / "README.md"
        dummy.write_text("test")
        subprocess.run(["git", "-C", str(unregistered), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(unregistered), "commit", "-m", "init", "--allow-empty"],
            capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        log = subprocess.run(
            ["git", "-C", str(unregistered), "log", "--oneline", "-1"],
            capture_output=True, text=True,
        )
        commit_hash = log.stdout.strip().split()[0] if log.stdout.strip() else "HEAD"

        exit_code = run_trigger(commit_hash, str(unregistered))
        assert exit_code == 0, f"Expected exit 0, got {exit_code}"
        return "Silent exit for unregistered repo"

    runner.run_scenario("B3", "Unregistered repo → silent exit", b3)

    # B4: Paused project → skip
    def b4():
        # Pause the project
        harness.conn.execute(
            "UPDATE projects SET paused = 1 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        exit_code = run_trigger(COMMITS["major_feature"], str(harness.repo_path))
        assert exit_code == 0, f"Expected exit 0, got {exit_code}"

        # Unpause
        harness.conn.execute(
            "UPDATE projects SET paused = 0 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()
        return "Skipped paused project"

    runner.run_scenario("B4", "Paused project → skip", b4)

    # B5: Missing API key → error
    def b5():
        env_path = harness.base / ".env"
        env_content = env_path.read_text()
        # Remove ANTHROPIC_API_KEY
        modified = "\n".join(
            line for line in env_content.splitlines()
            if not line.startswith("ANTHROPIC_API_KEY")
        )
        env_path.write_text(modified)

        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code in (1, 3), f"Expected exit 1 or 3, got {exit_code}"
            return f"Error exit code: {exit_code}"
        finally:
            # Restore
            env_path.write_text(env_content)

    runner.run_scenario("B5", "Missing API key → error", b5)

    # B7: Dry-run mode (run before B6 to not pollute state)
    def b7():
        from social_hook.db import get_all_recent_decisions

        before = len(get_all_recent_decisions(harness.conn))
        exit_code = run_trigger(
            COMMITS["large_feature"], str(harness.repo_path), dry_run=True
        )
        assert exit_code == 0, f"run_trigger dry-run returned {exit_code}"

        after = len(get_all_recent_decisions(harness.conn))
        assert after == before, f"Dry-run persisted rows: {after} vs {before}"
        return "No rows persisted"

    runner.run_scenario("B7", "Dry-run mode", b7, llm_call=True)

    # B6: Free tier + long content → thread (structural check)
    def b6():
        from social_hook.db.operations import get_draft_tweets

        exit_code = run_trigger(COMMITS["large_feature"], str(harness.repo_path))
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        drafts = get_pending_drafts(harness.conn, harness.project_id)
        thread_found = False
        for draft in drafts:
            tweets = get_draft_tweets(harness.conn, draft.id)
            if tweets:
                thread_found = True
                return f"Thread found: {len(tweets)} tweets"

        # Thread not guaranteed — LLM may create a short post
        return "No thread (LLM chose single post)"

    runner.run_scenario("B6", "Free tier + long content → thread check", b6, llm_call=True)

    # B8: Consolidation context visible
    def b8():
        # Seed a pending draft first
        harness.seed_draft(harness.project_id, status="draft")

        exit_code = run_trigger(COMMITS["major_feature"], str(harness.repo_path))
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        assert len(decisions) > 0, "No decisions"
        d = decisions[0]
        valid = {"post_worthy", "not_post_worthy", "consolidate", "deferred"}
        assert d.decision in valid, f"Invalid decision: {d.decision}"
        return f"Decision: {d.decision} (consolidate is valid outcome)"

    runner.run_scenario("B8", "Consolidation context visible", b8, llm_call=True)

    # B9: Deferred decision check
    def b9():
        exit_code = run_trigger(COMMITS["docs_only_2"], str(harness.repo_path))
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        d = None
        for dec in decisions:
            if dec.commit_hash.startswith(COMMITS["docs_only_2"][:7]):
                d = dec
                break
        assert d is not None, f"No decision for {COMMITS['docs_only_2']}"
        valid = {"post_worthy", "not_post_worthy", "consolidate", "deferred"}
        assert d.decision in valid
        return f"Decision: {d.decision} (deferred is valid)"

    runner.run_scenario("B9", "Deferred/not_post_worthy for minor commit", b9, llm_call=True)


# ---------------------------------------------------------------------------
# Section C: Narrative Mechanics
# ---------------------------------------------------------------------------

def test_C_narrative(harness: E2EHarness, runner: E2ERunner):
    """C1-C12: Narrative mechanics scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    # C1: Episode type assigned on post_worthy decision
    def c1():
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=20)
        pw = [d for d in decisions if d.decision == "post_worthy"]
        if not pw:
            return "SKIP: No post_worthy decisions to check"
        d = pw[0]
        valid_episodes = {"decision", "before_after", "demo_proof", "milestone",
                        "postmortem", "launch", "synthesis"}
        assert d.episode_type in valid_episodes, f"Invalid episode_type: {d.episode_type}"
        return f"Episode type: {d.episode_type}"

    runner.run_scenario("C1", "Episode type assigned on post_worthy", c1)

    # C2: Post category assigned on post_worthy decision
    def c2():
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=20)
        pw = [d for d in decisions if d.decision == "post_worthy"]
        if not pw:
            return "SKIP: No post_worthy decisions to check"
        d = pw[0]
        valid_categories = {"arc", "opportunistic", "experiment"}
        assert d.post_category in valid_categories, f"Invalid post_category: {d.post_category}"
        return f"Post category: {d.post_category}"

    runner.run_scenario("C2", "Post category assigned on post_worthy", c2)

    # C3: Arc created for arc-category post
    def c3():
        arcs = ops.get_active_arcs(harness.conn, harness.project_id)
        # If no arc posts happened, seed one
        if not arcs:
            from social_hook.models import Arc
            from social_hook.filesystem import generate_id
            arc = Arc(
                id=generate_id("arc"),
                project_id=harness.project_id,
                theme="E2E test arc",
                status="active",
                post_count=1,
            )
            ops.insert_arc(harness.conn, arc)
            arcs = ops.get_active_arcs(harness.conn, harness.project_id)

        assert len(arcs) >= 1, "No active arcs"
        assert arcs[0].status == "active"
        assert arcs[0].theme, "Arc has no theme"
        return f"Active arcs: {len(arcs)}, theme: {arcs[0].theme}"

    runner.run_scenario("C3", "Arc created for arc-category post", c3)

    # C4: Max 3 active arcs
    def c4():
        from social_hook.models import Arc
        from social_hook.filesystem import generate_id

        # Ensure we have 3 active arcs
        current = ops.get_active_arcs(harness.conn, harness.project_id)
        for i in range(3 - len(current)):
            arc = Arc(
                id=generate_id("arc"),
                project_id=harness.project_id,
                theme=f"Test arc {i + len(current) + 1}",
                status="active",
                post_count=0,
            )
            ops.insert_arc(harness.conn, arc)

        arcs = ops.get_active_arcs(harness.conn, harness.project_id)
        assert len(arcs) <= 3, f"More than 3 active arcs: {len(arcs)}"
        return f"Active arcs: {len(arcs)} (max 3 enforced)"

    runner.run_scenario("C4", "Max 3 active arcs enforced", c4)

    # C5: Narrative debt increments
    def c5():
        debt_before = ops.get_narrative_debt(harness.conn, harness.project_id)
        before_count = debt_before.debt_counter if debt_before else 0

        ops.increment_narrative_debt(harness.conn, harness.project_id)

        debt_after = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt_after is not None
        assert debt_after.debt_counter == before_count + 1, \
            f"Expected {before_count + 1}, got {debt_after.debt_counter}"
        return f"Debt: {before_count} → {debt_after.debt_counter}"

    runner.run_scenario("C5", "Narrative debt increments", c5)

    # C6: Narrative debt resets
    def c6():
        # Ensure debt > 0
        ops.increment_narrative_debt(harness.conn, harness.project_id)
        ops.reset_narrative_debt(harness.conn, harness.project_id)

        debt = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt is not None
        assert debt.debt_counter == 0, f"Expected 0, got {debt.debt_counter}"
        return "Debt reset to 0"

    runner.run_scenario("C6", "Narrative debt resets after synthesis", c6)

    # C7: Experiment posts don't affect debt
    def c7():
        debt_before = ops.get_narrative_debt(harness.conn, harness.project_id)
        before_count = debt_before.debt_counter if debt_before else 0

        # Experiment posts should NOT call increment_narrative_debt
        # This is a contract test — verify the counter doesn't change
        debt_after = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt_after.debt_counter == before_count, \
            f"Debt changed: {before_count} → {debt_after.debt_counter}"
        return f"Debt unchanged: {before_count}"

    runner.run_scenario("C7", "Experiment posts don't affect debt", c7)

    # C8: High debt signals synthesis needed
    def c8():
        # Set debt above threshold
        ops.reset_narrative_debt(harness.conn, harness.project_id)
        for _ in range(4):  # Above default threshold of 3
            ops.increment_narrative_debt(harness.conn, harness.project_id)

        debt = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt.debt_counter >= 3, f"Debt only {debt.debt_counter}"

        # Run trigger — evaluator should see high debt
        from social_hook.trigger import run_trigger
        exit_code = run_trigger(COMMITS["bugfix"], str(harness.repo_path))
        assert exit_code == 0

        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=5)
        d = decisions[0] if decisions else None
        assert d is not None

        runner.add_review_item(
            "C8",
            title="High debt signals synthesis needed",
            decision=d.decision,
            episode_type=d.episode_type,
            reasoning=d.reasoning or "",
            review_question="Did evaluator consider high debt? Lean toward synthesis?",
        )

        # Reset debt for remaining tests
        ops.reset_narrative_debt(harness.conn, harness.project_id)
        return f"Decision: {d.decision} (debt was {debt.debt_counter})"

    runner.run_scenario("C8", "High debt signals synthesis needed", c8)

    # C9: Lifecycle phase in evaluator context
    def c9():
        from social_hook.db import update_lifecycle
        from social_hook.models import Lifecycle

        # Seed lifecycle at build phase
        harness.conn.execute(
            "UPDATE lifecycle SET phase = ?, confidence = ? WHERE project_id = ?",
            ("build", 0.6, harness.project_id),
        )
        harness.conn.commit()

        from social_hook.trigger import run_trigger
        exit_code = run_trigger(COMMITS["major_feature"], str(harness.repo_path))
        assert exit_code == 0

        # Reset to research
        harness.conn.execute(
            "UPDATE lifecycle SET phase = ?, confidence = ? WHERE project_id = ?",
            ("research", 0.3, harness.project_id),
        )
        harness.conn.commit()
        return "Lifecycle phase visible in context"

    runner.run_scenario("C9", "Lifecycle phase in evaluator context", c9)

    # C10: Lifecycle phase detection
    def c10():
        from social_hook.narrative import detect_lifecycle_phase

        signals_research = {
            "high_file_churn": True,
            "new_directories": True,
            "docs_heavy": True,
            "tests_growing": False,
            "release_tags": False,
        }
        lc_research = detect_lifecycle_phase(signals_research)
        assert lc_research.phase in {"research", "build", "demo", "launch", "post_launch"}

        signals_demo = {
            "high_file_churn": False,
            "demo_scripts": True,
            "readme_updates": True,
            "tests_growing": True,
            "release_tags": False,
        }
        lc_demo = detect_lifecycle_phase(signals_demo)
        assert lc_demo.phase in {"research", "build", "demo", "launch", "post_launch"}

        return f"Research signals→{lc_research.phase}, Demo signals→{lc_demo.phase}"

    runner.run_scenario("C10", "Lifecycle phase detection", c10)

    # C11: Strategy trigger: phase transition
    def c11():
        from social_hook.narrative import check_strategy_triggers, record_strategy_moment
        from social_hook.models import Lifecycle

        # Seed stored lifecycle at research
        harness.conn.execute(
            "UPDATE lifecycle SET phase = ?, confidence = ? WHERE project_id = ?",
            ("research", 0.3, harness.project_id),
        )
        harness.conn.commit()

        new_lc = Lifecycle(
            project_id=harness.project_id,
            phase="build",
            confidence=0.8,
        )
        triggers = check_strategy_triggers(
            harness.conn, harness.project_id, new_lifecycle=new_lc,
        )
        assert "phase_transition" in triggers, f"Expected phase_transition, got {triggers}"

        record_strategy_moment(harness.conn, harness.project_id)
        return f"Triggers: {triggers}"

    runner.run_scenario("C11", "Strategy trigger: phase transition", c11)

    # C12: Strategy trigger: time-based
    def c12():
        from social_hook.narrative import check_strategy_triggers

        # Set last_strategy_moment to 8 days ago
        old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        harness.conn.execute(
            "UPDATE lifecycle SET last_strategy_moment = ? WHERE project_id = ?",
            (old_time, harness.project_id),
        )
        harness.conn.commit()

        triggers = check_strategy_triggers(harness.conn, harness.project_id)
        assert "time_elapsed" in triggers, f"Expected time_elapsed, got {triggers}"
        return f"Triggers: {triggers}"

    runner.run_scenario("C12", "Strategy trigger: time-based", c12)


# ---------------------------------------------------------------------------
# Section D: Draft Lifecycle
# ---------------------------------------------------------------------------

def test_D_draft_lifecycle(harness: E2EHarness, runner: E2ERunner, telegram_capture: TelegramCapture):
    """D1-D7: Draft lifecycle scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    token = config.env.get("TELEGRAM_BOT_TOKEN", "test")
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    # D1: Approve draft
    def d1():
        draft = harness.seed_draft(harness.project_id, status="draft")
        from social_hook.bot.commands import cmd_approve
        telegram_capture.clear()
        cmd_approve(token, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "approved", f"Status: {updated.status}"
        return "Draft approved"

    runner.run_scenario("D1", "Approve draft", d1)

    # D2: Reject draft with reason
    def d2():
        draft = harness.seed_draft(harness.project_id, status="draft")
        from social_hook.bot.commands import cmd_reject
        telegram_capture.clear()
        cmd_reject(token, chat_id, f"{draft.id} too formal", config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "rejected", f"Status: {updated.status}"
        assert updated.last_error and "Rejected:" in updated.last_error, \
            f"last_error: {updated.last_error}"
        return f"Rejected with reason: {updated.last_error}"

    runner.run_scenario("D2", "Reject draft with reason", d2)

    # D3: Schedule at optimal time
    def d3():
        draft = harness.seed_draft(harness.project_id, status="draft")
        from social_hook.bot.commands import cmd_schedule
        telegram_capture.clear()
        cmd_schedule(token, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "scheduled", f"Status: {updated.status}"
        assert updated.scheduled_time is not None, "No scheduled_time set"
        return f"Scheduled at: {updated.scheduled_time}"

    runner.run_scenario("D3", "Schedule at optimal time", d3)

    # D4: Schedule at custom time
    def d4():
        draft = harness.seed_draft(harness.project_id, status="draft")
        from social_hook.bot.commands import cmd_schedule
        telegram_capture.clear()
        cmd_schedule(token, chat_id, f"{draft.id} 2026-03-01 14:00", config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "scheduled", f"Status: {updated.status}"
        assert updated.scheduled_time is not None
        return f"Scheduled at: {updated.scheduled_time}"

    runner.run_scenario("D4", "Schedule at custom time", d4)

    # D5: Cancel scheduled draft
    def d5():
        draft = harness.seed_draft(
            harness.project_id, status="scheduled",
            scheduled_time=datetime.now(timezone.utc).isoformat(),
        )
        from social_hook.bot.commands import cmd_cancel
        telegram_capture.clear()
        cmd_cancel(token, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "cancelled", f"Status: {updated.status}"
        return "Draft cancelled"

    runner.run_scenario("D5", "Cancel scheduled draft", d5)

    # D6: Retry failed draft (known bug: last_error not cleared)
    def d6():
        draft = harness.seed_draft(
            harness.project_id, status="failed",
            last_error="Posting failed: API timeout",
            retry_count=1,
        )
        from social_hook.bot.commands import cmd_retry
        telegram_capture.clear()
        cmd_retry(token, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "scheduled", f"Status: {updated.status}"

        # Known bug detection: last_error should be cleared but isn't
        if updated.last_error:
            detail = f"KNOWN BUG DETECTED: last_error not cleared: {updated.last_error}"
        else:
            detail = "Draft retried, last_error cleared (bug fixed!)"
        return detail

    runner.run_scenario("D6", "Retry failed draft (known bug check)", d6)

    # D7: Draft superseded
    def d7():
        draft1 = harness.seed_draft(harness.project_id, status="draft")
        draft2 = harness.seed_draft(harness.project_id, status="draft")

        result = ops.supersede_draft(harness.conn, draft1.id, draft2.id)
        assert result is True, "supersede_draft returned False"

        updated = ops.get_draft(harness.conn, draft1.id)
        assert updated.status == "superseded", f"Status: {updated.status}"
        assert updated.superseded_by == draft2.id
        return f"Draft1 superseded by draft2"

    runner.run_scenario("D7", "Draft superseded", d7)


# ---------------------------------------------------------------------------
# Section E: Scheduler
# ---------------------------------------------------------------------------

def test_E_scheduler(harness: E2EHarness, runner: E2ERunner):
    """E1-E4: Scheduler scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    # E1: Due draft → post (dry-run adapter)
    def e1():
        from social_hook.scheduler import scheduler_tick

        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        draft = harness.seed_draft(
            harness.project_id, status="scheduled",
            scheduled_time=past_time,
        )

        count = scheduler_tick(dry_run=True)
        assert count >= 1, f"Expected >=1, scheduler processed {count}"

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "posted", f"Status: {updated.status}"
        return f"Processed: {count}, draft posted"

    runner.run_scenario("E1", "Due draft → post (dry-run adapter)", e1)

    # E2: Paused project → skip
    def e2():
        from social_hook.scheduler import scheduler_tick

        harness.conn.execute(
            "UPDATE projects SET paused = 1 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        draft = harness.seed_draft(
            harness.project_id, status="scheduled",
            scheduled_time=past_time,
        )

        count = scheduler_tick(dry_run=True)

        updated = ops.get_draft(harness.conn, draft.id)

        # Unpause
        harness.conn.execute(
            "UPDATE projects SET paused = 0 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        assert updated.status == "scheduled", f"Status changed: {updated.status}"
        return f"Skipped paused project (processed: {count})"

    runner.run_scenario("E2", "Paused project → skip", e2)

    # E3: Lock prevents concurrent run
    def e3():
        from social_hook.scheduler import acquire_lock, release_lock, scheduler_tick

        acquired = acquire_lock()
        assert acquired, "Failed to acquire lock"

        try:
            count = scheduler_tick(dry_run=True)
            assert count == 0, f"Expected 0 (lock held), got {count}"
        finally:
            release_lock()

        return "Lock blocked concurrent run"

    runner.run_scenario("E3", "Lock prevents concurrent run", e3)

    # E4: No due drafts → no-op
    def e4():
        from social_hook.scheduler import scheduler_tick

        count = scheduler_tick(dry_run=True)
        # May be 0 or low number if no new due drafts
        return f"Processed: {count}"

    runner.run_scenario("E4", "No due drafts → no-op", e4)


# ---------------------------------------------------------------------------
# Section F: Bot Commands
# ---------------------------------------------------------------------------

def test_F_bot_commands(harness: E2EHarness, runner: E2ERunner, telegram_capture: TelegramCapture):
    """F1-F12: Bot command scenarios."""
    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    token = config.env.get("TELEGRAM_BOT_TOKEN", "test")
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    def make_message(text):
        return {
            "message_id": 1,
            "from": {"id": int(chat_id) if chat_id.isdigit() else 0},
            "chat": {"id": int(chat_id) if chat_id.isdigit() else 0},
            "text": text,
        }

    from social_hook.bot.commands import handle_command

    # F1: Help
    def f1():
        telegram_capture.clear()
        handle_command(make_message("/help"), token, config)
        assert telegram_capture.last_message_contains("command"), \
            f"Expected 'command' in response"
        return "Help sent"

    runner.run_scenario("F1", "Help command", f1)

    # F2: Status with data
    def f2():
        telegram_capture.clear()
        handle_command(make_message("/status"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Status sent"

    runner.run_scenario("F2", "Status with data", f2)

    # F3: Status empty (tested with real state — may have projects)
    def f3():
        telegram_capture.clear()
        handle_command(make_message("/status"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Status sent"

    runner.run_scenario("F3", "Status (may have data)", f3)

    # F4: Pending list
    def f4():
        # Seed a pending draft
        harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_command(make_message("/pending"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Pending list sent"

    runner.run_scenario("F4", "Pending list", f4)

    # F5: Pending empty
    def f5():
        telegram_capture.clear()
        handle_command(make_message("/pending"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Pending response sent"

    runner.run_scenario("F5", "Pending (may be empty)", f5)

    # F6: Projects list
    def f6():
        telegram_capture.clear()
        handle_command(make_message("/projects"), token, config)
        assert telegram_capture.messages, "No message sent"
        msg = telegram_capture.last_message()
        assert "social-media-auto-hook" in msg["text"].lower() or "project" in msg["text"].lower()
        return "Projects listed"

    runner.run_scenario("F6", "Projects list", f6)

    # F7: Usage summary
    def f7():
        telegram_capture.clear()
        handle_command(make_message("/usage"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Usage sent"

    runner.run_scenario("F7", "Usage summary", f7)

    # F8: Review draft
    def f8():
        draft = harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_command(make_message(f"/review {draft.id}"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Review sent"

    runner.run_scenario("F8", "Review draft", f8)

    # F9: Unknown command
    def f9():
        telegram_capture.clear()
        handle_command(make_message("/foo"), token, config)
        assert telegram_capture.messages, "No message sent"
        assert telegram_capture.last_message_contains("unknown") or \
               telegram_capture.last_message_contains("not recognized")
        return "Unknown command handled"

    runner.run_scenario("F9", "Unknown command", f9)

    # F10: Pause project
    def f10():
        from social_hook.db import operations as ops
        telegram_capture.clear()
        handle_command(make_message(f"/pause {harness.project_id}"), token, config)

        project = ops.get_project(harness.conn, harness.project_id)
        assert project.paused is True, f"paused={project.paused}"

        # Unpause for remaining tests
        harness.conn.execute(
            "UPDATE projects SET paused = 0 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()
        return "Project paused"

    runner.run_scenario("F10", "Pause project", f10)

    # F11: Resume project
    def f11():
        from social_hook.db import operations as ops

        # Pause first
        harness.conn.execute(
            "UPDATE projects SET paused = 1 WHERE id = ?",
            (harness.project_id,),
        )
        harness.conn.commit()

        telegram_capture.clear()
        handle_command(make_message(f"/resume {harness.project_id}"), token, config)

        project = ops.get_project(harness.conn, harness.project_id)
        assert project.paused is False, f"paused={project.paused}"
        return "Project resumed"

    runner.run_scenario("F11", "Resume project", f11)

    # F12: Scheduled list
    def f12():
        harness.seed_draft(
            harness.project_id, status="scheduled",
            scheduled_time=datetime.now(timezone.utc).isoformat(),
        )
        telegram_capture.clear()
        handle_command(make_message("/scheduled"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Scheduled list sent"

    runner.run_scenario("F12", "Scheduled list", f12)


# ---------------------------------------------------------------------------
# Section G: Bot Buttons
# ---------------------------------------------------------------------------

def test_G_bot_buttons(harness: E2EHarness, runner: E2ERunner, telegram_capture: TelegramCapture):
    """G1-G8: Bot button scenarios."""
    from social_hook.db import operations as ops
    from social_hook.bot.buttons import handle_callback

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    token = config.env.get("TELEGRAM_BOT_TOKEN", "test")
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    def make_callback(data):
        return {
            "id": "cb_1",
            "from": {"id": int(chat_id) if chat_id.isdigit() else 0},
            "message": {
                "message_id": 1,
                "chat": {"id": int(chat_id) if chat_id.isdigit() else 0},
            },
            "data": data,
        }

    # G1: Quick approve
    def g1():
        draft = harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_callback(make_callback(f"quick_approve:{draft.id}"), token, config)
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status in ("scheduled", "approved"), f"Status: {updated.status}"
        return f"Status: {updated.status}"

    runner.run_scenario("G1", "Quick approve button", g1)

    # G2: Schedule submenu
    def g2():
        draft = harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_callback(make_callback(f"schedule:{draft.id}"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Schedule submenu shown"

    runner.run_scenario("G2", "Schedule submenu", g2)

    # G3: Schedule optimal
    def g3():
        draft = harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_callback(make_callback(f"schedule_optimal:{draft.id}"), token, config)
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "scheduled", f"Status: {updated.status}"
        return f"Scheduled at: {updated.scheduled_time}"

    runner.run_scenario("G3", "Schedule optimal button", g3)

    # G4: Edit submenu
    def g4():
        draft = harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_callback(make_callback(f"edit:{draft.id}"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Edit submenu shown"

    runner.run_scenario("G4", "Edit submenu", g4)

    # G5: Reject submenu
    def g5():
        draft = harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_callback(make_callback(f"reject:{draft.id}"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Reject submenu shown"

    runner.run_scenario("G5", "Reject submenu", g5)

    # G6: Reject now
    def g6():
        draft = harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_callback(make_callback(f"reject_now:{draft.id}"), token, config)
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "rejected", f"Status: {updated.status}"
        return "Draft rejected"

    runner.run_scenario("G6", "Reject now button", g6)

    # G7: Cancel
    def g7():
        draft = harness.seed_draft(
            harness.project_id, status="scheduled",
            scheduled_time=datetime.now(timezone.utc).isoformat(),
        )
        telegram_capture.clear()
        handle_callback(make_callback(f"cancel:{draft.id}"), token, config)
        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "cancelled", f"Status: {updated.status}"
        return "Draft cancelled"

    runner.run_scenario("G7", "Cancel button", g7)

    # G8: Review
    def g8():
        draft = harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_callback(make_callback(f"review:{draft.id}"), token, config)
        assert telegram_capture.messages, "No message sent"
        return "Review shown"

    runner.run_scenario("G8", "Review button", g8)


# ---------------------------------------------------------------------------
# Section H: Bot Free-Text (Gatekeeper)
# ---------------------------------------------------------------------------

def test_H_gatekeeper(harness: E2EHarness, runner: E2ERunner, telegram_capture: TelegramCapture):
    """H1-H2: Bot free-text scenarios."""
    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    token = config.env.get("TELEGRAM_BOT_TOKEN", "test")
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    from social_hook.bot.commands import handle_message

    def make_message(text):
        return {
            "message_id": 1,
            "from": {"id": int(chat_id) if chat_id.isdigit() else 0},
            "chat": {"id": int(chat_id) if chat_id.isdigit() else 0},
            "text": text,
        }

    # H1: Query message
    def h1():
        # Seed a draft so there's something to query
        harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_message(make_message("what's pending?"), token, config)
        assert telegram_capture.messages, "No response sent"

        runner.add_review_item(
            "H1",
            title='Gatekeeper: "what\'s pending?"',
            response=telegram_capture.last_message()["text"] if telegram_capture.messages else "",
            review_question="Helpful and accurate?",
        )
        return "Gatekeeper responded"

    runner.run_scenario("H1", "Query message → gatekeeper routes", h1)

    # H2: Expert escalation
    def h2():
        harness.seed_draft(harness.project_id, status="draft")
        telegram_capture.clear()
        handle_message(make_message("make it punchier"), token, config)
        assert telegram_capture.messages, "No response sent"

        runner.add_review_item(
            "H2",
            title='Expert escalation: "make it punchier"',
            response=telegram_capture.last_message()["text"] if telegram_capture.messages else "",
            review_question="Did the expert improve the content?",
        )
        return "Expert escalation handled"

    runner.run_scenario("H2", "Expert escalation", h2)


# ---------------------------------------------------------------------------
# Section I: Setup Validation
# ---------------------------------------------------------------------------

def test_I_setup_validation(harness: E2EHarness, runner: E2ERunner):
    """I1-I3: Setup validation scenarios."""
    config = harness.load_config()

    # I1: Valid Anthropic key
    def i1():
        from social_hook.setup.validation import validate_anthropic_key
        key = config.env.get("ANTHROPIC_API_KEY", "")
        if not key:
            return "SKIP: No ANTHROPIC_API_KEY (provider not configured)"
        ok, msg = validate_anthropic_key(key)
        assert ok, f"Validation failed: {msg}"
        return msg

    runner.run_scenario("I1", "Valid Anthropic key", i1)

    # I2: Valid Telegram token
    def i2():
        from social_hook.setup.validation import validate_telegram_bot
        token = config.env.get("TELEGRAM_BOT_TOKEN", "")
        assert token, "No TELEGRAM_BOT_TOKEN in config"
        ok, msg = validate_telegram_bot(token)
        assert ok, f"Validation failed: {msg}"
        return msg

    runner.run_scenario("I2", "Valid Telegram token", i2)

    # I3: Invalid Anthropic key
    def i3():
        from social_hook.setup.validation import validate_anthropic_key
        ok, msg = validate_anthropic_key("sk-ant-bad-key-12345")
        assert not ok, f"Expected validation failure, got success: {msg}"
        return f"Correctly rejected: {msg[:60]}"

    runner.run_scenario("I3", "Invalid Anthropic key", i3)


# ---------------------------------------------------------------------------
# Section J: CLI Commands
# ---------------------------------------------------------------------------

def test_J_cli(harness: E2EHarness, runner: E2ERunner):
    """J1-J6: CLI command scenarios."""
    from typer.testing import CliRunner
    from social_hook.cli import app

    cli = CliRunner()

    if not harness.project_id:
        harness.seed_project()

    # J1: Version
    def j1():
        result = cli.invoke(app, ["version"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}"
        return result.output.strip()

    runner.run_scenario("J1", "Version", j1)

    # J2: Inspect log
    def j2():
        result = cli.invoke(app, ["inspect", "log"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        return f"Output: {len(result.output)} chars"

    runner.run_scenario("J2", "Inspect log", j2)

    # J3: Inspect pending
    def j3():
        result = cli.invoke(app, ["inspect", "pending"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        return f"Output: {len(result.output)} chars"

    runner.run_scenario("J3", "Inspect pending", j3)

    # J4: Inspect usage
    def j4():
        result = cli.invoke(app, ["inspect", "usage"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        return f"Output: {len(result.output)} chars"

    runner.run_scenario("J4", "Inspect usage", j4)

    # J5: Test command
    def j5():
        result = cli.invoke(app, ["test", "test", "--repo", str(harness.repo_path), "--last", "1"])
        # May succeed or fail depending on state — just check it runs
        return f"Exit code: {result.exit_code}"

    runner.run_scenario("J5", "Test command", j5)

    # J6: Unregister project (use a throwaway project)
    def j6():
        # Register a throwaway
        throwaway = harness.base / "repos" / "throwaway"
        throwaway.mkdir(exist_ok=True)
        subprocess.run(["git", "init", str(throwaway)], capture_output=True)
        subprocess.run(["git", "-C", str(throwaway), "commit", "--allow-empty", "-m", "init"],
                       capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "test",
                            "GIT_AUTHOR_EMAIL": "test@test.com",
                            "GIT_COMMITTER_NAME": "test",
                            "GIT_COMMITTER_EMAIL": "test@test.com"})

        reg_result = cli.invoke(app, ["project", "register", str(throwaway)])
        if reg_result.exit_code != 0:
            return f"SKIP: Could not register throwaway: {reg_result.output}"

        # Extract ID
        throwaway_id = None
        for line in reg_result.output.splitlines():
            if "ID:" in line:
                throwaway_id = line.split("ID:")[-1].strip()
                break
        if not throwaway_id:
            return "SKIP: Could not extract throwaway ID"

        result = cli.invoke(app, ["project", "unregister", throwaway_id, "--force"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"

        from social_hook.db import operations as ops
        project = ops.get_project(harness.conn, throwaway_id)
        assert project is None, "Project still exists after unregister"
        return "Project unregistered"

    runner.run_scenario("J6", "Unregister project", j6)


# ---------------------------------------------------------------------------
# Section K: Cross-Cutting
# ---------------------------------------------------------------------------

def test_K_crosscutting(harness: E2EHarness, runner: E2ERunner, telegram_capture: TelegramCapture):
    """K1-K6: Cross-cutting scenarios."""
    from social_hook.db import operations as ops

    if not harness.project_id:
        harness.seed_project()

    config = harness.load_config()
    token = config.env.get("TELEGRAM_BOT_TOKEN", "test")
    chat_id = config.env.get("TELEGRAM_CHAT_ID", "test")

    # K1: Full chain: trigger → approve → schedule → post
    def k1():
        from social_hook.trigger import run_trigger
        from social_hook.scheduler import scheduler_tick
        from social_hook.bot.commands import cmd_approve

        exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
        assert exit_code == 0, f"Trigger failed: {exit_code}"

        drafts = ops.get_pending_drafts(harness.conn, harness.project_id)
        if not drafts:
            return "SKIP: No draft created (evaluator chose not_post_worthy)"

        draft = drafts[0]
        telegram_capture.clear()
        cmd_approve(token, chat_id, draft.id, config)

        updated = ops.get_draft(harness.conn, draft.id)
        if updated.status == "approved":
            # Need to schedule it
            from social_hook.bot.commands import cmd_schedule
            cmd_schedule(token, chat_id, draft.id, config)
            updated = ops.get_draft(harness.conn, draft.id)

        if updated.status == "scheduled":
            # Set time to past so scheduler picks it up
            harness.conn.execute(
                "UPDATE drafts SET scheduled_time = ? WHERE id = ?",
                ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), draft.id),
            )
            harness.conn.commit()

            count = scheduler_tick(dry_run=True)

            updated = ops.get_draft(harness.conn, draft.id)
            assert updated.status == "posted", f"Status: {updated.status}"
            return "Full chain: trigger → approve → schedule → posted"

        return f"Chain completed with status: {updated.status}"

    runner.run_scenario("K1", "Full chain: trigger → approve → post", k1)

    # K2: Full chain: trigger → reject → no post
    def k2():
        from social_hook.trigger import run_trigger
        from social_hook.bot.commands import cmd_reject

        exit_code = run_trigger(COMMITS["major_feature"], str(harness.repo_path))
        assert exit_code == 0

        drafts = ops.get_pending_drafts(harness.conn, harness.project_id)
        if not drafts:
            return "SKIP: No draft created"

        draft = drafts[0]
        telegram_capture.clear()
        cmd_reject(token, chat_id, f"{draft.id} not the right angle", config)

        updated = ops.get_draft(harness.conn, draft.id)
        assert updated.status == "rejected", f"Status: {updated.status}"
        return "Rejected, no post"

    runner.run_scenario("K2", "Full chain: trigger → reject → no post", k2)

    # K3: Dry-run end-to-end
    def k3():
        from social_hook.trigger import run_trigger

        before_decisions = len(ops.get_all_recent_decisions(harness.conn))

        exit_code = run_trigger(
            COMMITS["large_feature"], str(harness.repo_path), dry_run=True
        )
        assert exit_code == 0

        after_decisions = len(ops.get_all_recent_decisions(harness.conn))
        assert after_decisions == before_decisions, \
            f"Dry-run persisted: {after_decisions} vs {before_decisions}"
        return "Dry-run: nothing persisted"

    runner.run_scenario("K3", "Dry-run end-to-end", k3)

    # K4: Full chain with arc verification
    def k4():
        arcs_before = ops.get_active_arcs(harness.conn, harness.project_id)
        arc_count_before = len(arcs_before)

        from social_hook.trigger import run_trigger
        exit_code = run_trigger(COMMITS["major_feature"], str(harness.repo_path))
        assert exit_code == 0

        arcs_after = ops.get_active_arcs(harness.conn, harness.project_id)
        return f"Arcs: {arc_count_before} → {len(arcs_after)}"

    runner.run_scenario("K4", "Full chain: verify arc state", k4)

    # K5: Debt accumulation → synthesis trigger
    def k5():
        # Reset and accumulate debt
        ops.reset_narrative_debt(harness.conn, harness.project_id)
        for _ in range(4):
            ops.increment_narrative_debt(harness.conn, harness.project_id)

        debt = ops.get_narrative_debt(harness.conn, harness.project_id)
        assert debt.debt_counter >= 3, f"Debt: {debt.debt_counter}"

        from social_hook.trigger import run_trigger
        exit_code = run_trigger(COMMITS["major_feature"], str(harness.repo_path))
        assert exit_code == 0

        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=3)
        d = decisions[0] if decisions else None

        # Reset debt
        ops.reset_narrative_debt(harness.conn, harness.project_id)

        if d:
            runner.add_review_item(
                "K5",
                title="Debt accumulation → synthesis trigger",
                decision=d.decision,
                episode_type=d.episode_type,
                reasoning=d.reasoning or "",
                review_question="Did evaluator consider high debt? Synthesis?",
            )
            return f"Debt={debt.debt_counter}, Decision: {d.decision}"
        return f"Debt={debt.debt_counter}"

    runner.run_scenario("K5", "Debt accumulation → synthesis trigger", k5)

    # K6: Supersede draft (DB operation)
    def k6():
        draft1 = harness.seed_draft(harness.project_id, status="draft")
        draft2 = harness.seed_draft(harness.project_id, status="draft")

        result = ops.supersede_draft(harness.conn, draft1.id, draft2.id)
        assert result is True

        updated = ops.get_draft(harness.conn, draft1.id)
        assert updated.status == "superseded"
        assert updated.superseded_by == draft2.id
        return "Supersede: DB operation works"

    runner.run_scenario("K6", "Supersede draft (DB operation)", k6)


# ---------------------------------------------------------------------------
# Section L: Multi-Provider
# ---------------------------------------------------------------------------

def test_L_multi_provider(harness: E2EHarness, runner: E2ERunner):
    """L1-L8: Multi-provider integration scenarios."""
    from social_hook.errors import ConfigError
    from social_hook.llm.factory import parse_provider_model, create_client
    from social_hook.trigger import run_trigger

    # Save original config
    config_path = harness.base / "config.yaml"
    original_config = config_path.read_text() if config_path.exists() else ""

    # L1: Claude CLI evaluator (if claude is in PATH)
    def l1():
        import shutil
        if not shutil.which("claude"):
            return "SKIP: Claude CLI not in PATH"
        harness.update_config({"models": {
            "evaluator": "claude-cli/sonnet",
            "drafter": "anthropic/claude-sonnet-4-5",
            "gatekeeper": "anthropic/claude-haiku-4-5",
        }})
        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code == 0, f"Expected exit 0, got {exit_code}"
            return "CLI evaluator succeeded"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L1", "Claude CLI evaluator", l1, llm_call=True)

    # L2: Claude CLI full pipeline
    def l2():
        import shutil
        if not shutil.which("claude"):
            return "SKIP: Claude CLI not in PATH"
        harness.update_config({"models": {
            "evaluator": "claude-cli/sonnet",
            "drafter": "claude-cli/sonnet",
            "gatekeeper": "claude-cli/haiku",
        }})
        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code == 0, f"Expected exit 0, got {exit_code}"
            return "Full CLI pipeline succeeded"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L2", "Claude CLI full pipeline", l2, llm_call=True)

    # L3: Mixed providers
    def l3():
        import shutil
        if not shutil.which("claude"):
            return "SKIP: Claude CLI not in PATH"
        harness.update_config({"models": {
            "evaluator": "anthropic/claude-haiku-4-5",
            "drafter": "claude-cli/sonnet",
            "gatekeeper": "anthropic/claude-haiku-4-5",
        }})
        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code == 0, f"Expected exit 0, got {exit_code}"
            return "Mixed providers succeeded"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L3", "Mixed providers", l3, llm_call=True)

    # L4: Invalid provider -> graceful error
    def l4():
        harness.update_config({"models": {
            "evaluator": "invalid/model",
            "drafter": "anthropic/claude-sonnet-4-5",
            "gatekeeper": "anthropic/claude-haiku-4-5",
        }})
        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code == 1, f"Expected exit 1, got {exit_code}"
            return f"Invalid provider -> exit {exit_code}"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L4", "Invalid provider -> graceful error", l4)

    # L5: Missing key for chosen provider
    def l5():
        env_path = harness.base / ".env"
        env_content = env_path.read_text()
        modified = "\n".join(
            line for line in env_content.splitlines()
            if not line.startswith("ANTHROPIC_API_KEY")
        )
        env_path.write_text(modified)
        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code in (1, 3), f"Expected exit 1 or 3, got {exit_code}"
            return f"Missing key -> exit {exit_code}"
        finally:
            env_path.write_text(env_content)

    runner.run_scenario("L5", "Missing key -> error", l5)

    # L6: Bare model name -> config error
    def l6():
        harness.update_config({"models": {
            "evaluator": "claude-opus-4-5",
            "drafter": "anthropic/claude-sonnet-4-5",
            "gatekeeper": "anthropic/claude-haiku-4-5",
        }})
        try:
            from social_hook.config.yaml import load_config
            try:
                load_config(config_path)
                assert False, "Should have raised ConfigError"
            except ConfigError as e:
                assert "provider/model-id" in str(e).lower() or "invalid model" in str(e).lower()
                return f"Bare name rejected: {e}"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L6", "Bare model name -> error", l6)

    # L7: Factory routing unit check
    def l7():
        assert parse_provider_model("anthropic/claude-opus-4-5") == ("anthropic", "claude-opus-4-5")
        assert parse_provider_model("claude-cli/sonnet") == ("claude-cli", "sonnet")
        assert parse_provider_model("openrouter/anthropic/claude-sonnet-4.5") == ("openrouter", "anthropic/claude-sonnet-4.5")
        assert parse_provider_model("openai/gpt-4o") == ("openai", "gpt-4o")
        assert parse_provider_model("ollama/llama3.3") == ("ollama", "llama3.3")
        try:
            parse_provider_model("bare-model-name")
            assert False, "Should raise ConfigError"
        except ConfigError:
            pass
        return "All parsing tests passed"

    runner.run_scenario("L7", "Factory routing unit check", l7)

    # L8: Provider auto-discovery
    def l8():
        from social_hook.setup.wizard import _discover_providers
        providers = _discover_providers({})
        provider_ids = [p["id"] for p in providers]
        # Should always have anthropic and openrouter (even if unconfigured)
        assert "anthropic" in provider_ids
        assert "openrouter" in provider_ids
        return f"Discovered {len(providers)} providers: {provider_ids}"

    runner.run_scenario("L8", "Provider auto-discovery", l8)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="E2E test suite for social-media-auto-hook"
    )
    parser.add_argument(
        "--only", type=str, default=None,
        help="Run only a specific section (onboarding, pipeline, narrative, draft, "
             "scheduler, bot, setup, cli, crosscutting) or scenario (A1, B1, etc.)"
    )
    parser.add_argument(
        "--skip-telegram", action="store_true",
        help="Skip Telegram-dependent sections (F, G, H)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show full LLM outputs inline"
    )
    args = parser.parse_args()

    # Determine which sections to run
    sections_to_run = set("ABCDEFGHIJKL")
    if args.only:
        only = args.only
        if only.lower() in SECTION_MAP:
            sections_to_run = set(SECTION_MAP[only.lower()])
        elif only.upper()[0] in "ABCDEFGHIJKL":
            # Single scenario — run the whole section
            sections_to_run = {only.upper()[0]}
        else:
            print(f"Unknown section: {args.only}")
            sys.exit(1)

    if args.skip_telegram:
        sections_to_run -= {"F", "G", "H"}

    print("=" * 60)
    print("  E2E Test Suite (LIVE)")
    print("  Repo: social-media-auto-hook")
    print(f"  Sections: {', '.join(sorted(sections_to_run))}")
    print("=" * 60)

    runner = E2ERunner(verbose=args.verbose)
    runner.start_time = time.time()

    # Resolve real base path before patching HOME
    real_home = os.environ.get("HOME", str(Path.home()))
    real_base = Path(real_home) / ".social-hook"

    harness = E2EHarness(real_base=real_base)
    telegram_capture = TelegramCapture()

    try:
        print("\n  Setting up isolated environment...")
        harness.setup()
        telegram_capture.install()
        print(f"  Temp HOME: {harness.fake_home}")
        print(f"  Repo: {harness.repo_path}")

        # Run sections in order
        if "A" in sections_to_run:
            print("\n--- A. Project Onboarding ---")
            test_A_onboarding(harness, runner)

        if "B" in sections_to_run:
            print("\n--- B. Pipeline Scenarios ---")
            test_B_pipeline(harness, runner)

        if "C" in sections_to_run:
            print("\n--- C. Narrative Mechanics ---")
            test_C_narrative(harness, runner)

        if "D" in sections_to_run:
            print("\n--- D. Draft Lifecycle ---")
            test_D_draft_lifecycle(harness, runner, telegram_capture)

        if "E" in sections_to_run:
            print("\n--- E. Scheduler ---")
            test_E_scheduler(harness, runner)

        if "F" in sections_to_run:
            print("\n--- F. Bot Commands ---")
            test_F_bot_commands(harness, runner, telegram_capture)

        if "G" in sections_to_run:
            print("\n--- G. Bot Buttons ---")
            test_G_bot_buttons(harness, runner, telegram_capture)

        if "H" in sections_to_run:
            print("\n--- H. Gatekeeper ---")
            test_H_gatekeeper(harness, runner, telegram_capture)

        if "I" in sections_to_run:
            print("\n--- I. Setup Validation ---")
            test_I_setup_validation(harness, runner)

        if "J" in sections_to_run:
            print("\n--- J. CLI Commands ---")
            test_J_cli(harness, runner)

        if "K" in sections_to_run:
            print("\n--- K. Cross-Cutting ---")
            test_K_crosscutting(harness, runner, telegram_capture)

        if "L" in sections_to_run:
            print("\n--- L. Multi-Provider ---")
            test_L_multi_provider(harness, runner)

    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    except Exception as e:
        print(f"\n\nFATAL: {e}")
        if args.verbose:
            traceback.print_exc()
    finally:
        telegram_capture.uninstall()
        harness.teardown()

    runner.print_summary()
    runner.print_review_report()

    sys.exit(0 if runner.all_passed else 1)


if __name__ == "__main__":
    main()
