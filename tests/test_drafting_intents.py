"""Tests for src/social_hook/drafting_intents.py — intent builder functions."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

from social_hook.drafting import DraftingIntent
from social_hook.drafting_intents import (
    intent_from_decision,
    intent_from_merge,
    intent_from_platforms,
    intent_from_routed_targets,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(platforms=None):
    """Build a minimal Config-like namespace."""
    from social_hook.config.platforms import OutputPlatformConfig

    platforms = platforms or {
        "x": OutputPlatformConfig(enabled=True, priority="primary", account_tier="free"),
    }
    scheduling = SimpleNamespace(
        timezone="UTC",
        optimal_days=[],
        optimal_hours=[],
        max_per_week=10,
        thread_min_tweets=4,
    )
    return SimpleNamespace(platforms=platforms, scheduling=scheduling)


def _make_evaluation(angle="test angle", arc_id=None, media_tool=None):
    """Build a minimal LogEvaluationInput-like object."""
    strategy = SimpleNamespace(
        action="draft",
        reason="test reason",
        angle=angle,
        post_category=None,
        arc_id=arc_id,
        new_arc_theme=None,
        media_tool=media_tool,
        reference_posts=None,
        include_project_docs=False,
        topic_id=None,
        context_source=None,
        consolidate_with=None,
    )
    return SimpleNamespace(
        commit_analysis=SimpleNamespace(summary="test summary"),
        strategies={"default": strategy},
    )


def _make_decision(**overrides):
    """Build a minimal Decision-like object."""
    defaults = dict(
        id="dec-1",
        project_id="proj-1",
        commit_hash="abc123",
        decision="draft",
        reasoning="test reasoning",
        angle="test angle",
        post_category=None,
        commit_summary="summary",
        arc_id=None,
        reference_posts=None,
        media_tool=None,
        targets={},
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_routed_target(
    target_name="lead-timeline",
    action="draft",
    strategy="building-public",
    draft_group=None,
    platform="x",
    tier="free",
    primary=True,
    account_name="main-x",
):
    """Build a minimal RoutedTarget-like object."""
    strategy_decision = SimpleNamespace(
        action="draft",
        reason="looks good",
        angle="technical angle",
        post_category=None,
        arc_id=None,
        new_arc_theme=None,
        media_tool=None,
        reference_posts=None,
        include_project_docs=False,
        topic_id=None,
        context_source=None,
    )
    target_config = SimpleNamespace(
        strategy=strategy,
        primary=primary,
        account=account_name,
    )
    account_config = SimpleNamespace(
        platform=platform,
        tier=tier,
    )
    return SimpleNamespace(
        target_name=target_name,
        target_config=target_config,
        account_config=account_config,
        strategy_decision=strategy_decision,
        action=action,
        skip_reason=None,
        draft_group=draft_group,
    )


# ---------------------------------------------------------------------------
# intent_from_platforms
# ---------------------------------------------------------------------------


class TestIntentFromPlatforms:
    def test_builds_intent_with_platforms(self):
        config = _make_config()
        evaluation = _make_evaluation(angle="my angle")
        intent = intent_from_platforms(evaluation, "dec-1", config)

        assert isinstance(intent, DraftingIntent)
        assert intent.decision_id == "dec-1"
        assert intent.angle == "my angle"
        assert len(intent.platforms) == 1
        assert intent.platforms[0].platform == "x"

    def test_multiple_platforms(self):
        from social_hook.config.platforms import OutputPlatformConfig

        config = _make_config(
            platforms={
                "x": OutputPlatformConfig(enabled=True, priority="primary", account_tier="free"),
                "linkedin": OutputPlatformConfig(enabled=True, priority="secondary"),
            }
        )
        evaluation = _make_evaluation()
        intent = intent_from_platforms(evaluation, "dec-2", config)
        assert len(intent.platforms) == 2

    def test_disabled_platforms_excluded(self):
        from social_hook.config.platforms import OutputPlatformConfig

        config = _make_config(
            platforms={
                "x": OutputPlatformConfig(enabled=True, priority="primary"),
                "linkedin": OutputPlatformConfig(enabled=False),
            }
        )
        evaluation = _make_evaluation()
        intent = intent_from_platforms(evaluation, "dec-3", config)
        assert len(intent.platforms) == 1
        assert intent.platforms[0].platform == "x"


# ---------------------------------------------------------------------------
# intent_from_decision
# ---------------------------------------------------------------------------


class TestIntentFromDecision:
    def test_builds_from_decision(self):
        config = _make_config()
        conn = MagicMock(spec=sqlite3.Connection)
        decision = _make_decision(angle="fresh angle", arc_id="arc-1")
        intent = intent_from_decision(decision, config, conn)

        assert isinstance(intent, DraftingIntent)
        assert intent.angle == "fresh angle"
        assert intent.arc_id == "arc-1"
        assert intent.include_project_docs is True
        assert intent.decision_id == "dec-1"

    def test_target_platform_filter(self):
        from social_hook.config.platforms import OutputPlatformConfig

        config = _make_config(
            platforms={
                "x": OutputPlatformConfig(enabled=True, priority="primary", account_tier="free"),
                "linkedin": OutputPlatformConfig(enabled=True, priority="secondary"),
            }
        )
        conn = MagicMock(spec=sqlite3.Connection)
        decision = _make_decision()
        intent = intent_from_decision(decision, config, conn, target_platform="linkedin")
        assert len(intent.platforms) == 1
        assert intent.platforms[0].platform == "linkedin"


# ---------------------------------------------------------------------------
# intent_from_merge
# ---------------------------------------------------------------------------


class TestIntentFromMerge:
    def test_builds_merge_intent(self):
        config = _make_config()
        drafts = [
            SimpleNamespace(id="d1", content="content 1"),
            SimpleNamespace(id="d2", content="content 2"),
        ]
        decisions = [
            _make_decision(id="dec-1", angle="angle 1"),
            _make_decision(id="dec-2", angle="angle 2"),
        ]
        intent = intent_from_merge(drafts, decisions, "combine themes", config, "x")

        assert isinstance(intent, DraftingIntent)
        assert "combine themes" in intent.angle
        assert intent.include_project_docs is True
        assert len(intent.platforms) == 1
        assert intent.platforms[0].platform == "x"

    def test_merge_without_instruction(self):
        config = _make_config()
        decisions = [_make_decision(angle="a1"), _make_decision(angle="a2")]
        intent = intent_from_merge([], decisions, None, config, "x")
        assert "a1" in intent.angle
        assert "a2" in intent.angle


# ---------------------------------------------------------------------------
# intent_from_routed_targets
# ---------------------------------------------------------------------------


class TestIntentFromRoutedTargets:
    def test_single_target(self):
        config = _make_config()
        evaluation = _make_evaluation()
        conn = MagicMock(spec=sqlite3.Connection)
        conn.execute.return_value.fetchall.return_value = [("main-x",)]

        target = _make_routed_target()
        intents = intent_from_routed_targets(
            [target], "dec-1", evaluation, config, conn, project_id="test-project"
        )

        assert len(intents) == 1
        assert isinstance(intents[0], DraftingIntent)
        assert intents[0].decision_id == "dec-1"

    def test_skip_targets_excluded(self):
        config = _make_config()
        evaluation = _make_evaluation()
        conn = MagicMock(spec=sqlite3.Connection)
        conn.execute.return_value.fetchall.return_value = []

        target = _make_routed_target(action="skip")
        intents = intent_from_routed_targets(
            [target], "dec-1", evaluation, config, conn, project_id="test-project"
        )
        assert intents == []

    def test_grouped_targets(self):
        config = _make_config()
        evaluation = _make_evaluation()
        conn = MagicMock(spec=sqlite3.Connection)
        conn.execute.return_value.fetchall.return_value = [("main-x",)]

        t1 = _make_routed_target(target_name="t1", draft_group="group-a")
        t2 = _make_routed_target(target_name="t2", draft_group="group-a")
        t3 = _make_routed_target(target_name="t3")

        intents = intent_from_routed_targets(
            [t1, t2, t3], "dec-1", evaluation, config, conn, project_id="test-project"
        )
        # One intent for the group, one for the ungrouped target
        assert len(intents) == 2

    def test_preview_mode_detection(self):
        config = _make_config()
        evaluation = _make_evaluation()
        conn = MagicMock(spec=sqlite3.Connection)
        # No oauth tokens -> all targets are preview
        conn.execute.return_value.fetchall.return_value = []

        target = _make_routed_target(account_name="no-creds")
        intents = intent_from_routed_targets(
            [target], "dec-1", evaluation, config, conn, project_id="test-project"
        )
        assert len(intents) == 1
        assert intents[0].platforms[0].preview_mode is True
