"""Tests for intent_from_routed_targets() in drafting_intents.py."""

from unittest.mock import MagicMock

from social_hook.config.targets import AccountConfig, TargetConfig
from social_hook.config.yaml import Config, SchedulingConfig
from social_hook.drafting import DraftingIntent, draft
from social_hook.drafting_intents import intent_from_routed_targets
from social_hook.llm.schemas import StrategyDecisionInput, TargetAction
from social_hook.routing import RoutedTarget


def _make_routed_target(
    name: str,
    platform: str = "x",
    strategy: str = "bip",
    action: str = "draft",
    primary: bool = False,
    draft_group: str | None = None,
    tier: str | None = "free",
) -> RoutedTarget:
    """Build a RoutedTarget for testing."""
    return RoutedTarget(
        target_name=name,
        target_config=TargetConfig(
            account=f"acc-{platform}",
            strategy=strategy,
            primary=primary,
        ),
        account_config=AccountConfig(platform=platform, tier=tier),
        strategy_decision=StrategyDecisionInput(
            action=TargetAction(action) if action != "skip" else TargetAction.skip,
            reason="test",
        ),
        action=action,
        draft_group=draft_group,
    )


class TestIntentFromRoutedTargets:
    """Tests for intent_from_routed_targets()."""

    def _make_conn(self, accounts=None):
        conn = MagicMock()
        rows = [(a,) for a in (accounts or ["acc-x"])]
        conn.execute.return_value.fetchall.return_value = rows
        return conn

    def _make_evaluation(self):
        eval_mock = MagicMock()
        eval_mock.commit_analysis.summary = "test"
        return eval_mock

    def test_no_draft_actions(self, temp_db):
        """No targets with draft action -> empty result."""
        targets = [_make_routed_target("main", action="skip")]
        config = Config(scheduling=SchedulingConfig())

        result = intent_from_routed_targets(
            targets,
            "dec-1",
            self._make_evaluation(),
            config,
            self._make_conn(),
            project_id="test-project",
        )
        assert result == []

    def test_single_target_produces_intent(self, temp_db):
        """Single draft target produces one DraftingIntent."""
        targets = [_make_routed_target("main", action="draft")]
        config = Config(
            scheduling=SchedulingConfig(),
            platforms={
                "x": MagicMock(
                    enabled=True,
                    priority="primary",
                    type="builtin",
                    account_tier="free",
                    filter=None,
                    frequency=None,
                    scheduling=None,
                    description=None,
                    format=None,
                    max_length=None,
                    identity=None,
                ),
            },
        )

        intents = intent_from_routed_targets(
            targets,
            "dec-1",
            self._make_evaluation(),
            config,
            self._make_conn(),
            project_id="test-project",
        )

        assert len(intents) == 1
        assert isinstance(intents[0], DraftingIntent)
        assert len(intents[0].platforms) == 1

    def test_grouped_targets_single_intent(self, temp_db):
        """Targets in same draft_group produce one intent with multiple platform specs."""
        targets = [
            _make_routed_target("x-main", platform="x", draft_group="group-bip"),
            _make_routed_target("li-main", platform="linkedin", draft_group="group-bip"),
        ]
        config = Config(
            scheduling=SchedulingConfig(),
            platforms={
                "x": MagicMock(
                    enabled=True,
                    priority="primary",
                    type="builtin",
                    account_tier="free",
                    filter=None,
                    frequency=None,
                    scheduling=None,
                    description=None,
                    format=None,
                    max_length=None,
                    identity=None,
                ),
                "linkedin": MagicMock(
                    enabled=True,
                    priority="secondary",
                    type="builtin",
                    account_tier=None,
                    filter=None,
                    frequency=None,
                    scheduling=None,
                    description=None,
                    format=None,
                    max_length=None,
                    identity=None,
                ),
            },
        )

        intents = intent_from_routed_targets(
            targets,
            "dec-1",
            self._make_evaluation(),
            config,
            self._make_conn(["acc-x", "acc-linkedin"]),
            project_id="test-project",
        )

        # Grouped targets -> one intent
        assert len(intents) == 1
        assert len(intents[0].platforms) == 2

    def test_different_groups_separate_intents(self, temp_db):
        """Targets in different draft_groups produce separate intents."""
        targets = [
            _make_routed_target("x-main", platform="x", draft_group="group-bip"),
            _make_routed_target("li-main", platform="linkedin", draft_group="group-brand"),
        ]
        config = Config(
            scheduling=SchedulingConfig(),
            platforms={
                "x": MagicMock(
                    enabled=True,
                    priority="primary",
                    type="builtin",
                    account_tier="free",
                    filter=None,
                    frequency=None,
                    scheduling=None,
                    description=None,
                    format=None,
                    max_length=None,
                    identity=None,
                ),
                "linkedin": MagicMock(
                    enabled=True,
                    priority="secondary",
                    type="builtin",
                    account_tier=None,
                    filter=None,
                    frequency=None,
                    scheduling=None,
                    description=None,
                    format=None,
                    max_length=None,
                    identity=None,
                ),
            },
        )

        intents = intent_from_routed_targets(
            targets,
            "dec-1",
            self._make_evaluation(),
            config,
            self._make_conn(["acc-x", "acc-linkedin"]),
            project_id="test-project",
        )

        # Different groups -> separate intents
        assert len(intents) == 2

    def test_draft_function_is_callable(self, temp_db):
        """draft() function exists and is callable."""
        assert callable(draft)
