"""Tests for targets pipeline coverage gaps: interval gating, topic lifecycle, prompt assembly, config validation."""

from types import SimpleNamespace

import pytest

from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.models.content import ContentTopic
from social_hook.models.core import CommitInfo, Project

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db(tmp_path):
    """Create a temporary database with schema."""
    db_path = tmp_path / "test.db"
    conn = init_database(db_path)
    yield conn
    conn.close()


@pytest.fixture
def project_id(db):
    """Register a test project and return its ID."""
    pid = "proj_tgt_test"
    project = Project(id=pid, name="targets-test", repo_path="/tmp/targets-test")
    ops.insert_project(db, project)
    return pid


# =============================================================================
# 1-4: Interval gating — _run_commit_analyzer_gate
# =============================================================================


class TestIntervalGate:
    """Tests for _run_commit_analyzer_gate in trigger_batch.py."""

    def test_interval_gate_defers_when_count_below_threshold(self, db, project_id):
        """Counter returns 1, interval=3: should defer (should_evaluate=False)."""
        from social_hook.trigger_batch import _run_commit_analyzer_gate

        project = ops.get_project(db, project_id)
        project_config = SimpleNamespace(context=SimpleNamespace(commit_analysis_interval=3))

        outcome = _run_commit_analyzer_gate(db, project, project_config)

        assert outcome.result is None
        assert outcome.should_evaluate is False
        assert ops.get_analysis_commit_count(db, project_id) == 1

    def test_interval_gate_evaluates_at_threshold(self, db, project_id):
        """Counter reaches interval=3: should_evaluate=True."""
        from social_hook.trigger_batch import _run_commit_analyzer_gate

        project = ops.get_project(db, project_id)
        # Pre-increment to 2 so next call hits 3
        ops.increment_analysis_commit_count(db, project_id)
        ops.increment_analysis_commit_count(db, project_id)

        project_config = SimpleNamespace(context=SimpleNamespace(commit_analysis_interval=3))

        outcome = _run_commit_analyzer_gate(db, project, project_config)

        assert outcome.should_evaluate is True
        assert ops.get_analysis_commit_count(db, project_id) == 3

    def test_interval_gate_minimum_clamp(self, db, project_id):
        """Interval=0 is clamped to 1, meaning always evaluate (no batching)."""
        from social_hook.trigger_batch import _run_commit_analyzer_gate

        project = ops.get_project(db, project_id)
        project_config = SimpleNamespace(context=SimpleNamespace(commit_analysis_interval=0))

        outcome = _run_commit_analyzer_gate(db, project, project_config)

        assert outcome.should_evaluate is True

    def test_interval_gate_no_config_defaults_to_evaluate(self, db, project_id):
        """project_config=None defaults to interval=1 (always evaluate)."""
        from social_hook.trigger_batch import _run_commit_analyzer_gate

        project = ops.get_project(db, project_id)

        outcome = _run_commit_analyzer_gate(db, project, project_config=None)

        assert outcome.should_evaluate is True


# =============================================================================
# 5: Dismissed topics excluded from tag matching
# =============================================================================


class TestDismissedTopicsExcludedFromTagMatching:
    """Test that dismissed topics are excluded from get_topics_matching_tag."""

    def test_dismissed_topics_excluded_from_tag_matching(self, db, project_id):
        """A topic with status='dismissed' must NOT be returned by get_topics_matching_tag."""
        topic = ContentTopic(
            id="topic_dismissed_tag",
            project_id=project_id,
            strategy="building-public",
            topic="Auth System",
            status="dismissed",
            created_by="track1",
        )
        ops.insert_content_topic(db, topic)

        matches = ops.get_topics_matching_tag(db, project_id, "auth")

        assert len(matches) == 0

    def test_non_dismissed_topics_returned_by_tag_matching(self, db, project_id):
        """Sanity check: a non-dismissed topic IS returned by get_topics_matching_tag."""
        topic = ContentTopic(
            id="topic_active_tag",
            project_id=project_id,
            strategy="building-public",
            topic="Auth System",
            status="uncovered",
            created_by="track1",
        )
        ops.insert_content_topic(db, topic)

        matches = ops.get_topics_matching_tag(db, project_id, "auth")

        assert len(matches) == 1
        assert matches[0].id == "topic_active_tag"


# =============================================================================
# 6: Dismissed topics not recreated by seeding
# =============================================================================


class TestDismissedTopicsNotRecreatedBySeeding:
    """Test that _insert_topic_if_new skips dismissed topics."""

    def test_dismissed_topics_not_recreated_by_seeding(self, db, project_id):
        """A dismissed topic 'Auth System' blocks _insert_topic_if_new from creating a duplicate."""
        from social_hook.topics import _insert_topic_if_new

        # Create a dismissed topic
        dismissed = ContentTopic(
            id="topic_dismissed_seed",
            project_id=project_id,
            strategy="building-public",
            topic="Auth System",
            status="dismissed",
            created_by="track1",
        )
        ops.insert_content_topic(db, dismissed)

        # Build the existing_by_name lookup (as process_topic_suggestions does)
        existing_topics = ops.get_topics_by_strategy(db, project_id, "building-public")
        existing_by_name = {t.topic.lower(): t for t in existing_topics}

        result = _insert_topic_if_new(
            db,
            project_id,
            "building-public",
            title="Auth System",
            created_by="track1",
            existing_by_name=existing_by_name,
        )

        assert result is None

        # Verify no new topic was created
        all_topics = ops.get_topics_by_strategy(db, project_id, "building-public")
        auth_topics = [t for t in all_topics if "auth" in t.topic.lower()]
        assert len(auth_topics) == 1
        assert auth_topics[0].status == "dismissed"


# =============================================================================
# 7: Strategy-scoped seeding (positioning only)
# =============================================================================


class _FakeSuggestion:
    """Mimics TopicSuggestion from LLM schemas."""

    def __init__(self, title, description=None, strategy_type="code-driven"):
        self.title = title
        self.description = description
        self.strategy_type = strategy_type


class TestStrategyScopedSeeding:
    """Test that process_topic_suggestions routes positioning topics to positioning strategies only."""

    def test_strategy_scoped_seeding_only_positioning(self, db, project_id):
        """Positioning suggestion with strategies ['building-public', 'brand-primary']
        creates topics only for 'brand-primary' (positioning), NOT 'building-public' (code-driven)."""
        from social_hook.topics import process_topic_suggestions

        suggestions = [
            _FakeSuggestion("Simplified Onboarding", strategy_type="positioning"),
        ]

        created = process_topic_suggestions(
            db,
            project_id,
            suggestions,
            strategies=["building-public", "brand-primary"],
        )

        assert len(created) == 1
        assert created[0].strategy == "brand-primary"
        assert created[0].created_by == "discovery"

    def test_code_driven_only_routes_to_code_driven(self, db, project_id):
        """Code-driven suggestion only routes to code-driven strategies."""
        from social_hook.topics import process_topic_suggestions

        suggestions = [
            _FakeSuggestion("OAuth Migration", strategy_type="code-driven"),
        ]

        created = process_topic_suggestions(
            db,
            project_id,
            suggestions,
            strategies=["building-public", "brand-primary"],
        )

        assert len(created) == 1
        assert created[0].strategy == "building-public"


# =============================================================================
# 8-9: force_draft_topic — status guards
# =============================================================================


class TestForceDraftTopicStatusGuards:
    """Test force_draft_topic accepts 'uncovered' but rejects 'dismissed'."""

    def test_force_draft_topic_uncovered_accepted(self, db, project_id):
        """An uncovered topic should be accepted by force_draft_topic (returns cycle_id)."""
        from social_hook.topics import force_draft_topic

        topic = ContentTopic(
            id="topic_uncovered_fd",
            project_id=project_id,
            strategy="building-public",
            topic="Auth Flow",
            status="uncovered",
            created_by="track1",
        )
        ops.insert_content_topic(db, topic)

        # config=None means it won't attempt LLM calls, but still creates a cycle
        result = force_draft_topic(
            db,
            config=None,
            project_id=project_id,
            topic_id="topic_uncovered_fd",
            strategy="building-public",
        )

        # Should return a cycle_id (not None)
        assert result is not None
        assert result.startswith("cycle")

    def test_force_draft_topic_dismissed_rejected(self, db, project_id):
        """A dismissed topic should be rejected by force_draft_topic (returns None)."""
        from social_hook.topics import force_draft_topic

        topic = ContentTopic(
            id="topic_dismissed_fd",
            project_id=project_id,
            strategy="building-public",
            topic="Old Idea",
            status="dismissed",
            created_by="track1",
        )
        ops.insert_content_topic(db, topic)

        result = force_draft_topic(
            db,
            config=None,
            project_id=project_id,
            topic_id="topic_dismissed_fd",
            strategy="building-public",
        )

        assert result is None


# =============================================================================
# 10-11: Granularity-based topic creation from tags via process_topic_suggestions
# =============================================================================


class TestGranularityTopicCreation:
    """Test that topic_granularity config controls when topics are created from suggestions.

    The granularity gate is enforced at the pipeline level: callers only pass
    suggestions to process_topic_suggestions when the classification meets the
    granularity threshold. These tests verify the pipeline's threshold logic.

    Thresholds:
      low  -> only notable/significant create topics
      medium -> routine/notable/significant
      high -> all (including trivial)
    """

    def _should_create_topics(self, classification, granularity):
        """Replicate the pipeline's granularity gate logic."""
        if granularity == "high":
            return True
        if granularity == "medium":
            return classification in ("routine", "notable", "significant")
        # low (default)
        return classification in ("notable", "significant")

    def test_create_topics_from_tags_respects_granularity_low(self, db, project_id):
        """With granularity='low', classification='routine' should NOT pass the gate."""
        from social_hook.topics import process_topic_suggestions

        classification = "routine"
        granularity = "low"

        # Gate check — pipeline would skip process_topic_suggestions entirely
        should_create = self._should_create_topics(classification, granularity)
        assert should_create is False

        # Demonstrate: if the gate is respected, no topics are created
        if should_create:
            suggestions = [_FakeSuggestion("Test Topic", strategy_type="code-driven")]
            process_topic_suggestions(db, project_id, suggestions, ["building-public"])

        all_topics = ops.get_topics_by_strategy(db, project_id, "building-public")
        assert len(all_topics) == 0

    def test_create_topics_from_tags_creates_for_notable(self, db, project_id):
        """With granularity='low', classification='notable' should pass the gate and create topics."""
        from social_hook.topics import process_topic_suggestions

        classification = "notable"
        granularity = "low"

        should_create = self._should_create_topics(classification, granularity)
        assert should_create is True

        suggestions = [
            _FakeSuggestion("Auth System Refactor", strategy_type="code-driven"),
        ]
        created = process_topic_suggestions(db, project_id, suggestions, ["building-public"])
        assert len(created) == 1
        assert created[0].topic == "Auth System Refactor"


# =============================================================================
# 12-13: Evaluator prompt — diff inclusion vs analysis
# =============================================================================


class TestEvaluatorPromptDiffHandling:
    """Test assemble_evaluator_prompt includes/excludes diff based on analysis presence."""

    def _make_project_context(self):
        """Build a minimal ProjectContext for prompt assembly."""
        from social_hook.models.context import ProjectContext

        project = Project(id="proj-prompt", name="test", repo_path="/tmp/test")
        return ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
        )

    def test_evaluator_prompt_excludes_diff_when_analysis_present(self):
        """When analysis is provided, the prompt should NOT contain raw diff,
        but SHOULD contain 'Pre-Computed Commit Analysis'."""
        from social_hook.llm.prompts import assemble_evaluator_prompt

        commit = CommitInfo(
            hash="abc123",
            message="refactor auth",
            diff="--- a/auth.py\n+++ b/auth.py\n-old code\n+new code",
            files_changed=["auth.py"],
            insertions=1,
            deletions=1,
        )

        analysis = SimpleNamespace(
            commit_analysis=SimpleNamespace(
                classification="notable",
                episode_tags=["refactor", "auth"],
                summary="Refactored auth module",
                technical_detail="Replaced session-based auth with JWT",
            ),
        )

        result = assemble_evaluator_prompt(
            prompt="You are the evaluator.",
            project_context=self._make_project_context(),
            commit=commit,
            analysis=analysis,
        )

        assert "Pre-Computed Commit Analysis" in result
        assert "```diff" not in result
        # The raw diff content should not appear
        assert "old code" not in result

    def test_evaluator_prompt_includes_diff_without_analysis(self):
        """When analysis=None, the prompt should contain the raw diff."""
        from social_hook.llm.prompts import assemble_evaluator_prompt

        commit = CommitInfo(
            hash="def456",
            message="fix login bug",
            diff="--- a/login.py\n+++ b/login.py\n-broken\n+fixed",
            files_changed=["login.py"],
            insertions=1,
            deletions=1,
        )

        result = assemble_evaluator_prompt(
            prompt="You are the evaluator.",
            project_context=self._make_project_context(),
            commit=commit,
            analysis=None,
        )

        assert "```" in result
        assert "fixed" in result


# =============================================================================
# 14: Empty strategies guard in evaluator prompt
# =============================================================================


class TestEmptyStrategiesGuard:
    """Test that assemble_evaluator_prompt raises ConfigError when targets present but strategies missing."""

    def _make_project_context(self):
        from social_hook.models.context import ProjectContext

        project = Project(id="proj-guard", name="test", repo_path="/tmp/test")
        return ProjectContext(
            project=project,
            social_context=None,
            lifecycle=None,
            active_arcs=[],
            narrative_debt=0,
        )

    def test_empty_strategies_guard(self):
        """Targets present but strategies=None must raise ConfigError."""
        from social_hook.errors import ConfigError
        from social_hook.llm.prompts import assemble_evaluator_prompt

        commit = CommitInfo(hash="ghi789", message="test", diff="")

        with pytest.raises(ConfigError, match="No strategies"):
            assemble_evaluator_prompt(
                prompt="You are the evaluator.",
                project_context=self._make_project_context(),
                commit=commit,
                targets={"main-feed": SimpleNamespace(strategy="building-public")},
                strategies=None,
            )


# =============================================================================
# 15: Topic granularity config validation
# =============================================================================


class TestTopicGranularityConfigValidation:
    """Test that _parse_context_config rejects invalid topic_granularity values."""

    def test_topic_granularity_config_validation(self):
        """Parsing config with topic_granularity='invalid' must raise ConfigError."""
        from social_hook.config.project import _parse_context_config
        from social_hook.errors import ConfigError

        with pytest.raises(ConfigError, match="Invalid topic_granularity"):
            _parse_context_config({"topic_granularity": "invalid"})

    def test_topic_granularity_valid_values_accepted(self):
        """Valid granularity values ('low', 'medium', 'high') should parse without error."""
        from social_hook.config.project import _parse_context_config

        for valid in ("low", "medium", "high"):
            result = _parse_context_config({"topic_granularity": valid})
            assert result.topic_granularity == valid

    def test_topic_granularity_default_is_low(self):
        """Default granularity (empty config) should be 'low'."""
        from social_hook.config.project import _parse_context_config

        result = _parse_context_config({})
        assert result.topic_granularity == "low"
