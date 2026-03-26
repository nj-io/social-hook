"""Tests for topics.py coverage: force_draft_topic paths, resolve_default_platform, is_default_target_preview."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.config.targets import (
    AccountConfig,
    TargetConfig,
    is_default_target_preview,
    resolve_default_platform,
)
from social_hook.models import ContentTopic, Project
from social_hook.topics import force_draft_topic, seed_topics_from_brief

# =============================================================================
# resolve_default_platform
# =============================================================================


class TestResolveDefaultPlatform:
    """Tests for resolve_default_platform."""

    def test_primary_target_platform(self):
        """Primary target's platform is used."""
        config = MagicMock()
        config.targets = {
            "main": TargetConfig(account="prod", strategy="s1", primary=True),
            "secondary": TargetConfig(account="prod2", strategy="s2"),
        }
        config.accounts = {
            "prod": AccountConfig(platform="linkedin"),
            "prod2": AccountConfig(platform="x"),
        }
        result = resolve_default_platform(config)
        assert result == "linkedin"

    def test_first_target_when_no_primary(self):
        """First target's platform when none is primary."""
        config = MagicMock()
        config.targets = {
            "feed": TargetConfig(account="acct1", strategy="s1"),
        }
        config.accounts = {
            "acct1": AccountConfig(platform="x"),
        }
        result = resolve_default_platform(config)
        assert result == "x"

    def test_no_targets_defaults_to_x(self):
        """No targets configured -> defaults to 'x'."""
        config = MagicMock()
        config.targets = {}
        result = resolve_default_platform(config)
        assert result == "x"

    def test_accountless_target_uses_platform_field(self):
        """Accountless target falls back to target.platform."""
        config = MagicMock()
        config.targets = {
            "preview": TargetConfig(account="", platform="linkedin", strategy="s1", primary=True),
        }
        config.accounts = {}
        result = resolve_default_platform(config)
        assert result == "linkedin"


# =============================================================================
# is_default_target_preview
# =============================================================================


class TestIsDefaultTargetPreview:
    """Tests for is_default_target_preview."""

    def test_primary_with_account_not_preview(self):
        """Primary target with account -> not preview."""
        config = MagicMock()
        config.targets = {
            "main": TargetConfig(account="prod", strategy="s1", primary=True),
        }
        assert is_default_target_preview(config) is False

    def test_primary_without_account_is_preview(self):
        """Primary target without account -> preview mode."""
        config = MagicMock()
        config.targets = {
            "main": TargetConfig(account="", platform="x", strategy="s1", primary=True),
        }
        assert is_default_target_preview(config) is True

    def test_no_targets_is_preview(self):
        """No targets configured -> preview mode."""
        config = MagicMock()
        config.targets = {}
        assert is_default_target_preview(config) is True

    def test_first_target_when_no_primary(self):
        """Falls back to first target's account status."""
        config = MagicMock()
        config.targets = {
            "feed": TargetConfig(account="prod", strategy="s1"),
        }
        assert is_default_target_preview(config) is False


# =============================================================================
# force_draft_topic: dry run path
# =============================================================================


class TestForceDraftTopicDryRun:
    """force_draft_topic in dry_run mode."""

    def test_dry_run_returns_cycle_id(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-dry", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(
            id="topic-dry",
            project_id="proj-dry",
            strategy="s1",
            topic="Test Topic",
            status="holding",
            commit_count=3,
        )
        ops.insert_content_topic(temp_db, topic)

        result = force_draft_topic(
            conn=temp_db,
            config=None,
            project_id="proj-dry",
            topic_id="topic-dry",
            strategy="s1",
            dry_run=True,
        )
        assert result is not None
        assert result.startswith("cycle_")


# =============================================================================
# force_draft_topic: no config -> early return
# =============================================================================


class TestForceDraftTopicNoConfig:
    """force_draft_topic with config=None returns cycle_id without LLM."""

    def test_none_config_returns_cycle_id(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-noconf", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(
            id="topic-noconf",
            project_id="proj-noconf",
            strategy="s1",
            topic="Feature X",
            status="holding",
            commit_count=2,
        )
        ops.insert_content_topic(temp_db, topic)

        result = force_draft_topic(
            conn=temp_db,
            config=None,
            project_id="proj-noconf",
            topic_id="topic-noconf",
            strategy="s1",
            dry_run=False,
        )
        assert result is not None
        # Cycle should be inserted
        cycles = ops.get_recent_cycles(temp_db, "proj-noconf")
        assert len(cycles) == 1


# =============================================================================
# force_draft_topic: wrong status
# =============================================================================


class TestForceDraftTopicWrongStatus:
    """force_draft_topic rejects topics not in 'holding' or 'uncovered' status."""

    def test_uncovered_topic_succeeds(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-wrong", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(
            id="topic-wrong",
            project_id="proj-wrong",
            strategy="s1",
            topic="Test",
            status="uncovered",
        )
        ops.insert_content_topic(temp_db, topic)

        result = force_draft_topic(
            conn=temp_db,
            config=None,
            project_id="proj-wrong",
            topic_id="topic-wrong",
            strategy="s1",
        )
        assert result is not None  # uncovered topics can be force-drafted

    def test_covered_topic_returns_none(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-cov", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(
            id="topic-cov",
            project_id="proj-cov",
            strategy="s1",
            topic="Test",
            status="covered",
        )
        ops.insert_content_topic(temp_db, topic)

        result = force_draft_topic(
            conn=temp_db,
            config=None,
            project_id="proj-cov",
            topic_id="topic-cov",
            strategy="s1",
        )
        assert result is None


# =============================================================================
# force_draft_topic: topic not found
# =============================================================================


class TestForceDraftTopicNotFound:
    """force_draft_topic raises ConfigError for missing topic."""

    def test_missing_topic_raises(self, temp_db):
        from social_hook.errors import ConfigError

        with pytest.raises(ConfigError, match="Topic not found"):
            force_draft_topic(
                conn=temp_db,
                config=None,
                project_id="proj-x",
                topic_id="nonexistent",
                strategy="s1",
            )


# =============================================================================
# force_draft_topic: targets path (config with targets)
# =============================================================================


class TestForceDraftTopicTargetsPath:
    """force_draft_topic routes through targets when config.targets exists."""

    def test_targets_path_calls_route_and_draft(self, temp_db):
        from social_hook.db import operations as ops
        from social_hook.llm.schemas import (
            CommitAnalysis,
            LogEvaluationInput,
            StrategyDecisionInput,
            TargetAction,
        )

        project = Project(id="proj-target", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(
            id="topic-target",
            project_id="proj-target",
            strategy="building-public",
            topic="Feature X",
            status="holding",
            commit_count=3,
        )
        ops.insert_content_topic(temp_db, topic)

        evaluation = LogEvaluationInput(
            commit_analysis=CommitAnalysis(summary="topic draft", episode_tags=[]),
            strategies={
                "building-public": StrategyDecisionInput(
                    action=TargetAction.draft,
                    reason="ready",
                ),
            },
        )
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate.return_value = evaluation

        config = MagicMock()
        config.models.evaluator = "anthropic/claude-sonnet-4-5"
        config.targets = {"main-feed": MagicMock(strategy="building-public")}
        config.content_strategies = {"building-public": MagicMock()}

        mock_routed = MagicMock()
        mock_routed.action = "draft"

        with (
            patch("social_hook.db.operations.get_project", return_value=project),
            patch("social_hook.config.project.load_project_config", return_value=None),
            patch("social_hook.llm.prompts.assemble_evaluator_context", return_value=MagicMock()),
            patch("social_hook.llm.factory.create_client", return_value=MagicMock()),
            patch("social_hook.llm.evaluator.Evaluator", return_value=mock_evaluator),
            patch("social_hook.routing.route_to_targets", return_value=[mock_routed]) as mock_route,
            patch("social_hook.drafting.draft_for_targets") as mock_draft,
        ):
            result = force_draft_topic(
                conn=temp_db,
                config=config,
                project_id="proj-target",
                topic_id="topic-target",
                strategy="building-public",
            )

        assert result is not None
        mock_route.assert_called_once()
        mock_draft.assert_called_once()


# =============================================================================
# seed_topics_from_brief: no strategies
# =============================================================================


class TestSeedTopicsFromBrief:
    """seed_topics_from_brief edge cases."""

    def test_empty_strategies_returns_empty(self, temp_db):
        result = seed_topics_from_brief(temp_db, "proj-1", "## Key Capabilities\n- Feature", [])
        assert result == []

    def test_no_capabilities_section_returns_empty(self, temp_db):
        result = seed_topics_from_brief(
            temp_db, "proj-1", "# Brief\n\nNo caps section here.", ["s1"]
        )
        assert result == []
