"""Tests for draft_for_targets() in drafting.py."""

from unittest.mock import MagicMock, patch

from social_hook.config.targets import AccountConfig, TargetConfig
from social_hook.config.yaml import Config, SchedulingConfig
from social_hook.drafting import draft_for_targets
from social_hook.llm.schemas import StrategyDecisionInput, TargetAction
from social_hook.models.core import Project
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


class TestDraftForTargets:
    """Tests for draft_for_targets()."""

    def test_no_draft_actions(self, temp_db):
        """No targets with draft action -> empty result."""
        targets = [_make_routed_target("main", action="skip")]
        config = Config(scheduling=SchedulingConfig())
        project = MagicMock(spec=Project)
        project.id = "proj-1"

        result = draft_for_targets(
            target_actions=targets,
            config=config,
            conn=temp_db,
            db=MagicMock(),
            project=project,
            decision_id="dec-1",
            evaluation=MagicMock(),
            context=MagicMock(),
            commit=MagicMock(),
        )
        assert result == []

    @patch("social_hook.drafting._draft_for_resolved_platforms")
    def test_single_target_calls_drafting(self, mock_draft, temp_db):
        """Single draft target calls _draft_for_resolved_platforms."""
        mock_draft.return_value = []

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
        project = MagicMock(spec=Project)
        project.id = "proj-1"

        draft_for_targets(
            target_actions=targets,
            config=config,
            conn=temp_db,
            db=MagicMock(),
            project=project,
            decision_id="dec-1",
            evaluation=MagicMock(),
            context=MagicMock(),
            commit=MagicMock(),
        )

        assert mock_draft.called

    @patch("social_hook.drafting._draft_for_resolved_platforms")
    def test_grouped_targets_single_call(self, mock_draft, temp_db):
        """Targets in same draft_group produce one _draft_for_resolved_platforms call."""
        mock_draft.return_value = []

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
        project = MagicMock(spec=Project)
        project.id = "proj-1"

        draft_for_targets(
            target_actions=targets,
            config=config,
            conn=temp_db,
            db=MagicMock(),
            project=project,
            decision_id="dec-1",
            evaluation=MagicMock(),
            context=MagicMock(),
            commit=MagicMock(),
        )

        # Grouped targets -> one call with both targets
        assert mock_draft.call_count == 1
        platforms_arg = mock_draft.call_args[0][0]
        assert len(platforms_arg) == 2
        assert "x-main" in platforms_arg
        assert "li-main" in platforms_arg

    @patch("social_hook.drafting._draft_for_resolved_platforms")
    def test_different_groups_separate_calls(self, mock_draft, temp_db):
        """Targets in different draft_groups produce separate calls."""
        mock_draft.return_value = []

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
        project = MagicMock(spec=Project)
        project.id = "proj-1"

        draft_for_targets(
            target_actions=targets,
            config=config,
            conn=temp_db,
            db=MagicMock(),
            project=project,
            decision_id="dec-1",
            evaluation=MagicMock(),
            context=MagicMock(),
            commit=MagicMock(),
        )

        # Different groups -> separate calls
        assert mock_draft.call_count == 2

    @patch("social_hook.drafting._draft_for_resolved_platforms")
    def test_backward_compat_draft_for_platforms(self, mock_draft, temp_db):
        """draft_for_platforms() still works when called directly."""
        # This test just verifies the old function still exists and is callable
        from social_hook.drafting import draft_for_platforms

        assert callable(draft_for_platforms)
