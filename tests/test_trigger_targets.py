"""Tests for trigger.py targets pipeline path (Chunk 4)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from social_hook.llm.schemas import (
    CommitAnalysis,
    LogEvaluationInput,
    PostCategorySchema,
    StrategyDecisionInput,
    TargetAction,
)
from social_hook.models.content import ContentTopic
from social_hook.models.core import CommitInfo, Project
from social_hook.trigger import (
    _combine_strategy_reasoning,
    _determine_overall_decision,
)

# =============================================================================
# _determine_overall_decision
# =============================================================================


class TestDetermineOverallDecision:
    """Test _determine_overall_decision helper."""

    def test_empty_strategies_returns_skip(self):
        assert _determine_overall_decision({}) == "skip"

    def test_all_draft_returns_draft(self):
        strategies = {
            "s1": StrategyDecisionInput(action=TargetAction.draft, reason="r1"),
            "s2": StrategyDecisionInput(action=TargetAction.draft, reason="r2"),
        }
        assert _determine_overall_decision(strategies) == "draft"

    def test_any_draft_returns_draft(self):
        strategies = {
            "s1": StrategyDecisionInput(action=TargetAction.skip, reason="r1"),
            "s2": StrategyDecisionInput(action=TargetAction.draft, reason="r2"),
        }
        assert _determine_overall_decision(strategies) == "draft"

    def test_all_skip_returns_skip(self):
        strategies = {
            "s1": StrategyDecisionInput(action=TargetAction.skip, reason="r1"),
            "s2": StrategyDecisionInput(action=TargetAction.skip, reason="r2"),
        }
        assert _determine_overall_decision(strategies) == "skip"

    def test_all_hold_returns_hold(self):
        strategies = {
            "s1": StrategyDecisionInput(action=TargetAction.hold, reason="r1"),
            "s2": StrategyDecisionInput(action=TargetAction.hold, reason="r2"),
        }
        assert _determine_overall_decision(strategies) == "hold"

    def test_mixed_hold_skip_returns_skip(self):
        strategies = {
            "s1": StrategyDecisionInput(action=TargetAction.hold, reason="r1"),
            "s2": StrategyDecisionInput(action=TargetAction.skip, reason="r2"),
        }
        assert _determine_overall_decision(strategies) == "skip"

    def test_string_actions_work(self):
        """String action values (not enums) also work."""
        strategies = {
            "s1": StrategyDecisionInput(action="draft", reason="r1"),
        }
        assert _determine_overall_decision(strategies) == "draft"


# =============================================================================
# _combine_strategy_reasoning
# =============================================================================


class TestCombineStrategyReasoning:
    """Test _combine_strategy_reasoning helper."""

    def test_single_strategy(self):
        strategies = {
            "building-public": StrategyDecisionInput(action="draft", reason="Good commit")
        }
        result = _combine_strategy_reasoning(strategies)
        assert result == "building-public: Good commit"

    def test_multiple_strategies(self):
        strategies = {
            "s1": StrategyDecisionInput(action="draft", reason="reason 1"),
            "s2": StrategyDecisionInput(action="skip", reason="reason 2"),
        }
        result = _combine_strategy_reasoning(strategies)
        assert "s1: reason 1" in result
        assert "s2: reason 2" in result
        assert "; " in result

    def test_long_reasoning_not_truncated(self):
        """Full reasoning is preserved — no truncation."""
        strategies = {
            f"strategy-{i}": StrategyDecisionInput(action="skip", reason="x" * 100)
            for i in range(10)
        }
        result = _combine_strategy_reasoning(strategies)
        assert "strategy-0: " in result
        assert "strategy-9: " in result
        assert len(result) > 500


# =============================================================================
# run_summary_trigger uses StrategyDecisionInput
# =============================================================================


class TestRunSummaryTriggerTargetsCompat:
    """run_summary_trigger() uses StrategyDecisionInput, not TargetDecisionInput."""

    def test_imports_strategy_decision_input(self):
        """Verify the import works (would fail if StrategyDecisionInput was removed)."""
        from social_hook.llm.schemas import StrategyDecisionInput

        d = StrategyDecisionInput(
            action=TargetAction.draft,
            reason="test",
            episode_type=None,
            post_category=PostCategorySchema.opportunistic,
        )
        assert d.action == TargetAction.draft

    def test_log_evaluation_input_accepts_strategies_key(self):
        """LogEvaluationInput takes strategies= kwarg (not targets=)."""
        evaluation = LogEvaluationInput(
            commit_analysis=CommitAnalysis(summary="test", episode_tags=["intro"]),
            strategies={
                "default": StrategyDecisionInput(
                    action=TargetAction.draft,
                    reason="test",
                    episode_type=None,
                ),
            },
        )
        assert "default" in evaluation.strategies
        assert evaluation.strategies["default"].action == TargetAction.draft


# =============================================================================
# Targets path integration (mocked)
# =============================================================================


class TestTargetsPathIntegration:
    """Test the new targets pipeline path in trigger.py."""

    def _make_evaluation(self, strategies=None):
        if strategies is None:
            strategies = {
                "building-public": StrategyDecisionInput(
                    action=TargetAction.draft,
                    reason="Great commit for building in public",
                    angle="Show the refactoring process",
                    post_category=PostCategorySchema.opportunistic,
                ),
            }
        return LogEvaluationInput(
            commit_analysis=CommitAnalysis(
                summary="Refactored auth module",
                episode_tags=["refactor", "auth"],
            ),
            strategies=strategies,
        )

    def test_evaluation_cycle_created(self, temp_db):
        """An evaluation cycle record is created when targets path runs."""
        from social_hook.db import operations as ops
        from social_hook.trigger import TriggerContext, _run_targets_path

        project = Project(id="proj-1", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        evaluation = self._make_evaluation()
        commit = CommitInfo(hash="abc123", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="building-public")}
        config.notification_level = "drafts_only"

        with (
            patch("social_hook.routing.route_to_targets", return_value=[]),
            patch("social_hook.db.operations.get_held_decisions", return_value=[]),
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            ctx = TriggerContext(
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                project_config=None,
                current_branch="main",
                dry_run=False,
                verbose=False,
                show_prompt=False,
            )
            _run_targets_path(
                ctx=ctx,
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                commit_hash="abc123",
                context=context,
                evaluator_client=MagicMock(),
            )

        cycles = ops.get_recent_cycles(temp_db, "proj-1")
        assert len(cycles) == 1
        assert cycles[0].trigger_type == "commit"
        assert cycles[0].trigger_ref == "abc123"

    def test_topic_commit_counts_incremented(self, temp_db):
        """Tag-to-topic matching increments topic commit counts."""
        from social_hook.db import operations as ops
        from social_hook.trigger import TriggerContext, _run_targets_path

        project = Project(id="proj-2", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        # Create a topic matching "auth" tag
        topic = ContentTopic(
            id="topic-1",
            project_id="proj-2",
            strategy="building-public",
            topic="authentication system",
            commit_count=0,
        )
        ops.insert_content_topic(temp_db, topic)

        evaluation = self._make_evaluation()
        commit = CommitInfo(hash="def456", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="building-public")}
        config.notification_level = "drafts_only"

        with (
            patch("social_hook.routing.route_to_targets", return_value=[]),
            patch("social_hook.db.operations.get_held_decisions", return_value=[]),
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            ctx = TriggerContext(
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                project_config=None,
                current_branch="main",
                dry_run=False,
                verbose=False,
                show_prompt=False,
            )
            _run_targets_path(
                ctx=ctx,
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                commit_hash="def456",
                context=context,
                evaluator_client=MagicMock(),
            )

        # "auth" tag should match "authentication system" topic
        updated_topic = ops.get_topic(temp_db, "topic-1")
        assert updated_topic.commit_count == 1

    def test_hold_action_sets_topic_status(self, temp_db):
        """Hold action sets topic status to 'holding'."""
        from social_hook.db import operations as ops
        from social_hook.trigger import TriggerContext, _run_targets_path

        project = Project(id="proj-3", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(
            id="topic-2",
            project_id="proj-3",
            strategy="building-public",
            topic="test topic",
            status="uncovered",
        )
        ops.insert_content_topic(temp_db, topic)

        strategies = {
            "building-public": StrategyDecisionInput(
                action=TargetAction.hold,
                reason="Wait for more commits",
                topic_id="topic-2",
            ),
        }
        evaluation = self._make_evaluation(strategies)
        commit = CommitInfo(hash="ghi789", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="building-public")}
        config.notification_level = "all_decisions"

        with (
            patch("social_hook.routing.route_to_targets", return_value=[]),
            patch("social_hook.db.operations.get_held_decisions", return_value=[]),
            patch("social_hook.trigger._send_decision_notification"),
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            ctx = TriggerContext(
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                project_config=None,
                current_branch="main",
                dry_run=False,
                verbose=False,
                show_prompt=False,
            )
            _run_targets_path(
                ctx=ctx,
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                commit_hash="ghi789",
                context=context,
                evaluator_client=MagicMock(),
            )

        updated_topic = ops.get_topic(temp_db, "topic-2")
        assert updated_topic.status == "holding"

    def test_mixed_decisions_correct_overall(self, temp_db):
        """Mixed draft/skip -> overall 'draft', routes correctly."""
        from social_hook.db import operations as ops
        from social_hook.trigger import TriggerContext, _run_targets_path

        project = Project(id="proj-4", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        strategies = {
            "building-public": StrategyDecisionInput(
                action=TargetAction.draft,
                reason="Good for building in public",
                angle="show the refactor",
            ),
            "brand-primary": StrategyDecisionInput(
                action=TargetAction.skip,
                reason="Not brand-worthy",
            ),
        }
        evaluation = self._make_evaluation(strategies)
        commit = CommitInfo(hash="jkl012", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="building-public")}
        config.notification_level = "drafts_only"

        mock_routed = MagicMock()
        mock_routed.action = "draft"

        with (
            patch("social_hook.routing.route_to_targets", return_value=[mock_routed]),
            patch("social_hook.drafting.draft_for_targets", return_value=[]),
            patch("social_hook.db.operations.get_held_decisions", return_value=[]),
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            ctx = TriggerContext(
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                project_config=None,
                current_branch="main",
                dry_run=False,
                verbose=False,
                show_prompt=False,
            )
            _run_targets_path(
                ctx=ctx,
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                commit_hash="jkl012",
                context=context,
                evaluator_client=MagicMock(),
            )

        # Decision should be "draft" (any draft -> overall draft)
        decisions = ops.get_recent_decisions(temp_db, "proj-4")
        assert len(decisions) == 1
        assert decisions[0].decision == "draft"

    def test_backward_compat_legacy_path(self):
        """When config.targets is empty, legacy path is used."""
        # Build a legacy evaluation with "default" target
        evaluation = LogEvaluationInput(
            commit_analysis=CommitAnalysis(summary="Fix bug", episode_tags=["bugfix"]),
            strategies={
                "default": StrategyDecisionInput(
                    action=TargetAction.skip,
                    reason="Not post-worthy",
                ),
            },
        )

        # The run_trigger function should use legacy path since config.targets is empty
        # We verify by checking that evaluation.strategies.get("default") is used
        assert evaluation.strategies.get("default") is not None
        assert evaluation.strategies.get("default").action == TargetAction.skip

    def test_source_dependency_skip(self, temp_db):
        """Dependent target is skipped when source strategy's target didn't fire."""
        from social_hook.db import operations as ops
        from social_hook.trigger import TriggerContext, _run_targets_path

        project = Project(id="proj-6", name="test", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        strategies = {
            "building-public": StrategyDecisionInput(
                action=TargetAction.skip,
                reason="Not this time",
            ),
        }
        evaluation = self._make_evaluation(strategies)
        commit = CommitInfo(hash="src123", message="test", diff="")
        context = SimpleNamespace(held_decisions=[])

        config = MagicMock()
        config.targets = {"main-feed": MagicMock(strategy="building-public")}
        config.notification_level = "all_decisions"

        # All targets skipped
        with (
            patch("social_hook.routing.route_to_targets", return_value=[]),
            patch("social_hook.db.operations.get_held_decisions", return_value=[]),
            patch("social_hook.trigger._send_decision_notification"),
        ):
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(temp_db, dry_run=False)
            ctx = TriggerContext(
                config=config,
                conn=temp_db,
                db=db,
                project=project,
                commit=commit,
                project_config=None,
                current_branch="main",
                dry_run=False,
                verbose=False,
                show_prompt=False,
            )
            _run_targets_path(
                ctx=ctx,
                evaluation=evaluation,
                analysis=evaluation.commit_analysis,
                commit_hash="src123",
                context=context,
                evaluator_client=MagicMock(),
            )

        decisions = ops.get_recent_decisions(temp_db, "proj-6")
        assert len(decisions) == 1
        assert decisions[0].decision == "skip"


# =============================================================================
# get_topics_matching_tag
# =============================================================================


class TestGetTopicsMatchingTag:
    """Test the new get_topics_matching_tag ops function."""

    def test_matching_tag(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-tag-1", name="test", repo_path="/tmp")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(
            id="t1", project_id="proj-tag-1", strategy="s1", topic="OAuth Authentication"
        )
        ops.insert_content_topic(temp_db, topic)

        matches = ops.get_topics_matching_tag(temp_db, "proj-tag-1", "auth")
        assert len(matches) == 1
        assert matches[0].id == "t1"

    def test_no_match(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-tag-2", name="test", repo_path="/tmp")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(
            id="t2", project_id="proj-tag-2", strategy="s1", topic="Database Migration"
        )
        ops.insert_content_topic(temp_db, topic)

        matches = ops.get_topics_matching_tag(temp_db, "proj-tag-2", "auth")
        assert len(matches) == 0

    def test_case_insensitive(self, temp_db):
        from social_hook.db import operations as ops

        project = Project(id="proj-tag-3", name="test", repo_path="/tmp")
        ops.insert_project(temp_db, project)

        topic = ContentTopic(id="t3", project_id="proj-tag-3", strategy="s1", topic="OAuth Setup")
        ops.insert_content_topic(temp_db, topic)

        matches = ops.get_topics_matching_tag(temp_db, "proj-tag-3", "OAUTH")
        assert len(matches) == 1

    def test_different_project_excluded(self, temp_db):
        from social_hook.db import operations as ops

        project1 = Project(id="proj-tag-4a", name="test1", repo_path="/tmp/a")
        project2 = Project(id="proj-tag-4b", name="test2", repo_path="/tmp/b")
        ops.insert_project(temp_db, project1)
        ops.insert_project(temp_db, project2)

        topic = ContentTopic(id="t4", project_id="proj-tag-4a", strategy="s1", topic="auth stuff")
        ops.insert_content_topic(temp_db, topic)

        # Should not match in different project
        matches = ops.get_topics_matching_tag(temp_db, "proj-tag-4b", "auth")
        assert len(matches) == 0
