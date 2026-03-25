"""Tests for target routing layer."""

from social_hook.config.targets import AccountConfig, TargetConfig
from social_hook.config.yaml import Config, ContentStrategyConfig, SchedulingConfig
from social_hook.llm.schemas import StrategyDecisionInput, TargetAction
from social_hook.routing import route_to_targets


def _make_config(
    accounts: dict[str, AccountConfig],
    targets: dict[str, TargetConfig],
    strategies: dict[str, ContentStrategyConfig] | None = None,
) -> Config:
    """Build a Config with accounts, targets, and strategies."""
    return Config(
        accounts=accounts,
        targets=targets,
        content_strategies=strategies or {},
        scheduling=SchedulingConfig(timezone="UTC"),
    )


def _make_decision(action: str = "draft", reason: str = "test") -> StrategyDecisionInput:
    return StrategyDecisionInput(action=TargetAction(action), reason=reason)


class TestRouteToTargets:
    """Tests for route_to_targets()."""

    def test_empty_targets(self, temp_db):
        """No targets configured -> empty result."""
        config = Config()
        result = route_to_targets({"default": _make_decision()}, config, temp_db)
        assert result == []

    def test_single_target_draft(self, temp_db):
        """Single target with draft decision -> one draft action."""
        config = _make_config(
            accounts={"my-x": AccountConfig(platform="x", tier="free")},
            targets={"main": TargetConfig(account="my-x", strategy="bip", primary=True)},
            strategies={"bip": ContentStrategyConfig(audience="devs")},
        )
        decisions = {"bip": _make_decision("draft", "Good commit")}
        result = route_to_targets(decisions, config, temp_db)

        assert len(result) == 1
        assert result[0].target_name == "main"
        assert result[0].action == "draft"
        assert result[0].skip_reason is None

    def test_single_target_skip(self, temp_db):
        """Single target with skip decision -> skip action."""
        config = _make_config(
            accounts={"my-x": AccountConfig(platform="x")},
            targets={"main": TargetConfig(account="my-x", strategy="bip", primary=True)},
            strategies={"bip": ContentStrategyConfig()},
        )
        decisions = {"bip": _make_decision("skip", "Not interesting")}
        result = route_to_targets(decisions, config, temp_db)

        assert len(result) == 1
        assert result[0].action == "skip"
        assert result[0].skip_reason == "Not interesting"

    def test_hold_maps_to_skip(self, temp_db):
        """Hold decision maps to skip with reason."""
        config = _make_config(
            accounts={"my-x": AccountConfig(platform="x")},
            targets={"main": TargetConfig(account="my-x", strategy="bip")},
            strategies={"bip": ContentStrategyConfig()},
        )
        decisions = {"bip": _make_decision("hold", "Save for later")}
        result = route_to_targets(decisions, config, temp_db)

        assert len(result) == 1
        assert result[0].action == "skip"
        assert "Hold" in result[0].skip_reason

    def test_primary_first_ordering(self, temp_db):
        """Primary targets come before secondary targets."""
        config = _make_config(
            accounts={
                "acc-x": AccountConfig(platform="x"),
                "acc-li": AccountConfig(platform="linkedin"),
            },
            targets={
                "secondary-li": TargetConfig(account="acc-li", strategy="bip", primary=False),
                "primary-x": TargetConfig(account="acc-x", strategy="bip", primary=True),
            },
            strategies={"bip": ContentStrategyConfig()},
        )
        decisions = {"bip": _make_decision("draft")}
        result = route_to_targets(decisions, config, temp_db)

        assert len(result) == 2
        assert result[0].target_name == "primary-x"
        assert result[1].target_name == "secondary-li"

    def test_dependent_targets_last(self, temp_db):
        """Targets with source dependency come after independent ones."""
        config = _make_config(
            accounts={"acc-x": AccountConfig(platform="x")},
            targets={
                "main": TargetConfig(account="acc-x", strategy="bip", primary=True),
                "community": TargetConfig(
                    account="acc-x",
                    strategy="bip",
                    source="main",
                    destination="community",
                    community_id="123",
                ),
            },
            strategies={"bip": ContentStrategyConfig()},
        )
        decisions = {"bip": _make_decision("draft")}
        result = route_to_targets(decisions, config, temp_db)

        assert len(result) == 2
        assert result[0].target_name == "main"
        assert result[1].target_name == "community"

    def test_source_dependency_skip(self, temp_db):
        """Dependent target skipped when source target didn't draft."""
        config = _make_config(
            accounts={"acc-x": AccountConfig(platform="x")},
            targets={
                "main": TargetConfig(account="acc-x", strategy="bip", primary=True),
                "community": TargetConfig(
                    account="acc-x",
                    strategy="bip-community",
                    source="main",
                    destination="community",
                    community_id="123",
                ),
            },
            strategies={
                "bip": ContentStrategyConfig(),
                "bip-community": ContentStrategyConfig(),
            },
        )
        # main gets skip, community depends on main
        decisions = {
            "bip": _make_decision("skip", "Not interesting"),
            "bip-community": _make_decision("draft", "Would have posted"),
        }
        result = route_to_targets(decisions, config, temp_db)

        assert len(result) == 2
        assert result[0].action == "skip"  # main
        assert result[1].action == "skip"  # community skipped due to source
        assert "Source target" in result[1].skip_reason

    def test_draft_groups_same_strategy(self, temp_db):
        """Targets sharing a strategy get the same draft_group."""
        config = _make_config(
            accounts={
                "acc-x": AccountConfig(platform="x"),
                "acc-li": AccountConfig(platform="linkedin"),
            },
            targets={
                "x-main": TargetConfig(account="acc-x", strategy="bip", primary=True),
                "li-main": TargetConfig(account="acc-li", strategy="bip", primary=False),
            },
            strategies={"bip": ContentStrategyConfig()},
        )
        decisions = {"bip": _make_decision("draft")}
        result = route_to_targets(decisions, config, temp_db)

        drafts = [r for r in result if r.action == "draft"]
        assert len(drafts) == 2
        # Same strategy -> same draft group
        assert drafts[0].draft_group == drafts[1].draft_group
        assert drafts[0].draft_group == "group-bip"

    def test_different_strategies_different_groups(self, temp_db):
        """Targets with different strategies get different draft_groups."""
        config = _make_config(
            accounts={
                "acc-x": AccountConfig(platform="x"),
                "acc-li": AccountConfig(platform="linkedin"),
            },
            targets={
                "x-main": TargetConfig(account="acc-x", strategy="bip", primary=True),
                "li-main": TargetConfig(account="acc-li", strategy="brand", primary=False),
            },
            strategies={
                "bip": ContentStrategyConfig(),
                "brand": ContentStrategyConfig(),
            },
        )
        decisions = {
            "bip": _make_decision("draft"),
            "brand": _make_decision("draft"),
        }
        result = route_to_targets(decisions, config, temp_db)

        drafts = [r for r in result if r.action == "draft"]
        assert len(drafts) == 2
        assert drafts[0].draft_group != drafts[1].draft_group

    def test_missing_strategy_decision(self, temp_db):
        """Target referencing strategy with no decision -> skip."""
        config = _make_config(
            accounts={"acc-x": AccountConfig(platform="x")},
            targets={"main": TargetConfig(account="acc-x", strategy="missing")},
            strategies={"missing": ContentStrategyConfig()},
        )
        decisions = {}  # No decisions at all
        result = route_to_targets(decisions, config, temp_db)

        assert len(result) == 1
        assert result[0].action == "skip"
        assert "No decision" in result[0].skip_reason

    def test_multi_strategy_multi_target(self, temp_db):
        """3 strategies x 5 targets routing."""
        config = _make_config(
            accounts={
                "x1": AccountConfig(platform="x", tier="free"),
                "li1": AccountConfig(platform="linkedin"),
            },
            targets={
                "x-bip": TargetConfig(account="x1", strategy="bip", primary=True),
                "x-brand": TargetConfig(account="x1", strategy="brand"),
                "li-brand": TargetConfig(account="li1", strategy="brand"),
                "x-community": TargetConfig(
                    account="x1",
                    strategy="community",
                    source="x-bip",
                    destination="community",
                    community_id="c1",
                ),
                "li-community": TargetConfig(
                    account="li1",
                    strategy="community",
                    source="li-brand",
                    destination="community",
                    community_id="c2",
                ),
            },
            strategies={
                "bip": ContentStrategyConfig(),
                "brand": ContentStrategyConfig(),
                "community": ContentStrategyConfig(),
            },
        )
        decisions = {
            "bip": _make_decision("draft"),
            "brand": _make_decision("draft"),
            "community": _make_decision("draft"),
        }
        result = route_to_targets(decisions, config, temp_db)

        assert len(result) == 5
        # Primary first
        assert result[0].target_name == "x-bip"
        assert result[0].target_config.primary is True

        # Dependent targets last
        dep_names = [r.target_name for r in result if r.target_config.source]
        assert all(result.index(r) >= 3 for r in result if r.target_name in dep_names)

        # x-community should draft (source x-bip drafted)
        x_comm = next(r for r in result if r.target_name == "x-community")
        assert x_comm.action == "draft"

        # li-community should draft (source li-brand drafted)
        li_comm = next(r for r in result if r.target_name == "li-community")
        assert li_comm.action == "draft"
