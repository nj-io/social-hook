"""Tests for Development Narrative integration in prompt assembly."""

from unittest.mock import patch

import pytest

from social_hook.config.project import ContextConfig, ProjectConfig
from social_hook.llm.dry_run import DryRunContext
from social_hook.llm.prompts import (
    assemble_drafter_prompt,
    assemble_evaluator_context,
    assemble_evaluator_prompt,
)
from social_hook.models import (
    Arc,
    CommitInfo,
    Decision,
    Draft,
    Lifecycle,
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


SAMPLE_NARRATIVES = [
    {
        "summary": "Implemented JWT authentication flow",
        "key_decisions": [
            "Use RS256 over HS256 for key rotation",
            "Store refresh tokens in httpOnly cookies",
            "Set token expiry to 15 minutes",
        ],
        "rejected_approaches": [
            "Session-based auth (doesn't scale for API)",
            "OAuth-only (too complex for MVP)",
        ],
        "aha_moments": [
            "Refresh token rotation prevents replay attacks",
            "Middleware pattern keeps auth logic clean",
        ],
        "social_hooks": [
            "Why we chose JWT over sessions",
            "The refresh token gotcha nobody warns you about",
            "Auth in 50 lines of code",
        ],
    },
    {
        "summary": "Refactored database layer to use connection pooling",
        "key_decisions": [
            "Switch from sqlite3 to SQLAlchemy for pooling",
        ],
        "rejected_approaches": [],
        "aha_moments": [
            "Connection pool size should match worker count",
        ],
        "social_hooks": [
            "Database connections are expensive — here's proof",
        ],
    },
]


# =============================================================================
# Evaluator Prompt: Narrative rendering
# =============================================================================


class TestEvaluatorPromptNarrative:
    """Development Narrative section in evaluator prompt."""

    def test_narratives_present_shows_section(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "## Development Narrative" in result

    def test_empty_narratives_no_section(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = []
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "## Development Narrative" not in result

    def test_includes_key_decisions(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "**Key decisions:**" in result
        assert "Use RS256 over HS256 for key rotation" in result

    def test_includes_rejected_approaches(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "**Rejected approaches:**" in result
        assert "Session-based auth" in result

    def test_includes_aha_moments(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "**Insights:**" in result
        assert "Refresh token rotation" in result

    def test_includes_social_hooks(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "**Post angles:**" in result
        assert "Why we chose JWT over sessions" in result

    def test_session_summary_as_heading(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "### Session: Implemented JWT authentication flow" in result
        assert "### Session: Refactored database layer" in result

    def test_limits_to_5_narratives(self, sample_project_context, sample_commit):
        many_narratives = [
            {"summary": f"Session {i}", "key_decisions": [f"decision-{i}"]}
            for i in range(10)
        ]
        sample_project_context.session_narratives = many_narratives
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "Session 0" in result
        assert "Session 4" in result
        assert "Session 5" not in result

    def test_limits_list_items_to_3(self, sample_project_context, sample_commit):
        narrative_with_many = {
            "summary": "Big session",
            "key_decisions": [f"dec-{i}" for i in range(10)],
            "rejected_approaches": [f"rej-{i}" for i in range(10)],
            "aha_moments": [f"aha-{i}" for i in range(10)],
            "social_hooks": [f"hook-{i}" for i in range(10)],
        }
        sample_project_context.session_narratives = [narrative_with_many]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "dec-0" in result
        assert "dec-2" in result
        assert "dec-3" not in result
        assert "rej-2" in result
        assert "rej-3" not in result
        assert "aha-2" in result
        assert "aha-3" not in result
        assert "hook-2" in result
        assert "hook-3" not in result

    def test_missing_summary_shows_fallback(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = [{"key_decisions": ["d1"]}]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "### Session: No summary" in result

    def test_in_window_narrative_no_label(self, sample_project_context, sample_commit):
        """In-window narratives have no extra label."""
        sample_project_context.session_narratives = [
            {"summary": "Recent work", "_in_window": True, "key_decisions": ["d1"]},
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "### Session: Recent work" in result
        assert "(earlier context)" not in result

    def test_out_of_window_narrative_shows_label(self, sample_project_context, sample_commit):
        """Out-of-window narratives show '(earlier context)' label."""
        sample_project_context.session_narratives = [
            {"summary": "Old work", "_in_window": False, "key_decisions": ["d1"]},
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "### Session: Old work (earlier context)" in result

    def test_mixed_window_labels(self, sample_project_context, sample_commit):
        """Mix of in-window and out-of-window narratives renders correctly."""
        sample_project_context.session_narratives = [
            {"summary": "Current", "_in_window": True, "key_decisions": []},
            {"summary": "Previous", "_in_window": False, "key_decisions": []},
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "### Session: Current\n" in result or "### Session: Current" in result
        assert "(earlier context)" not in result.split("### Session: Current")[1].split("###")[0]
        assert "### Session: Previous (earlier context)" in result

    def test_no_in_window_flag_defaults_to_true(self, sample_project_context, sample_commit):
        """Narratives without _in_window flag default to in-window (no label)."""
        sample_project_context.session_narratives = [
            {"summary": "Legacy narrative", "key_decisions": ["d1"]},
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "### Session: Legacy narrative" in result
        assert "(earlier context)" not in result

    def test_empty_lists_omitted(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = [
            {
                "summary": "Minimal session",
                "key_decisions": [],
                "rejected_approaches": [],
                "aha_moments": [],
                "social_hooks": [],
            }
        ]
        result = assemble_evaluator_prompt(
            "# Eval", sample_project_context, sample_commit
        )
        assert "## Development Narrative" in result
        assert "### Session: Minimal session" in result
        assert "**Key decisions:**" not in result
        assert "**Rejected approaches:**" not in result
        assert "**Insights:**" not in result
        assert "**Post angles:**" not in result


# =============================================================================
# Drafter Prompt: Narrative rendering
# =============================================================================


class TestDrafterPromptNarrative:
    """Development Narrative section in drafter prompt."""

    def test_narratives_present_shows_section(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        decision = Decision(
            id="dec_1", project_id="proj_test1", commit_hash="abc123",
            decision="post_worthy", reasoning="Added auth",
        )
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            sample_project_context.recent_posts, sample_commit,
        )
        assert "## Development Narrative" in result

    def test_empty_narratives_no_section(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = []
        decision = Decision(
            id="dec_1", project_id="proj_test1", commit_hash="abc123",
            decision="post_worthy", reasoning="Added auth",
        )
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            sample_project_context.recent_posts, sample_commit,
        )
        assert "## Development Narrative" not in result

    def test_includes_narrative_content(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        decision = Decision(
            id="dec_1", project_id="proj_test1", commit_hash="abc123",
            decision="post_worthy", reasoning="Added auth",
        )
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            sample_project_context.recent_posts, sample_commit,
        )
        assert "### Session: Implemented JWT authentication flow" in result
        assert "**Key decisions:**" in result
        assert "**Post angles:**" in result

    def test_dict_decision_with_narratives(self, sample_project_context, sample_commit):
        sample_project_context.session_narratives = SAMPLE_NARRATIVES
        decision = {"decision": "post_worthy", "reasoning": "Test"}
        result = assemble_drafter_prompt(
            "# Drafter", decision, sample_project_context,
            [], sample_commit,
        )
        assert "## Development Narrative" in result


# =============================================================================
# assemble_evaluator_context: Narrative loading
# =============================================================================


class TestEvaluatorContextNarrativeLoading:
    """Tests for narrative loading in assemble_evaluator_context."""

    def test_loads_narratives_successfully(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj_nar1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        mock_narratives = [
            {"summary": "Added auth flow", "key_decisions": ["Use JWT"]},
        ]

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig()

        with patch(
            "social_hook.narrative.storage.load_recent_narratives",
            return_value=mock_narratives,
        ) as mock_load:
            ctx = assemble_evaluator_context(db, "proj_nar1", project_config)
            mock_load.assert_called_once_with("proj_nar1", limit=5, after=None, before=None)
            assert ctx.session_narratives == mock_narratives

    def test_passes_timestamps_to_load(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj_nar_ts", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig()

        with patch(
            "social_hook.narrative.storage.load_recent_narratives",
            return_value=[],
        ) as mock_load:
            assemble_evaluator_context(
                db, "proj_nar_ts", project_config,
                commit_timestamp="2026-02-20T12:00:00+07:00",
                parent_timestamp="2026-02-20T10:00:00+07:00",
            )
            mock_load.assert_called_once_with(
                "proj_nar_ts", limit=5,
                after="2026-02-20T10:00:00+07:00",
                before="2026-02-20T12:00:00+07:00",
            )

    def test_handles_load_failure_gracefully(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj_nar2", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig()

        with patch(
            "social_hook.narrative.storage.load_recent_narratives",
            side_effect=RuntimeError("Storage corrupted"),
        ):
            ctx = assemble_evaluator_context(db, "proj_nar2", project_config)
            assert ctx.session_narratives == []

    def test_handles_import_error_gracefully(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj_nar3", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        db = DryRunContext(temp_db, dry_run=False)
        project_config = ProjectConfig()

        with patch(
            "social_hook.narrative.storage.load_recent_narratives",
            side_effect=ImportError("Module not found"),
        ):
            ctx = assemble_evaluator_context(db, "proj_nar3", project_config)
            assert ctx.session_narratives == []


# =============================================================================
# ProjectContext defaults
# =============================================================================


class TestProjectContextNarrativeDefaults:
    """session_narratives field default behavior on ProjectContext."""

    def test_defaults_to_empty_list(self):
        project = Project(id="proj_def", name="test", repo_path="/tmp/test")
        ctx = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            audience_introduced=False,
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary=None,
        )
        assert ctx.session_narratives == []

    def test_accepts_narratives(self):
        project = Project(id="proj_acc", name="test", repo_path="/tmp/test")
        narratives = [{"summary": "test session"}]
        ctx = ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            audience_introduced=False,
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary=None,
            session_narratives=narratives,
        )
        assert ctx.session_narratives == narratives
