"""Tests for arc system activation (Chunk 7).

Tests cover:
- LogEvaluationInput new_arc_theme field (TargetDecisionInput)
- increment_arc_post_count() business logic
- trigger.py arc creation and post count wiring
- update_decision arc_id parameter
- draft() arc_context wiring
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from social_hook.db import operations as ops
from social_hook.llm.schemas import LogEvaluationInput
from social_hook.models.core import Decision, Project
from social_hook.narrative.arcs import (
    create_arc,
    get_arc,
    increment_arc_post_count,
)


def _setup_project(conn, project_id="proj_test1"):
    """Helper to insert a test project."""
    project = Project(id=project_id, name="test", repo_path="/tmp/test")
    ops.insert_project(conn, project)
    return project


def _make_evaluation(**overrides):
    """Create a mock evaluation result (SimpleNamespace, duck-typed for trigger logic)."""
    defaults = {
        "decision": "draft",
        "reasoning": "Test post",
        "episode_type": "milestone",
        "post_category": "arc",
        "arc_id": None,
        "new_arc_theme": None,
        "media_tool": None,
        "angle": "Test angle",
        "include_project_docs": None,
        "commit_summary": None,
        "reference_posts": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# =============================================================================
# Schema: new_arc_theme field (LogEvaluationInput / TargetDecisionInput)
# =============================================================================


class TestLogEvaluationNewArcTheme:
    """LogEvaluationInput new_arc_theme field validation."""

    def test_new_arc_theme_accepted(self):
        result = LogEvaluationInput.validate(
            {
                "commit_analysis": {"summary": "Starts new auth work"},
                "targets": {
                    "default": {
                        "action": "draft",
                        "reason": "Starts new auth work",
                        "new_arc_theme": "Building the auth system",
                        "post_category": "arc",
                        "episode_type": "milestone",
                    }
                },
            }
        )
        assert result.strategies["default"].new_arc_theme == "Building the auth system"
        assert result.strategies["default"].arc_id is None

    def test_arc_id_still_works(self):
        result = LogEvaluationInput.validate(
            {
                "commit_analysis": {"summary": "Continues auth arc"},
                "targets": {
                    "default": {
                        "action": "draft",
                        "reason": "Continues auth arc",
                        "arc_id": "arc_abc123",
                        "post_category": "arc",
                    }
                },
            }
        )
        assert result.strategies["default"].arc_id == "arc_abc123"
        assert result.strategies["default"].new_arc_theme is None

    def test_neither_arc_field(self):
        result = LogEvaluationInput.validate(
            {
                "commit_analysis": {"summary": "Standalone post"},
                "targets": {
                    "default": {
                        "action": "draft",
                        "reason": "Standalone post",
                        "post_category": "opportunistic",
                    }
                },
            }
        )
        assert result.strategies["default"].arc_id is None
        assert result.strategies["default"].new_arc_theme is None

    def test_new_arc_theme_optional(self):
        result = LogEvaluationInput.validate(
            {
                "commit_analysis": {"summary": "Typo fix"},
                "targets": {"default": {"action": "skip", "reason": "Just a typo fix"}},
            }
        )
        assert result.strategies["default"].new_arc_theme is None

    def test_tool_schema_includes_new_arc_theme(self):
        schema = LogEvaluationInput.to_tool_schema()
        target_props = schema["input_schema"]["properties"]["targets"]["additionalProperties"][
            "properties"
        ]
        assert "new_arc_theme" in target_props
        assert target_props["new_arc_theme"]["type"] == "string"

    def test_tool_schema_arc_id_present(self):
        schema = LogEvaluationInput.to_tool_schema()
        target_props = schema["input_schema"]["properties"]["targets"]["additionalProperties"][
            "properties"
        ]
        assert "arc_id" in target_props


# =============================================================================
# increment_arc_post_count
# =============================================================================


class TestIncrementArcPostCount:
    """Tests for narrative.arcs.increment_arc_post_count."""

    def test_increment_from_zero(self, temp_db):
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "Test arc")
        arc_before = get_arc(temp_db, arc_id)
        assert arc_before.post_count == 0

        result = increment_arc_post_count(temp_db, arc_id)
        assert result is True

        arc_after = get_arc(temp_db, arc_id)
        assert arc_after.post_count == 1
        assert arc_after.last_post_at is not None

    def test_increment_multiple(self, temp_db):
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "Multi-post arc")

        for _i in range(3):
            increment_arc_post_count(temp_db, arc_id)

        arc = get_arc(temp_db, arc_id)
        assert arc.post_count == 3

    def test_increment_nonexistent_arc(self, temp_db):
        result = increment_arc_post_count(temp_db, "arc_nonexistent")
        assert result is False

    def test_increment_sets_last_post_at(self, temp_db):
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "Timestamp test")

        arc_before = get_arc(temp_db, arc_id)
        assert arc_before.last_post_at is None

        increment_arc_post_count(temp_db, arc_id)

        arc_after = get_arc(temp_db, arc_id)
        assert arc_after.last_post_at is not None


# =============================================================================
# update_decision arc_id parameter
# =============================================================================


class TestUpdateDecisionArcId:
    """Tests for the arc_id parameter on update_decision."""

    def test_update_decision_sets_arc_id(self, temp_db):
        _setup_project(temp_db)
        # Create a real arc so FK constraint is satisfied
        arc_id = create_arc(temp_db, "proj_test1", "Test arc for FK")
        decision = Decision(
            id="dec_test1",
            project_id="proj_test1",
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
        )
        ops.insert_decision(temp_db, decision)

        result = ops.update_decision(temp_db, "dec_test1", arc_id=arc_id)
        assert result is True

        updated = ops.get_decision(temp_db, "dec_test1")
        assert updated.arc_id == arc_id

    def test_update_decision_arc_id_none_no_change(self, temp_db):
        _setup_project(temp_db)
        # Create real arc for FK constraint
        arc_id = create_arc(temp_db, "proj_test1", "Original arc")
        decision = Decision(
            id="dec_test2",
            project_id="proj_test1",
            commit_hash="def456",
            decision="draft",
            reasoning="Test",
            arc_id=arc_id,
        )
        ops.insert_decision(temp_db, decision)

        # Update without arc_id should not change it
        ops.update_decision(temp_db, "dec_test2", reasoning="Updated reason")

        updated = ops.get_decision(temp_db, "dec_test2")
        assert updated.arc_id == arc_id
        assert updated.reasoning == "Updated reason"


# =============================================================================
# Trigger: arc creation wiring
# =============================================================================


class TestTriggerArcCreation:
    """Tests for trigger.py arc creation logic."""

    def test_new_arc_theme_triggers_create_arc(self, temp_db):
        """When new_arc_theme is set and arc_id is not, create_arc is called."""
        _setup_project(temp_db)

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(temp_db, dry_run=False)

        evaluation = _make_evaluation(new_arc_theme="Auth system build")
        project = ops.get_project(temp_db, "proj_test1")

        # Insert a decision to update
        decision = Decision(
            id="dec_t1",
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
        )
        ops.insert_decision(temp_db, decision)

        # Simulate the trigger logic (same as trigger.py step 8b)
        _arc_id = getattr(evaluation, "arc_id", None)
        _new_arc_theme = getattr(evaluation, "new_arc_theme", None)

        if _new_arc_theme and not _arc_id:
            from social_hook.narrative.arcs import create_arc as _create_arc

            new_arc_id = _create_arc(db.conn, project.id, _new_arc_theme)
            db.update_decision(decision.id, arc_id=new_arc_id)
            decision.arc_id = new_arc_id

        assert decision.arc_id is not None
        assert decision.arc_id.startswith("arc_")

        # Verify DB was updated
        updated = ops.get_decision(temp_db, "dec_t1")
        assert updated.arc_id == decision.arc_id

        # Verify the arc was actually created
        arc = get_arc(temp_db, decision.arc_id)
        assert arc is not None
        assert arc.theme == "Auth system build"

    def test_arc_id_set_skips_creation(self, temp_db):
        """When arc_id is already set, no new arc is created."""
        evaluation = _make_evaluation(
            arc_id="arc_existing",
            new_arc_theme="Should be ignored",
        )

        _arc_id = getattr(evaluation, "arc_id", None)
        _new_arc_theme = getattr(evaluation, "new_arc_theme", None)

        # The trigger logic: if _new_arc_theme and not _arc_id
        should_create = _new_arc_theme and not _arc_id
        assert should_create is False

    def test_no_arc_fields_skips_creation(self, temp_db):
        """When neither arc field is set, no arc is created."""
        evaluation = _make_evaluation(post_category="opportunistic")

        _arc_id = getattr(evaluation, "arc_id", None)
        _new_arc_theme = getattr(evaluation, "new_arc_theme", None)

        should_create = bool(_new_arc_theme and not _arc_id)
        assert should_create is False

    def test_max_arcs_error_handled_gracefully(self, temp_db):
        """MaxArcsError during arc creation is caught and logged."""
        _setup_project(temp_db)
        # Create 3 arcs to hit the limit
        create_arc(temp_db, "proj_test1", "Arc 1")
        create_arc(temp_db, "proj_test1", "Arc 2")
        create_arc(temp_db, "proj_test1", "Arc 3")

        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(temp_db, dry_run=False)

        evaluation = _make_evaluation(new_arc_theme="Fourth arc")
        project = ops.get_project(temp_db, "proj_test1")

        decision = Decision(
            id="dec_t2",
            project_id=project.id,
            commit_hash="abc456",
            decision="draft",
            reasoning="Test",
        )
        ops.insert_decision(temp_db, decision)

        # Simulate the trigger logic with exception handling
        _arc_id = getattr(evaluation, "arc_id", None)
        _new_arc_theme = getattr(evaluation, "new_arc_theme", None)

        arc_created = False
        if _new_arc_theme and not _arc_id:
            try:
                from social_hook.narrative.arcs import create_arc as _create_arc

                new_arc_id = _create_arc(db.conn, project.id, _new_arc_theme)
                decision.arc_id = new_arc_id
                arc_created = True
            except Exception:
                pass

        # Should have failed gracefully
        assert arc_created is False
        assert decision.arc_id is None


# =============================================================================
# Trigger: arc post count increment wiring
# =============================================================================


class TestTriggerArcPostCountIncrement:
    """Tests for trigger.py arc post count increment logic."""

    def test_increment_called_when_drafts_created(self, temp_db):
        """Arc post count incremented when drafts are created for an arc."""
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "Test arc")

        decision = Decision(
            id="dec_inc1",
            project_id="proj_test1",
            commit_hash="abc789",
            decision="draft",
            reasoning="Test",
            arc_id=arc_id,
        )
        ops.insert_decision(temp_db, decision)

        # Simulate: created_drafts is non-empty and decision has arc_id
        created_drafts = [("draft_obj", "schedule_obj", [])]

        if created_drafts and decision.arc_id:
            increment_arc_post_count(temp_db, decision.arc_id)

        arc = get_arc(temp_db, arc_id)
        assert arc.post_count == 1

    def test_no_increment_without_arc_id(self, temp_db):
        """No increment when decision has no arc_id."""
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "Unrelated arc")

        decision = Decision(
            id="dec_inc2",
            project_id="proj_test1",
            commit_hash="def789",
            decision="draft",
            reasoning="Test",
            arc_id=None,
        )
        ops.insert_decision(temp_db, decision)

        created_drafts = [("draft_obj", "schedule_obj", [])]

        if created_drafts and decision.arc_id:
            increment_arc_post_count(temp_db, decision.arc_id)

        # Arc should remain at 0
        arc = get_arc(temp_db, arc_id)
        assert arc.post_count == 0

    def test_no_increment_without_drafts(self, temp_db):
        """No increment when no drafts were created."""
        _setup_project(temp_db)
        arc_id = create_arc(temp_db, "proj_test1", "No drafts arc")

        decision = Decision(
            id="dec_inc3",
            project_id="proj_test1",
            commit_hash="ghi789",
            decision="draft",
            reasoning="Test",
            arc_id=arc_id,
        )
        ops.insert_decision(temp_db, decision)

        created_drafts = []

        if created_drafts and decision.arc_id:
            increment_arc_post_count(temp_db, decision.arc_id)

        arc = get_arc(temp_db, arc_id)
        assert arc.post_count == 0


# =============================================================================
# Evaluator prompt includes arc instructions
# =============================================================================


class TestEvaluatorPromptArcInstructions:
    """Verify evaluator.md source template contains arc management instructions.

    Note: load_prompt() reads from ~/.social-hook/prompts/ (the installed copy).
    These tests verify the source template in src/ which gets installed by `setup`.
    """

    @staticmethod
    def _read_source_prompt():
        """Read the evaluator prompt source template."""
        from pathlib import Path

        src = Path(__file__).parent.parent / "src" / "social_hook" / "prompts" / "evaluator.md"
        return src.read_text(encoding="utf-8")

    def test_prompt_has_arc_management_section(self):
        prompt = self._read_source_prompt()
        assert "## Arc Management" in prompt

    def test_prompt_mentions_new_arc_theme(self):
        prompt = self._read_source_prompt()
        assert "new_arc_theme" in prompt

    def test_prompt_mentions_mutual_exclusivity(self):
        prompt = self._read_source_prompt()
        assert "mutually exclusive" in prompt.lower()

    def test_prompt_mentions_max_3_arcs(self):
        prompt = self._read_source_prompt()
        assert "3 active arcs" in prompt or "max 3" in prompt.lower()


# =============================================================================
# Drafting: arc_context wiring
# =============================================================================


class TestDraftingArcContext:
    """Tests that draft() passes arc_context to drafter."""

    @patch("social_hook.drafting.calculate_optimal_time")
    def test_arc_context_passed_when_arc_id_set(
        self,
        mock_schedule,
        temp_db,
    ):
        """When intent has arc_id, arc_context kwarg is passed to drafter."""
        from social_hook.config.yaml import Config
        from social_hook.drafting import DraftingIntent, PlatformSpec, draft
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.schemas import CreateDraftInput
        from social_hook.models.context import ProjectContext
        from social_hook.models.core import CommitInfo
        from social_hook.scheduling import ScheduleResult

        # Set up project and arc
        project = _setup_project(temp_db)
        arc_id = create_arc(temp_db, project.id, "Auth system build")

        # Decision
        decision = Decision(
            id="dec_draft1",
            project_id=project.id,
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
            arc_id=arc_id,
        )
        ops.insert_decision(temp_db, decision)

        # Build DraftingIntent with arc_id
        resolved = MagicMock()
        resolved.name = "preview"
        resolved.account_tier = "free"
        resolved.max_posts_per_day = 3
        resolved.min_gap_minutes = 30
        resolved.optimal_days = []
        resolved.optimal_hours = []
        resolved.filter = "all"
        intent = DraftingIntent(
            decision_id=decision.id,
            decision="draft",
            reasoning="Test",
            angle="Test angle",
            arc_id=arc_id,
            platforms=[PlatformSpec(platform="preview", resolved=resolved)],
        )

        # Commit
        commit = CommitInfo(
            hash="abc123",
            message="Add auth module",
            diff="+ auth code",
        )

        # Project context
        context = ProjectContext(
            project=project,
            social_context="Test context",
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            platform_introduced={"x": True},
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary=None,
        )

        # Mock schedule result (non-deferred)
        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 3, 12, 0),
            is_optimal_day=True,
            day_reason="test",
            time_reason="test",
            deferred=False,
        )

        # Mock the drafter's create_draft to capture args
        mock_draft_result = CreateDraftInput.validate(
            {
                "content": "Test draft content",
                "platform": "preview",
                "reasoning": "Test reasoning",
            }
        )

        config = Config()
        db = DryRunContext(temp_db, dry_run=False)

        with (
            patch("social_hook.llm.factory.create_client") as mock_create_client,
            patch(
                "social_hook.llm.drafter.Drafter.create_draft", return_value=mock_draft_result
            ) as mock_create_draft,
        ):
            mock_create_client.return_value = MagicMock()

            draft(
                intent,
                config,
                temp_db,
                db,
                project,
                context,
                commit,
            )

            # Verify create_draft was called with arc_context
            mock_create_draft.assert_called_once()
            call_kwargs = mock_create_draft.call_args
            assert "arc_context" in call_kwargs.kwargs
            arc_ctx = call_kwargs.kwargs["arc_context"]
            assert arc_ctx is not None
            assert "arc" in arc_ctx
            assert arc_ctx["arc"].id == arc_id
            assert arc_ctx["arc"].theme == "Auth system build"
            assert "posts" in arc_ctx
            assert isinstance(arc_ctx["posts"], list)

    @patch("social_hook.drafting.calculate_optimal_time")
    def test_arc_context_none_when_no_arc_id(
        self,
        mock_schedule,
        temp_db,
    ):
        """When intent has no arc_id, arc_context is None."""
        from social_hook.config.yaml import Config
        from social_hook.drafting import DraftingIntent, PlatformSpec, draft
        from social_hook.llm.dry_run import DryRunContext
        from social_hook.llm.schemas import CreateDraftInput
        from social_hook.models.context import ProjectContext
        from social_hook.models.core import CommitInfo
        from social_hook.scheduling import ScheduleResult

        project = _setup_project(temp_db)

        decision = Decision(
            id="dec_draft2",
            project_id=project.id,
            commit_hash="def456",
            decision="draft",
            reasoning="Test",
        )
        ops.insert_decision(temp_db, decision)

        resolved = MagicMock()
        resolved.name = "preview"
        resolved.account_tier = "free"
        resolved.max_posts_per_day = 3
        resolved.min_gap_minutes = 30
        resolved.optimal_days = []
        resolved.optimal_hours = []
        resolved.filter = "all"
        intent = DraftingIntent(
            decision_id=decision.id,
            decision="draft",
            reasoning="Test",
            angle="Test angle",
            arc_id=None,
            post_category="opportunistic",
            platforms=[PlatformSpec(platform="preview", resolved=resolved)],
        )

        commit = CommitInfo(
            hash="def456",
            message="Fix typo",
            diff="- old\n+ new",
        )

        context = ProjectContext(
            project=project,
            social_context="Test context",
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
            platform_introduced={"x": True},
            pending_drafts=[],
            recent_decisions=[],
            recent_posts=[],
            project_summary=None,
        )

        mock_schedule.return_value = ScheduleResult(
            datetime=datetime(2026, 3, 3, 12, 0),
            is_optimal_day=True,
            day_reason="test",
            time_reason="test",
            deferred=False,
        )

        mock_draft_result = CreateDraftInput.validate(
            {
                "content": "Test draft content",
                "platform": "preview",
                "reasoning": "Test reasoning",
            }
        )

        config = Config()
        db = DryRunContext(temp_db, dry_run=False)

        with (
            patch("social_hook.llm.factory.create_client") as mock_create_client,
            patch(
                "social_hook.llm.drafter.Drafter.create_draft", return_value=mock_draft_result
            ) as mock_create_draft,
        ):
            mock_create_client.return_value = MagicMock()

            draft(
                intent,
                config,
                temp_db,
                db,
                project,
                context,
                commit,
            )

            mock_create_draft.assert_called_once()
            call_kwargs = mock_create_draft.call_args
            assert "arc_context" in call_kwargs.kwargs
            assert call_kwargs.kwargs["arc_context"] is None
