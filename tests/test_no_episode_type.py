"""Tests for Chunk 5: Episode type removal.

Verifies that EpisodeTypeSchema is gone, content filter is removed,
decisions have episode_type=None, and old data still loads.
"""

import pytest

from social_hook.models.core import Decision


class TestNoEpisodeTypeInSchema:
    """EpisodeTypeSchema is removed from schemas.py."""

    def test_episode_type_schema_not_importable(self):
        with pytest.raises(ImportError):
            from social_hook.llm.schemas import EpisodeTypeSchema  # noqa: F401

    def test_target_decision_input_not_importable(self):
        with pytest.raises(ImportError):
            from social_hook.llm.schemas import TargetDecisionInput  # noqa: F401

    def test_strategy_decision_input_has_no_episode_type(self):
        from social_hook.llm.schemas import StrategyDecisionInput, TargetAction

        d = StrategyDecisionInput(action=TargetAction.draft, reason="test")
        assert not hasattr(d, "episode_type")


class TestNoContentFilter:
    """passes_content_filter and FILTER_EPISODE_TYPES are removed."""

    def test_passes_content_filter_not_importable(self):
        with pytest.raises(ImportError):
            from social_hook.config.platforms import passes_content_filter  # noqa: F401

    def test_filter_episode_types_not_importable(self):
        with pytest.raises(ImportError):
            from social_hook.config.platforms import FILTER_EPISODE_TYPES  # noqa: F401

    def test_content_filters_still_exists(self):
        """CONTENT_FILTERS set is kept for config validation."""
        from social_hook.config.platforms import CONTENT_FILTERS

        assert "all" in CONTENT_FILTERS
        assert "notable" in CONTENT_FILTERS


class TestDecisionEpisodeTypeNone:
    """New decisions have episode_type=None."""

    def test_new_decision_episode_type_none(self):
        d = Decision(
            id="d1",
            project_id="p1",
            commit_hash="abc",
            decision="draft",
            reasoning="test",
        )
        assert d.episode_type is None

    def test_old_decision_with_episode_type_loads(self):
        """Existing decisions with episode_type values still load correctly."""
        d = Decision(
            id="d2",
            project_id="p1",
            commit_hash="def",
            decision="draft",
            reasoning="test",
            episode_type="milestone",
        )
        assert d.episode_type == "milestone"

    def test_unknown_episode_type_accepted(self):
        """No validation on episode_type values — any string accepted."""
        d = Decision(
            id="d3",
            project_id="p1",
            commit_hash="ghi",
            decision="skip",
            reasoning="test",
            episode_type="completely_custom_value",
        )
        assert d.episode_type == "completely_custom_value"


class TestLogEvaluationNoTargetsProperty:
    """LogEvaluationInput no longer has .targets property."""

    def test_no_targets_property(self):
        from social_hook.llm.schemas import (
            LogEvaluationInput,
        )

        result = LogEvaluationInput.model_validate(
            {
                "commit_analysis": {"summary": "test"},
                "targets": {
                    "default": {"action": "skip", "reason": "test"},
                },
            }
        )
        # .strategies works
        assert "default" in result.strategies
        # .targets property is gone
        assert not hasattr(result, "targets")
