"""Tests for _adapt_content_for_platform and draft_for_targets grouping."""

from unittest.mock import MagicMock, patch

from social_hook.drafting import _adapt_content_for_platform, draft_for_targets
from social_hook.models import CommitInfo
from social_hook.routing import RoutedTarget

# =============================================================================
# Helpers
# =============================================================================


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
# _adapt_content_for_platform
# =============================================================================


class TestAdaptContentForPlatform:
    """Tests for _adapt_content_for_platform."""

    def test_threaded_x_to_linkedin_unthreads(self):
        """Threaded X content is unthreaded for LinkedIn."""
        thread = "1/ First point\n\n2/ Second point\n\n3/ Third point"
        result = _adapt_content_for_platform(
            content=thread,
            was_threaded=True,
            target_platform="linkedin",
            max_length=None,
        )
        # Should be unthreaded — no numbered markers
        assert "1/" not in result
        assert "First point" in result
        assert "Second point" in result

    def test_threaded_x_to_x_passthrough(self):
        """Threaded content staying on X passes through unchanged."""
        thread = "1/ Alpha\n\n2/ Beta"
        result = _adapt_content_for_platform(
            content=thread,
            was_threaded=True,
            target_platform="x",
            max_length=None,
        )
        assert result == thread

    def test_single_post_passthrough(self):
        """Non-threaded content passes through for any platform."""
        content = "Just a normal post."
        result = _adapt_content_for_platform(
            content=content,
            was_threaded=False,
            target_platform="linkedin",
            max_length=None,
        )
        assert result == content

    def test_truncation_when_over_max_length(self):
        """Content exceeding max_length gets truncated."""
        content = "A" * 500
        result = _adapt_content_for_platform(
            content=content,
            was_threaded=False,
            target_platform="linkedin",
            max_length=200,
        )
        assert len(result) == 200

    def test_no_truncation_when_under_max_length(self):
        """Content under max_length is not truncated."""
        content = "Short post"
        result = _adapt_content_for_platform(
            content=content,
            was_threaded=False,
            target_platform="x",
            max_length=280,
        )
        assert result == content

    def test_none_max_length_no_truncation(self):
        """max_length=None means no truncation."""
        content = "A" * 10000
        result = _adapt_content_for_platform(
            content=content,
            was_threaded=False,
            target_platform="linkedin",
            max_length=None,
        )
        assert len(result) == 10000


# =============================================================================
# draft_for_targets: grouping behavior
# =============================================================================


class TestDraftForTargetsGrouping:
    """draft_for_targets groups targets by draft_group."""

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
        return RoutedTarget(
            target_name=target_name,
            target_config=target_config,
            account_config=account_config,
            strategy_decision=strategy_decision,
            action="draft",
            draft_group=draft_group,
        )

    @patch("social_hook.drafting._draft_for_resolved_platforms")
    @patch("social_hook.drafting.resolve_platform")
    def test_grouped_targets_use_shared_group(self, mock_resolve, mock_draft):
        """Targets with same draft_group are batched with shared_group=True."""
        mock_resolve.return_value = _make_rpcfg(name="x")
        mock_draft.return_value = []

        config = MagicMock()
        config.platforms = {"x": MagicMock(enabled=True)}
        config.scheduling.timezone = "UTC"

        target_actions = [
            self._make_target_action("x-feed", "building-public", draft_group="group-1"),
            self._make_target_action("x-community", "building-public", draft_group="group-1"),
        ]

        draft_for_targets(
            target_actions=target_actions,
            config=config,
            conn=MagicMock(),
            db=MagicMock(),
            project=MagicMock(id="p1"),
            decision_id="d1",
            evaluation=MagicMock(),
            context=MagicMock(recent_posts=[]),
            commit=CommitInfo(hash="abc", message="test", diff=""),
        )

        # Should call _draft_for_resolved_platforms once for the group
        assert mock_draft.call_count == 1
        # The shared_group kwarg should be True
        call_kwargs = mock_draft.call_args[1] if mock_draft.call_args[1] else {}
        # shared_group is passed as keyword
        assert call_kwargs.get("shared_group") is True

    @patch("social_hook.drafting._draft_for_resolved_platforms")
    @patch("social_hook.drafting.resolve_platform")
    def test_ungrouped_targets_drafted_individually(self, mock_resolve, mock_draft):
        """Targets without draft_group are drafted one at a time."""
        mock_resolve.return_value = _make_rpcfg(name="x")
        mock_draft.return_value = []

        config = MagicMock()
        config.platforms = {"x": MagicMock(enabled=True)}
        config.scheduling.timezone = "UTC"

        target_actions = [
            self._make_target_action("x-feed", "building-public", draft_group=None),
            self._make_target_action(
                "linkedin-feed", "brand", account_platform="linkedin", draft_group=None
            ),
        ]

        draft_for_targets(
            target_actions=target_actions,
            config=config,
            conn=MagicMock(),
            db=MagicMock(),
            project=MagicMock(id="p1"),
            decision_id="d1",
            evaluation=MagicMock(),
            context=MagicMock(recent_posts=[]),
            commit=CommitInfo(hash="abc", message="test", diff=""),
        )

        # Two ungrouped targets = two calls
        assert mock_draft.call_count == 2

    @patch("social_hook.drafting._draft_for_resolved_platforms")
    @patch("social_hook.drafting.resolve_platform")
    def test_no_draft_actions_returns_empty(self, mock_resolve, mock_draft):
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

        result = draft_for_targets(
            target_actions=[skip_action],
            config=MagicMock(),
            conn=MagicMock(),
            db=MagicMock(),
            project=MagicMock(id="p1"),
            decision_id="d1",
            evaluation=MagicMock(),
            context=MagicMock(recent_posts=[]),
            commit=CommitInfo(hash="abc", message="test", diff=""),
        )

        assert result == []
        mock_draft.assert_not_called()

    @patch("social_hook.drafting._draft_for_resolved_platforms")
    @patch("social_hook.drafting.resolve_platform")
    def test_accountless_targets_in_preview_set(self, mock_resolve, mock_draft):
        """Targets without account should appear in preview_targets set."""
        mock_resolve.return_value = _make_rpcfg(name="x")
        mock_draft.return_value = []

        config = MagicMock()
        config.platforms = {"x": MagicMock(enabled=True)}
        config.scheduling.timezone = "UTC"

        from social_hook.config.targets import AccountConfig, TargetConfig

        # Accountless target
        target_config = TargetConfig(account="", platform="x", strategy="s1")
        account_config = AccountConfig(platform="x")
        strategy_decision = MagicMock()
        strategy_decision.context_source = None
        strategy_decision.topic_id = None
        strategy_decision.arc_id = None

        ta = RoutedTarget(
            target_name="x-preview",
            target_config=target_config,
            account_config=account_config,
            strategy_decision=strategy_decision,
            action="draft",
        )

        draft_for_targets(
            target_actions=[ta],
            config=config,
            conn=MagicMock(),
            db=MagicMock(),
            project=MagicMock(id="p1"),
            decision_id="d1",
            evaluation=MagicMock(),
            context=MagicMock(recent_posts=[]),
            commit=CommitInfo(hash="abc", message="test", diff=""),
        )

        # Check preview_targets was passed to _draft_for_resolved_platforms
        call_kwargs = mock_draft.call_args[1]
        assert "x-preview" in call_kwargs["preview_targets"]
