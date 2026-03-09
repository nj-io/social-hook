"""Section A: Project Onboarding scenarios."""

import subprocess
from pathlib import Path

from e2e.constants import COMMITS


def run(harness, runner):
    """A1-A10: Project onboarding scenarios."""
    from typer.testing import CliRunner

    from social_hook.cli import app

    cli = CliRunner()

    # A1: Register project via CLI
    def a1():
        result = cli.invoke(app, ["project", "register", str(harness.repo_path)])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert (
            "Registered project" in result.output
            or "proj_" in result.output.lower()
            or "project_" in result.output.lower()
        )
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
        from social_hook.db import get_lifecycle, get_narrative_debt, get_project

        project = get_project(harness.conn, harness.project_id)
        assert project is not None, "Project not found in DB"
        assert project.name == "social-media-auto-hook"
        assert Path(project.repo_path).resolve() == Path(harness.repo_path).resolve()
        assert project.paused is False, f"paused={project.paused}"
        assert project.audience_introduced is False, (
            f"audience_introduced={project.audience_introduced}"
        )

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
        project_root = harness.project_root
        second_clone = harness.base / "repos" / "second-clone"
        subprocess.run(
            ["git", "clone", "--quiet", str(project_root), str(second_clone)],
            check=True,
            capture_output=True,
        )
        result = cli.invoke(app, ["project", "register", str(second_clone)])
        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}"
        assert "already" in result.output.lower() or "origin" in result.output.lower()
        return "Blocked: duplicate origin"

    runner.run_scenario("A6", "Duplicate origin blocked", a6)

    # A7: Project introduction — first trigger with audience_introduced=False
    def a7():
        from social_hook.db import get_recent_decisions
        from social_hook.trigger import run_trigger

        exit_code = run_trigger(
            COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
        )
        assert exit_code == 0, f"run_trigger returned {exit_code}"

        decisions = get_recent_decisions(harness.conn, harness.project_id, limit=5)
        assert len(decisions) > 0, "No decisions created"
        d = decisions[0]

        # Structural check: decision is valid
        valid_decisions = {"draft", "hold", "skip"}
        assert d.decision in valid_decisions, f"Invalid decision: {d.decision}"

        detail = f"Decision: {d.decision}"
        if d.decision == "draft":
            assert d.episode_type is not None, "episode_type is None for draft"
            assert d.post_category is not None, "post_category is None for draft"
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

    runner.run_scenario(
        "A7", "Project introduction (audience_introduced=False)", a7, llm_call=True, isolate=True
    )

    # A8: Verify audience_introduced flag operations
    def a8():
        from social_hook.db.operations import get_audience_introduced, set_audience_introduced

        # Test set/get round-trip (works regardless of initial state)
        set_audience_introduced(harness.conn, harness.project_id, True)
        assert get_audience_introduced(harness.conn, harness.project_id) is True

        set_audience_introduced(harness.conn, harness.project_id, False)
        assert get_audience_introduced(harness.conn, harness.project_id) is False

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

        # Load project config from repo
        project_config = load_project_config(str(harness.repo_path))

        from e2e.harness import FakeDB

        db = FakeDB(harness.conn, harness.project_id)
        ctx = assemble_evaluator_context(db, harness.project_id, project_config)

        has_memories = bool(ctx.memories)
        has_notes = bool(ctx.context_notes)
        assert has_memories, "Memories not included in context"
        assert has_notes, "Context notes not included in context"
        return f"Memories: {len(ctx.memories)}, Notes: {len(ctx.context_notes)}"

    runner.run_scenario("A10", "Context files included in evaluator context", a10)
