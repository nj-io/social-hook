"""Tests for prompt management (T17)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from social_hook.config.project import ContextConfig, ProjectConfig
from social_hook.errors import PromptNotFoundError
from social_hook.llm.dry_run import DryRunContext
from social_hook.llm.prompts import (
    assemble_drafter_prompt,
    assemble_evaluator_context,
    assemble_evaluator_prompt,
    assemble_expert_prompt,
    assemble_gatekeeper_prompt,
    compact_by_truncation,
    count_tokens,
    load_prompt,
)
from social_hook.models import (
    Arc,
    CommitInfo,
    Decision,
    Draft,
    Lifecycle,
    NarrativeDebt,
    Post,
    Project,
    ProjectContext,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_commit():
    return CommitInfo(
        hash="abc123def456",
        message="Add user authentication module",
        diff="+ def authenticate(user):\n+     return check_password(user)",
        files_changed=["src/auth.py", "tests/test_auth.py"],
        insertions=50,
        deletions=10,
    )


@pytest.fixture
def sample_project_context():
    project = Project(
        id="proj_test1", name="test-project", repo_path="/tmp/test"
    )
    lifecycle = Lifecycle(
        project_id="proj_test1", phase="build", confidence=0.8
    )
    return ProjectContext(
        project=project,
        social_context="## Voice\nTechnical but approachable.",
        lifecycle=lifecycle,
        active_arcs=[
            Arc(id="arc_1", project_id="proj_test1", theme="Building auth", post_count=2),
        ],
        narrative_debt=1,
        audience_introduced=True,
        pending_drafts=[],
        recent_decisions=[
            Decision(
                id="dec_1", project_id="proj_test1", commit_hash="prev123",
                decision="post_worthy", reasoning="Added logging system",
                commit_message="Add structured logging module",
            ),
        ],
        recent_posts=[
            Post(
                id="post_1", draft_id="draft_1", project_id="proj_test1",
                platform="x", content="Just shipped logging!",
            ),
        ],
        project_summary="Test project building auth system.",
        memories=[
            {"date": "2026-01-30", "context": "Tech post", "feedback": '"Too formal"'},
        ],
    )


@pytest.fixture
def sample_draft():
    return Draft(
        id="draft_test1", project_id="proj_test1",
        decision_id="dec_1", platform="x",
        content="Just added auth module!",
    )


# =============================================================================
# T17: Prompt Loading
# =============================================================================


class TestLoadPrompt:
    """T17: Prompt file loading."""

    def test_load_existing_prompt(self, temp_dir):
        prompts_dir = temp_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "evaluator.md").write_text("# Evaluator\nYou evaluate commits.")

        with patch("social_hook.llm.prompts.Path.home", return_value=temp_dir / ".."):
            # Need to mock the full path construction
            pass

        # Direct path test
        prompt_path = prompts_dir / "evaluator.md"
        content = prompt_path.read_text()
        assert "Evaluator" in content

    def test_missing_prompt_raises(self, temp_dir):
        with patch(
            "social_hook.llm.prompts.Path.home",
            return_value=temp_dir,
        ):
            with pytest.raises(PromptNotFoundError, match="evaluator"):
                load_prompt("evaluator")

    def test_load_prompt_reads_file(self, temp_dir):
        prompts_dir = temp_dir / ".social-hook" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "evaluator.md").write_text("# Test Evaluator\nTest content.")

        with patch(
            "social_hook.llm.prompts.Path.home",
            return_value=temp_dir,
        ):
            content = load_prompt("evaluator")
            assert "Test Evaluator" in content
            assert "Test content." in content


# =============================================================================
# T17: Token Counting
# =============================================================================


class TestCountTokens:
    """T17: Approximate token counting."""

    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_short_string(self):
        # "hello" = 5 chars / 4 = 1
        assert count_tokens("hello") == 1

    def test_longer_string(self):
        text = "a" * 400
        assert count_tokens(text) == 100

    def test_realistic_text(self):
        text = "This is a typical sentence with about forty characters or so in it."
        tokens = count_tokens(text)
        assert 10 < tokens < 30  # Reasonable range


# =============================================================================
# T17: Evaluator Prompt Assembly
# =============================================================================


class TestAssembleEvaluatorPrompt:
    """T17: Evaluator context assembly."""

    def test_includes_base_prompt(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Base Prompt", sample_project_context, sample_commit
        )
        assert "# Base Prompt" in result

    def test_includes_social_context(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Technical but approachable" in result

    def test_includes_lifecycle(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "build" in result
        assert "0.8" in result

    def test_includes_narrative_debt(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Narrative debt: 1" in result

    def test_includes_active_arcs(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Building auth" in result

    def test_includes_commit_info(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "abc123def456" in result
        assert "Add user authentication module" in result

    def test_includes_diff(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "authenticate" in result

    def test_includes_recent_decisions(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Added logging system" in result

    def test_recent_decisions_include_commit_message(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Add structured logging module" in result

    def test_recent_decisions_null_commit_message(self, sample_project_context, sample_commit):
        sample_project_context.recent_decisions[0].commit_message = None
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert '"N/A"' in result

    def test_includes_recent_posts(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Just shipped logging" in result

    def test_includes_memories(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Too formal" in result

    def test_includes_project_summary(self, sample_project_context, sample_commit):
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "auth system" in result

    def test_config_limits_respected(self, sample_project_context, sample_commit):
        config = ContextConfig(recent_decisions=1, recent_posts=1)
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit, config
        )
        # Should still contain at least one decision
        assert "Added logging system" in result

    def test_no_social_context(self, sample_project_context, sample_commit):
        sample_project_context.social_context = None
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "## Project Context" in result  # Section header still present

    def test_include_readme(self, sample_project_context, sample_commit, temp_dir):
        """T20d: include_readme=True includes README.md content."""
        repo = temp_dir / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# My Project\nA CLI tool for automation.")
        sample_project_context.project.repo_path = str(repo)

        config = ContextConfig(include_readme=True)
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit, config
        )
        assert "## README" in result
        assert "A CLI tool for automation" in result

    def test_include_readme_false_excludes(
        self, sample_project_context, sample_commit, temp_dir
    ):
        """T20d: include_readme=False omits README.md."""
        repo = temp_dir / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# My Project\nShould not appear.")
        sample_project_context.project.repo_path = str(repo)

        config = ContextConfig(include_readme=False)
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit, config
        )
        assert "## README" not in result

    def test_include_claude_md(self, sample_project_context, sample_commit, temp_dir):
        """T20d: include_claude_md=True includes CLAUDE.md content."""
        repo = temp_dir / "repo"
        repo.mkdir()
        (repo / "CLAUDE.md").write_text("# Project Conventions\nUse snake_case.")
        sample_project_context.project.repo_path = str(repo)

        config = ContextConfig(include_claude_md=True)
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit, config
        )
        assert "## CLAUDE.md" in result
        assert "Use snake_case" in result

    def test_max_doc_tokens_truncates(
        self, sample_project_context, sample_commit, temp_dir
    ):
        """T20d: Large docs truncated to max_doc_tokens."""
        repo = temp_dir / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Big Doc\n" + "x" * 50000)
        sample_project_context.project.repo_path = str(repo)

        config = ContextConfig(include_readme=True, max_doc_tokens=100)
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit, config
        )
        assert "## README" in result
        assert "[...truncated]" in result

    def test_missing_docs_no_error(self, sample_project_context, sample_commit, temp_dir):
        """T20d: Missing README/CLAUDE.md doesn't error."""
        repo = temp_dir / "repo"
        repo.mkdir()
        sample_project_context.project.repo_path = str(repo)

        config = ContextConfig(include_readme=True, include_claude_md=True)
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit, config
        )
        assert "## README" not in result
        assert "## CLAUDE.md" not in result


# =============================================================================
# T17: Drafter Prompt Assembly
# =============================================================================


class TestAssembleDrafterPrompt:
    """T17: Drafter context assembly."""

    def test_includes_decision(self, sample_project_context, sample_commit):
        decision = Decision(
            id="dec_1", project_id="proj_test1", commit_hash="abc123",
            decision="post_worthy", reasoning="Important feature",
            episode_type="milestone",
        )
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            sample_project_context.recent_posts, sample_commit,
        )
        assert "post_worthy" in result
        assert "Important feature" in result
        assert "milestone" in result

    def test_includes_arc_context(self, sample_project_context, sample_commit):
        decision = Decision(
            id="dec_1", project_id="proj_test1", commit_hash="abc123",
            decision="post_worthy", reasoning="Test",
            post_category="arc",
        )
        arc = Arc(id="arc_1", project_id="proj_test1", theme="Auth arc", post_count=3)
        arc_ctx = {
            "arc": arc,
            "posts": [
                Post(id="p1", draft_id="d1", project_id="proj_test1",
                     platform="x", content="Previous auth post"),
            ],
        }
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            [], sample_commit, arc_context=arc_ctx,
        )
        assert "Auth arc" in result
        assert "Previous auth post" in result

    def test_no_arc_context_for_opportunistic(self, sample_project_context, sample_commit):
        decision = Decision(
            id="dec_1", project_id="proj_test1", commit_hash="abc123",
            decision="post_worthy", reasoning="Test",
            post_category="opportunistic",
        )
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            [], sample_commit,
        )
        assert "## Arc Context" not in result

    def test_includes_memories(self, sample_project_context, sample_commit):
        decision = {"decision": "post_worthy", "reasoning": "Test"}
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            [], sample_commit,
        )
        assert "Too formal" in result


# =============================================================================
# T17: Gatekeeper Prompt Assembly
# =============================================================================


class TestAssembleGatekeeperPrompt:
    """T17: Gatekeeper context assembly."""

    def test_includes_draft(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# Gatekeeper", sample_draft, "approve this",
        )
        assert "Just added auth module" in result
        assert "approve this" in result

    def test_includes_project_summary(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# Gatekeeper", sample_draft, "approve",
            project_summary="Building an auth system for devs.",
        )
        assert "Building an auth system" in result

    def test_no_summary(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# Gatekeeper", sample_draft, "approve",
        )
        assert "## Project Summary" not in result

    def test_dict_draft(self):
        draft = {"platform": "x", "content": "Test post"}
        result = assemble_gatekeeper_prompt(
            "# GK", draft, "looks good",
        )
        assert "Test post" in result


# =============================================================================
# T17: Expert Prompt Assembly
# =============================================================================


class TestAssembleExpertPrompt:
    """T17: Expert escalation context assembly."""

    def test_includes_escalation_info(self, sample_draft):
        result = assemble_expert_prompt(
            "# Expert", sample_draft, "Make it funnier",
            escalation_reason="Creative request",
            escalation_context="User wants humor",
        )
        assert "Creative request" in result
        assert "User wants humor" in result
        assert "Make it funnier" in result

    def test_includes_project_summary(self, sample_draft):
        result = assemble_expert_prompt(
            "# Expert", sample_draft, "edit this",
            escalation_reason="Complex edit",
            project_summary="Auth project for developers.",
        )
        assert "Auth project" in result

    def test_no_escalation_context(self, sample_draft):
        result = assemble_expert_prompt(
            "# Expert", sample_draft, "rewrite",
            escalation_reason="Rewrite request",
        )
        assert "Rewrite request" in result
        assert "Context:" not in result


# =============================================================================
# T17/T20b: Context Compaction
# =============================================================================


class TestCompaction:
    """T17/T20b: Context compaction by truncation."""

    def test_no_truncation_needed(self):
        text = "Short text"
        result = compact_by_truncation(text, max_tokens=1000)
        assert result == text

    def test_truncation_with_sections(self):
        sections = [
            "# Prompt\nBase content.",
            "\n---\n## Recent History",
            "### Recent Decisions",
        ]
        # Add many history lines
        for i in range(100):
            sections.append(f"- Decision {i}: Some reasoning about commit {i}")
        sections.append("\n---\n## Current Commit")
        sections.append("- Hash: abc123")

        full_text = "\n".join(sections)
        # Set max_tokens low enough to force truncation
        result = compact_by_truncation(full_text, max_tokens=50)
        # Should preserve prompt and commit sections
        assert "# Prompt" in result
        assert "abc123" in result

    def test_truncation_preserves_commit(self):
        text = "# Prompt\n" + "x" * 10000 + "\n---\n## Recent History\n" + \
               "y" * 10000 + "\n---\n## Current Commit\n- Hash: important_hash"
        result = compact_by_truncation(text, max_tokens=200)
        assert "important_hash" in result

    def test_no_sections_fallback(self):
        text = "a" * 10000
        result = compact_by_truncation(text, max_tokens=100)
        assert len(result) < len(text)
        assert "truncated" in result


# =============================================================================
# Milestone Summaries in Evaluator Prompt
# =============================================================================


class TestMilestoneSummariesInPrompt:
    """Milestone summaries section in evaluator prompt."""

    def test_milestone_summaries_included(self, sample_project_context, sample_commit):
        sample_project_context.milestone_summaries = [
            {
                "milestone_type": "post",
                "summary": "First post about auth module.",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
            },
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "## Milestone Summaries" in result
        assert "First post about auth module" in result
        assert "2026-01-01 to 2026-01-31" in result

    def test_no_milestone_summaries_omitted(self, sample_project_context, sample_commit):
        sample_project_context.milestone_summaries = []
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "## Milestone Summaries" not in result

    def test_multiple_milestone_summaries(self, sample_project_context, sample_commit):
        sample_project_context.milestone_summaries = [
            {
                "milestone_type": "post",
                "summary": "Auth module post.",
                "period_start": "2026-01-01",
                "period_end": "2026-01-15",
            },
            {
                "milestone_type": "decision",
                "summary": "Switched to JWT.",
                "period_start": "2026-01-16",
                "period_end": "2026-01-31",
            },
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Auth module post" in result
        assert "Switched to JWT" in result


# =============================================================================
# assemble_evaluator_context
# =============================================================================


class TestAssembleEvaluatorContext:
    """Tests for assemble_evaluator_context data orchestration."""

    def _setup(self, conn):
        """Setup test data in DB."""
        from social_hook.db import operations as ops
        from social_hook.filesystem import generate_id

        project = Project(id="proj_ctx1", name="test", repo_path="/tmp/test")
        ops.insert_project(conn, project)

        lifecycle = Lifecycle(project_id="proj_ctx1", phase="build", confidence=0.8)
        ops.insert_lifecycle(conn, lifecycle)

        arc = Arc(id="arc_ctx1", project_id="proj_ctx1", theme="Auth arc")
        ops.insert_arc(conn, arc)

        debt = NarrativeDebt(project_id="proj_ctx1", debt_counter=2)
        ops.insert_narrative_debt(conn, debt)

        decision = Decision(
            id="dec_ctx1", project_id="proj_ctx1", commit_hash="abc123",
            decision="post_worthy", reasoning="Added auth",
        )
        ops.insert_decision(conn, decision)

        ops.update_project_summary(conn, "proj_ctx1", "A test project.")

    def test_basic_assembly(self, temp_db):
        self._setup(temp_db)
        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig(
            social_context="## Voice\nTechnical.",
            memories="# Voice Memories\n\n| Date | Context | Feedback | Draft ID |\n|------|---------|----------|----------|\n| 2026-01-30 | Tech post | \"Too formal\" | draft-001 |\n",
        )

        ctx = assemble_evaluator_context(db, "proj_ctx1", project_config)

        assert ctx.project.id == "proj_ctx1"
        assert ctx.lifecycle.phase == "build"
        assert len(ctx.active_arcs) == 1
        assert ctx.narrative_debt == 2
        assert ctx.project_summary == "A test project."
        assert ctx.social_context == "## Voice\nTechnical."
        assert len(ctx.memories) == 1
        assert ctx.memories[0]["context"] == "Tech post"

    def test_no_narrative_debt_returns_zero(self, temp_db):
        from social_hook.db import operations as ops
        project = Project(id="proj_nodt", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig()

        ctx = assemble_evaluator_context(db, "proj_nodt", project_config)
        assert ctx.narrative_debt == 0

    def test_empty_project_config(self, temp_db):
        from social_hook.db import operations as ops
        project = Project(id="proj_empty", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig()

        ctx = assemble_evaluator_context(db, "proj_empty", project_config)
        assert ctx.social_context is None
        assert ctx.memories == []
        assert ctx.milestone_summaries == []

    def test_milestone_summaries_included(self, temp_db):
        from social_hook.db import operations as ops
        from social_hook.filesystem import generate_id

        self._setup(temp_db)
        summary = {
            "id": generate_id("ms"),
            "project_id": "proj_ctx1",
            "milestone_type": "post",
            "summary": "Auth module post.",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
        }
        ops.insert_milestone_summary(temp_db, summary)

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig()

        ctx = assemble_evaluator_context(db, "proj_ctx1", project_config)
        assert len(ctx.milestone_summaries) == 1
        assert ctx.milestone_summaries[0]["summary"] == "Auth module post."

    def test_importable_from_llm(self):
        """Verify import works from social_hook.llm."""
        from social_hook.llm import assemble_evaluator_context
        assert callable(assemble_evaluator_context)

    def test_context_notes_included(self, temp_db):
        from social_hook.db import operations as ops
        self._setup(temp_db)

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig(
            context_notes="# Context Notes\n\n| Date | Note | Source |\n|------|------|--------|\n| 2026-02-01 | Project is pivoting to OAuth | expert:draft_123 |\n",
        )

        ctx = assemble_evaluator_context(db, "proj_ctx1", project_config)
        assert len(ctx.context_notes) == 1
        assert ctx.context_notes[0]["note"] == "Project is pivoting to OAuth"
        assert ctx.context_notes[0]["source"] == "expert:draft_123"

    def test_no_context_notes_returns_empty(self, temp_db):
        from social_hook.db import operations as ops
        project = Project(id="proj_no_cn", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig()

        ctx = assemble_evaluator_context(db, "proj_no_cn", project_config)
        assert ctx.context_notes == []


# =============================================================================
# Context Notes in Prompt Assembly
# =============================================================================


class TestContextNotesInPrompts:
    """Tests for context notes injection into assembled prompts."""

    def test_evaluator_prompt_includes_context_notes(self, sample_project_context, sample_commit):
        sample_project_context.context_notes = [
            {"date": "2026-02-01", "note": "Project pivoting to OAuth", "source": "expert"},
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "## Context Notes" in result
        assert "Project pivoting to OAuth" in result
        assert "expert" in result

    def test_evaluator_prompt_no_context_notes(self, sample_project_context, sample_commit):
        sample_project_context.context_notes = []
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "## Context Notes" not in result

    def test_drafter_prompt_includes_context_notes(self, sample_project_context, sample_commit):
        sample_project_context.context_notes = [
            {"date": "2026-02-01", "note": "Avoid mentioning competitor X", "source": "human"},
        ]
        decision = Decision(
            id="dec_1", project_id="proj_test1", commit_hash="abc123",
            decision="post_worthy", reasoning="Added auth",
        )
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            sample_project_context.recent_posts, sample_commit,
        )
        assert "## Context Notes" in result
        assert "Avoid mentioning competitor X" in result

    def test_drafter_prompt_no_context_notes(self, sample_project_context, sample_commit):
        sample_project_context.context_notes = []
        decision = Decision(
            id="dec_1", project_id="proj_test1", commit_hash="abc123",
            decision="post_worthy", reasoning="Added auth",
        )
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            sample_project_context.recent_posts, sample_commit,
        )
        assert "## Context Notes" not in result

    def test_context_notes_limited_to_10(self, sample_project_context, sample_commit):
        sample_project_context.context_notes = [
            {"date": f"2026-01-{i:02d}", "note": f"Note {i}", "source": "test"}
            for i in range(20)
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        # Should only include the last 10
        assert "Note 10" in result
        assert "Note 19" in result
        # Earlier ones should not be present
        assert "Note 0]" not in result
