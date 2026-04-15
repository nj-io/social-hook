"""Tests for intent_from_routed_targets grouping."""

from unittest.mock import MagicMock

from social_hook.drafting_intents import intent_from_routed_targets
from social_hook.routing import RoutedTarget


def _make_rpcfg(max_length=None, account_tier=None, name="x", **kwargs):
    rpcfg = MagicMock()
    rpcfg.max_length = max_length
    rpcfg.account_tier = account_tier
    rpcfg.name = name
    rpcfg.max_posts_per_day = 3
    rpcfg.min_gap_minutes = 30
    rpcfg.optimal_days = None
    rpcfg.optimal_hours = None
    for k, v in kwargs.items():
        setattr(rpcfg, k, v)
    return rpcfg


# =============================================================================
# intent_from_routed_targets: grouping behavior
# =============================================================================


class TestIntentFromRoutedTargetsGrouping:
    """intent_from_routed_targets groups targets by draft_group."""

    def _make_target_action(
        self, target_name, strategy, account_platform="x", draft_group=None, account_name="prod"
    ):
        """Build a RoutedTarget."""
        from social_hook.config.targets import AccountConfig, TargetConfig

        target_config = TargetConfig(
            account=account_name,
            strategy=strategy,
            primary=True,
        )
        account_config = AccountConfig(platform=account_platform, tier="free")
        strategy_decision = MagicMock()
        strategy_decision.context_source = None
        strategy_decision.topic_id = None
        strategy_decision.arc_id = None
        strategy_decision.angle = "test angle"
        strategy_decision.reason = "test reason"
        strategy_decision.post_category = "standalone"
        strategy_decision.media_tool = None
        strategy_decision.include_project_docs = False
        strategy_decision.reference_posts = None
        return RoutedTarget(
            target_name=target_name,
            target_config=target_config,
            account_config=account_config,
            strategy_decision=strategy_decision,
            action="draft",
            draft_group=draft_group,
        )

    def _make_evaluation(self):
        eval_mock = MagicMock()
        eval_mock.commit_analysis.summary = "test"
        return eval_mock

    def test_grouped_targets_produce_single_intent(self):
        """Targets with same draft_group produce one intent with multiple platform specs."""
        from social_hook.config.yaml import SchedulingConfig

        config = MagicMock()
        config.platforms = {}  # Empty so _resolve_target_platform builds from account config
        config.scheduling = SchedulingConfig()

        target_actions = [
            self._make_target_action("x-feed", "building-public", draft_group="group-1"),
            self._make_target_action("x-community", "building-public", draft_group="group-1"),
        ]

        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [("prod",)]

        intents = intent_from_routed_targets(
            target_actions,
            "d1",
            self._make_evaluation(),
            config,
            conn,
            project_id="test-project",
        )

        # Should produce one intent for the group
        assert len(intents) == 1
        # With two platform specs
        assert len(intents[0].platforms) == 2

    def test_ungrouped_targets_produce_separate_intents(self):
        """Targets without draft_group produce one intent each."""
        from social_hook.config.yaml import SchedulingConfig

        config = MagicMock()
        config.platforms = {}
        config.scheduling = SchedulingConfig()

        target_actions = [
            self._make_target_action("x-feed", "building-public", draft_group=None),
            self._make_target_action(
                "linkedin-feed", "brand", account_platform="linkedin", draft_group=None
            ),
        ]

        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [("prod",)]

        intents = intent_from_routed_targets(
            target_actions,
            "d1",
            self._make_evaluation(),
            config,
            conn,
            project_id="test-project",
        )

        # Two ungrouped targets = two intents
        assert len(intents) == 2

    def test_no_draft_actions_returns_empty(self):
        """If all target_actions are non-draft, returns empty list."""
        from social_hook.config.targets import AccountConfig, TargetConfig

        target_config = TargetConfig(account="prod", strategy="s1")
        account_config = AccountConfig(platform="x")
        strategy_decision = MagicMock()
        strategy_decision.context_source = None
        strategy_decision.topic_id = None
        strategy_decision.arc_id = None

        skip_action = RoutedTarget(
            target_name="x-feed",
            target_config=target_config,
            account_config=account_config,
            strategy_decision=strategy_decision,
            action="skip",
            skip_reason="not relevant",
        )

        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []

        intents = intent_from_routed_targets(
            [skip_action],
            "d1",
            MagicMock(commit_analysis=MagicMock(summary="test")),
            MagicMock(),
            conn,
            project_id="test-project",
        )

        assert intents == []

    def test_accountless_targets_get_preview_mode(self):
        """Targets without account should have preview_mode=True."""
        from social_hook.config.yaml import SchedulingConfig

        config = MagicMock()
        config.platforms = {}
        config.scheduling = SchedulingConfig()

        target_actions = [
            self._make_target_action(
                "x-feed", "building-public", draft_group=None, account_name="unknown_acct"
            ),
        ]

        conn = MagicMock()
        # Return empty oauth_tokens — "unknown_acct" won't be in the set
        conn.execute.return_value.fetchall.return_value = []

        intents = intent_from_routed_targets(
            target_actions,
            "d1",
            self._make_evaluation(),
            config,
            conn,
            project_id="test-project",
        )

        assert len(intents) == 1
        assert intents[0].platforms[0].preview_mode is True
