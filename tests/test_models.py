"""Tests for domain models (T3)."""

from datetime import datetime

import pytest

from social_hook.models import (
    EDITABLE_STATUSES,
    PENDING_STATUSES,
    TERMINAL_STATUSES,
    Arc,
    ArcStatus,
    Decision,
    DecisionType,
    Draft,
    DraftStatus,
    EpisodeType,
    Lifecycle,
    LifecyclePhase,
    PostCategory,
    PostFormat,
    Project,
    UsageLog,
    is_draftable,
    is_held,
)

# =============================================================================
# T3: Core Data Models
# =============================================================================


class TestEnums:
    """T3: Enum tests."""

    def test_draft_status_values(self):
        """DraftStatus.SCHEDULED.value returns 'scheduled'."""
        assert DraftStatus.SCHEDULED.value == "scheduled"
        assert DraftStatus.DRAFT.value == "draft"
        assert DraftStatus.APPROVED.value == "approved"
        assert DraftStatus.POSTED.value == "posted"
        assert DraftStatus.REJECTED.value == "rejected"
        assert DraftStatus.FAILED.value == "failed"
        assert DraftStatus.SUPERSEDED.value == "superseded"
        assert DraftStatus.CANCELLED.value == "cancelled"
        assert DraftStatus.DEFERRED.value == "deferred"

    def test_decision_type_values(self):
        """DecisionType values are correct."""
        assert DecisionType.DRAFT.value == "draft"
        assert DecisionType.HOLD.value == "hold"
        assert DecisionType.SKIP.value == "skip"
        assert DecisionType.IMPORTED.value == "imported"
        assert DecisionType.DEFERRED_EVAL.value == "deferred_eval"

    def test_post_format_values(self):
        """PostFormat values are correct."""
        assert PostFormat.SINGLE.value == "single"
        assert PostFormat.THREAD.value == "thread"
        assert PostFormat.QUOTE.value == "quote"
        assert PostFormat.REPLY.value == "reply"

    def test_episode_type_values(self):
        """EpisodeType values are correct."""
        assert EpisodeType.DECISION.value == "decision"
        assert EpisodeType.BEFORE_AFTER.value == "before_after"
        assert EpisodeType.DEMO_PROOF.value == "demo_proof"
        assert EpisodeType.MILESTONE.value == "milestone"
        assert EpisodeType.POSTMORTEM.value == "postmortem"
        assert EpisodeType.LAUNCH.value == "launch"
        assert EpisodeType.SYNTHESIS.value == "synthesis"

    def test_post_category_values(self):
        """PostCategory values are correct."""
        assert PostCategory.ARC.value == "arc"
        assert PostCategory.OPPORTUNISTIC.value == "opportunistic"
        assert PostCategory.EXPERIMENT.value == "experiment"

    def test_lifecycle_phase_values(self):
        """LifecyclePhase values are correct."""
        assert LifecyclePhase.RESEARCH.value == "research"
        assert LifecyclePhase.BUILD.value == "build"
        assert LifecyclePhase.DEMO.value == "demo"
        assert LifecyclePhase.LAUNCH.value == "launch"
        assert LifecyclePhase.POST_LAUNCH.value == "post_launch"

    def test_arc_status_values(self):
        """ArcStatus values are correct."""
        assert ArcStatus.ACTIVE.value == "active"
        assert ArcStatus.COMPLETED.value == "completed"
        assert ArcStatus.ABANDONED.value == "abandoned"


class TestProjectModel:
    """T3: Project model tests."""

    def test_create_valid_project(self):
        """Create valid Project instance."""
        project = Project(
            id="project_123",
            name="test-project",
            repo_path="/tmp/test",
        )
        assert project.id == "project_123"
        assert project.name == "test-project"
        assert project.repo_path == "/tmp/test"

    def test_project_to_dict(self):
        """Serialize Project to dict."""
        project = Project(
            id="project_123",
            name="test-project",
            repo_path="/tmp/test",
            created_at=datetime(2026, 1, 15, 10, 30, 0),
        )

        d = project.to_dict()
        assert d["id"] == "project_123"
        assert d["name"] == "test-project"
        assert "audience_introduced" not in d
        assert d["created_at"] == "2026-01-15T10:30:00"

    def test_project_from_dict(self):
        """Deserialize Project from dict."""
        d = {
            "id": "project_123",
            "name": "test-project",
            "repo_path": "/tmp/test",
            "created_at": "2026-01-15T10:30:00",
        }

        project = Project.from_dict(d)
        assert project.id == "project_123"
        assert project.created_at == datetime(2026, 1, 15, 10, 30, 0)

    def test_project_to_row(self):
        """Serialize Project to DB row tuple."""
        project = Project(
            id="project_123",
            name="test-project",
            repo_path="/tmp/test",
        )

        row = project.to_row()
        assert row[0] == "project_123"
        assert row[1] == "test-project"
        assert row[2] == "/tmp/test"


class TestDraftModel:
    """T3: Draft model tests."""

    def test_create_valid_draft(self):
        """Create valid Draft instance."""
        draft = Draft(
            id="draft_123",
            project_id="project_123",
            decision_id="decision_123",
            platform="x",
            content="Test content",
        )
        assert draft.status == "draft"

    def test_draft_with_invalid_status_raises(self):
        """Create Draft with invalid status raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Draft(
                id="draft_123",
                project_id="project_123",
                decision_id="decision_123",
                platform="x",
                content="Test",
                status="invalid",
            )

        assert "Invalid status" in str(exc_info.value)

    def test_draft_to_dict_with_datetime(self):
        """Serialize Draft with datetime fields."""
        draft = Draft(
            id="draft_123",
            project_id="project_123",
            decision_id="decision_123",
            platform="x",
            content="Test",
            scheduled_time=datetime(2026, 1, 15, 14, 0, 0),
        )

        d = draft.to_dict()
        assert d["scheduled_time"] == "2026-01-15T14:00:00"

    def test_draft_from_dict_with_media_paths(self):
        """Deserialize Draft with JSON media_paths."""
        d = {
            "id": "draft_123",
            "project_id": "project_123",
            "decision_id": "decision_123",
            "platform": "x",
            "content": "Test",
            "media_paths": '["path1.png", "path2.png"]',
        }

        draft = Draft.from_dict(d)
        assert draft.media_paths == ["path1.png", "path2.png"]


class TestDecisionModel:
    """T3: Decision model tests."""

    def test_create_valid_decision(self):
        """Create valid Decision instance."""
        decision = Decision(
            id="decision_123",
            project_id="project_123",
            commit_hash="abc123",
            decision="draft",
            reasoning="Important feature",
        )
        assert decision.decision == "draft"

    def test_decision_with_invalid_decision_raises(self):
        """Create Decision with invalid decision value raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Decision(
                id="decision_123",
                project_id="project_123",
                commit_hash="abc123",
                decision="invalid_decision",
                reasoning="Test",
            )

        assert "Invalid decision" in str(exc_info.value)

    def test_decision_with_invalid_episode_type_raises(self):
        """Create Decision with invalid episode_type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Decision(
                id="decision_123",
                project_id="project_123",
                commit_hash="abc123",
                decision="draft",
                reasoning="Test",
                episode_type="invalid_episode",
            )

        assert "Invalid episode_type" in str(exc_info.value)

    def test_decision_to_dict_with_platforms(self):
        """Serialize Decision with platforms dict."""
        decision = Decision(
            id="decision_123",
            project_id="project_123",
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
            platforms={"x": "drafted", "linkedin": "skipped:not_relevant"},
        )

        d = decision.to_dict()
        assert d["platforms"]["x"] == "drafted"

    def test_decision_to_row_length(self):
        """Decision.to_row() returns correct number of columns."""
        decision = Decision(
            id="decision_123",
            project_id="project_123",
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
            commit_message="Add auth module",
        )
        assert len(decision.to_row()) == 19

    def test_decision_to_dict_includes_commit_message(self):
        """Decision.to_dict() includes commit_message."""
        decision = Decision(
            id="decision_123",
            project_id="project_123",
            commit_hash="abc123",
            decision="draft",
            reasoning="Test",
            commit_message="Add auth module",
        )
        d = decision.to_dict()
        assert d["commit_message"] == "Add auth module"


class TestLifecycleModel:
    """T3: Lifecycle model tests."""

    def test_create_valid_lifecycle(self):
        """Create valid Lifecycle instance."""
        lifecycle = Lifecycle(
            project_id="project_123",
            phase="build",
            confidence=0.75,
        )
        assert lifecycle.phase == "build"

    def test_lifecycle_with_invalid_phase_raises(self):
        """Create Lifecycle with invalid phase raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Lifecycle(
                project_id="project_123",
                phase="invalid_phase",
            )

        assert "Invalid phase" in str(exc_info.value)

    def test_lifecycle_with_invalid_confidence_raises(self):
        """Create Lifecycle with confidence outside 0-1 raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Lifecycle(
                project_id="project_123",
                confidence=1.5,
            )

        assert "Confidence must be between" in str(exc_info.value)


class TestArcModel:
    """T3: Arc model tests."""

    def test_create_valid_arc(self):
        """Create valid Arc instance."""
        arc = Arc(
            id="arc_123",
            project_id="project_123",
            theme="Building the content brain",
        )
        assert arc.status == "active"

    def test_arc_with_invalid_status_raises(self):
        """Create Arc with invalid status raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Arc(
                id="arc_123",
                project_id="project_123",
                theme="Test",
                status="invalid_status",
            )

        assert "Invalid status" in str(exc_info.value)


class TestDecisionNewFields:
    """Tests for evaluator rework Decision fields."""

    def test_decision_to_row_column_count(self):
        """Decision.to_row() returns 18-element tuple."""
        d = Decision(
            id="test", project_id="p", commit_hash="abc", decision="draft", reasoning="test"
        )
        assert len(d.to_row()) == 19

    def test_decision_new_types_valid(self):
        """New decision types (draft, hold, skip) are accepted."""
        for dtype in ("draft", "hold", "skip"):
            d = Decision(id="t", project_id="p", commit_hash="c", decision=dtype, reasoning="r")
            assert d.decision == dtype

    def test_decision_episode_tags_roundtrip(self):
        """episode_tags serializes to JSON and deserializes back."""
        d = Decision(
            id="t",
            project_id="p",
            commit_hash="c",
            decision="draft",
            reasoning="r",
            episode_tags=["milestone", "demo"],
        )
        d_dict = d.to_dict()
        assert d_dict["episode_tags"] == ["milestone", "demo"]

        # Simulate SQLite round-trip (JSON string)
        d_dict["episode_tags"] = '["milestone", "demo"]'
        restored = Decision.from_dict(d_dict)
        assert restored.episode_tags == ["milestone", "demo"]

    def test_decision_targets_roundtrip(self):
        """targets serializes to JSON and deserializes back."""
        d = Decision(
            id="t",
            project_id="p",
            commit_hash="c",
            decision="draft",
            reasoning="r",
            targets={"x": {"max_length": 280}},
        )
        row = d.to_row()
        assert '"x"' in row[13]  # targets is at index 13

        # from_dict with JSON string
        d_dict = d.to_dict()
        d_dict["targets"] = '{"x": {"max_length": 280}}'
        restored = Decision.from_dict(d_dict)
        assert restored.targets == {"x": {"max_length": 280}}

    def test_decision_consolidate_with_roundtrip(self):
        """consolidate_with serializes and deserializes correctly."""
        d = Decision(
            id="t",
            project_id="p",
            commit_hash="c",
            decision="hold",
            reasoning="r",
            consolidate_with=["abc123", "def456"],
        )
        row = d.to_row()
        assert row[15] is not None  # consolidate_with is at index 15

        d2 = Decision(
            id="t2",
            project_id="p",
            commit_hash="c2",
            decision="draft",
            reasoning="r",
            consolidate_with=None,
        )
        assert d2.to_row()[15] is None


class TestDecisionReferencePosts:
    """Tests for reference_posts field on Decision."""

    def test_reference_posts_roundtrip_dict(self):
        """reference_posts round-trips through to_dict/from_dict."""
        d = Decision(
            id="t",
            project_id="p",
            commit_hash="c",
            decision="draft",
            reasoning="r",
            reference_posts=["post_abc", "post_def"],
        )
        d_dict = d.to_dict()
        assert d_dict["reference_posts"] == ["post_abc", "post_def"]

        # Simulate SQLite round-trip (JSON string)
        d_dict["reference_posts"] = '["post_abc", "post_def"]'
        restored = Decision.from_dict(d_dict)
        assert restored.reference_posts == ["post_abc", "post_def"]

    def test_reference_posts_none(self):
        """reference_posts defaults to None."""
        d = Decision(id="t", project_id="p", commit_hash="c", decision="draft", reasoning="r")
        assert d.reference_posts is None
        assert d.to_dict()["reference_posts"] is None

    def test_reference_posts_in_to_row(self):
        """reference_posts is serialized as JSON in to_row()."""
        d = Decision(
            id="t",
            project_id="p",
            commit_hash="c",
            decision="draft",
            reasoning="r",
            reference_posts=["post_abc"],
        )
        row = d.to_row()
        assert row[16] == '["post_abc"]'

    def test_reference_posts_none_in_to_row(self):
        """reference_posts=None produces None in to_row()."""
        d = Decision(id="t", project_id="p", commit_hash="c", decision="draft", reasoning="r")
        assert d.to_row()[16] is None

    def test_to_row_length_with_reference_posts(self):
        """Decision.to_row() returns 18-element tuple."""
        d = Decision(id="t", project_id="p", commit_hash="c", decision="draft", reasoning="r")
        assert len(d.to_row()) == 19


class TestDecisionImported:
    """Tests for the imported decision type and branch field."""

    def test_imported_decision_accepted(self):
        """Decision with decision='imported' is accepted by __post_init__."""
        d = Decision(
            id="t",
            project_id="p",
            commit_hash="c",
            decision="imported",
            reasoning="Historical commit",
        )
        assert d.decision == "imported"

    def test_decision_branch_field(self):
        """Decision.branch field round-trips through to_dict/from_dict."""
        d = Decision(
            id="t", project_id="p", commit_hash="c", decision="draft", reasoning="r", branch="main"
        )
        assert d.branch == "main"
        d_dict = d.to_dict()
        assert d_dict["branch"] == "main"
        restored = Decision.from_dict(d_dict)
        assert restored.branch == "main"

    def test_decision_branch_in_to_row(self):
        """branch is the 18th element (index 17) in to_row()."""
        d = Decision(
            id="t",
            project_id="p",
            commit_hash="c",
            decision="draft",
            reasoning="r",
            branch="develop",
        )
        row = d.to_row()
        assert row[17] == "develop"

    def test_decision_branch_none_default(self):
        """branch defaults to None."""
        d = Decision(id="t", project_id="p", commit_hash="c", decision="draft", reasoning="r")
        assert d.branch is None
        assert d.to_row()[17] is None


class TestDraftNewFields:
    """Tests for evaluator rework Draft fields."""

    def test_draft_to_row_column_count(self):
        """Draft.to_row() returns 24-element tuple."""
        d = Draft(id="test", project_id="p", decision_id="d", platform="x", content="hello")
        assert len(d.to_row()) == 24

    def test_draft_intro_flag(self):
        """is_intro flag serializes correctly."""
        d = Draft(
            id="t", project_id="p", decision_id="d", platform="x", content="hi", is_intro=True
        )
        assert d.to_dict()["is_intro"] is True
        row = d.to_row()
        assert row[16] == 1  # is_intro position

    def test_draft_post_format(self):
        """post_format field round-trips."""
        d = Draft(
            id="t",
            project_id="p",
            decision_id="d",
            platform="x",
            content="hi",
            post_format="thread",
        )
        assert d.to_dict()["post_format"] == "thread"
        assert d.to_row()[17] == "thread"

    def test_draft_from_dict_new_fields(self):
        """Draft.from_dict() parses new fields."""
        d_dict = {
            "id": "t",
            "project_id": "p",
            "decision_id": "d",
            "platform": "x",
            "content": "hi",
            "is_intro": 1,
            "post_format": "reply",
            "reference_post_id": "post_abc",
        }
        d = Draft.from_dict(d_dict)
        assert d.is_intro is True
        assert d.post_format == "reply"
        assert d.reference_post_id == "post_abc"


class TestDeferredEvalDecision:
    """Tests for deferred_eval decision type and trigger_source field."""

    def test_deferred_eval_enum_exists(self):
        """DecisionType.DEFERRED_EVAL exists with correct value."""
        assert DecisionType.DEFERRED_EVAL.value == "deferred_eval"

    def test_decision_with_deferred_eval(self):
        """Decision with deferred_eval type is valid."""
        d = Decision(
            id="test",
            project_id="p",
            commit_hash="abc",
            decision="deferred_eval",
            reasoning="Rate limited",
        )
        assert d.decision == "deferred_eval"

    def test_decision_trigger_source_default(self):
        """Decision.trigger_source defaults to 'commit'."""
        d = Decision(
            id="test",
            project_id="p",
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        assert d.trigger_source == "commit"

    def test_decision_trigger_source_roundtrip(self):
        """Decision trigger_source survives to_dict/from_dict roundtrip."""
        d = Decision(
            id="test",
            project_id="p",
            commit_hash="abc",
            decision="deferred_eval",
            reasoning="Rate limited",
            trigger_source="auto",
        )
        d_dict = d.to_dict()
        assert d_dict["trigger_source"] == "auto"

        d2 = Decision.from_dict(d_dict)
        assert d2.trigger_source == "auto"
        assert d2.decision == "deferred_eval"

    def test_decision_from_dict_missing_trigger_source(self):
        """Decision.from_dict handles missing trigger_source (backward compat)."""
        d_dict = {
            "id": "test",
            "project_id": "p",
            "commit_hash": "abc",
            "decision": "draft",
            "reasoning": "test",
        }
        d = Decision.from_dict(d_dict)
        assert d.trigger_source == "commit"

    def test_decision_to_row_includes_trigger_source(self):
        """Decision.to_row() includes trigger_source as last element."""
        d = Decision(
            id="test",
            project_id="p",
            commit_hash="abc",
            decision="draft",
            reasoning="test",
            trigger_source="scheduler",
        )
        row = d.to_row()
        assert row[-1] == "scheduler"


class TestUsageLogTriggerSource:
    """Tests for trigger_source field on UsageLog."""

    def test_usage_log_trigger_source_default(self):
        """UsageLog.trigger_source defaults to 'auto'."""
        u = UsageLog(id="u1", operation_type="evaluate", model="opus")
        assert u.trigger_source == "auto"

    def test_usage_log_trigger_source_roundtrip(self):
        """UsageLog trigger_source survives to_dict/from_dict roundtrip."""
        u = UsageLog(
            id="u1",
            operation_type="evaluate",
            model="opus",
            trigger_source="manual",
        )
        u_dict = u.to_dict()
        assert u_dict["trigger_source"] == "manual"

        u2 = UsageLog.from_dict(u_dict)
        assert u2.trigger_source == "manual"

    def test_usage_log_from_dict_missing_trigger_source(self):
        """UsageLog.from_dict handles missing trigger_source (backward compat)."""
        u_dict = {
            "id": "u1",
            "operation_type": "evaluate",
            "model": "opus",
        }
        u = UsageLog.from_dict(u_dict)
        assert u.trigger_source == "auto"

    def test_usage_log_to_row_includes_trigger_source(self):
        """UsageLog.to_row() includes trigger_source."""
        u = UsageLog(
            id="u1",
            operation_type="evaluate",
            model="opus",
            trigger_source="manual",
        )
        row = u.to_row()
        assert len(row) == 11
        assert row[-1] == "manual"


class TestStatusGroups:
    """Tests for status group frozensets."""

    def test_terminal_statuses_values(self):
        """TERMINAL_STATUSES contains exactly the expected values."""
        assert {"posted", "rejected", "cancelled", "superseded"} == TERMINAL_STATUSES

    def test_pending_statuses_values(self):
        """PENDING_STATUSES contains exactly the expected values."""
        assert {"draft", "approved", "scheduled", "deferred"} == PENDING_STATUSES

    def test_editable_statuses_values(self):
        """EDITABLE_STATUSES contains exactly the expected values."""
        assert {"draft", "deferred"} == EDITABLE_STATUSES

    def test_editable_subset_of_pending(self):
        """EDITABLE_STATUSES is a proper subset of PENDING_STATUSES."""
        assert EDITABLE_STATUSES < PENDING_STATUSES

    def test_status_groups_cover_all_enum_values(self):
        """TERMINAL | PENDING | {failed} covers every DraftStatus value."""
        all_values = {s.value for s in DraftStatus}
        assert TERMINAL_STATUSES | PENDING_STATUSES | {"failed"} == all_values


class TestHelperFunctions:
    """Tests for is_draftable and is_held helpers."""

    def test_is_draftable(self):
        assert is_draftable("draft") is True
        assert is_draftable("hold") is False
        assert is_draftable("skip") is False
        # Old values no longer valid
        assert is_draftable("post_worthy") is False

    def test_is_held(self):
        assert is_held("hold") is True
        assert is_held("draft") is False
        # Old values no longer valid
        assert is_held("consolidate") is False
        assert is_held("skip") is False
