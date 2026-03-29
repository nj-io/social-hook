"""Tests for Chunk 1: Evaluator schema + prompt changes (strategy-aware evaluation)."""

import pytest
from pydantic import ValidationError

from social_hook.llm.schemas import (
    CommitAnalysis,
    ContextSourceSpec,
    LogEvaluationInput,
    StrategyDecisionInput,
    TargetAction,
)


class TestStrategyDecisionInput:
    """StrategyDecisionInput schema tests."""

    def test_basic_fields(self):
        decision = StrategyDecisionInput(
            action=TargetAction.draft,
            reason="Significant feature worth posting",
            angle="New auth flow",
        )
        assert decision.action == TargetAction.draft
        assert decision.reason == "Significant feature worth posting"
        assert decision.angle == "New auth flow"

    def test_topic_id_field(self):
        decision = StrategyDecisionInput(
            action=TargetAction.draft,
            reason="Relates to auth topic",
            topic_id="topic_auth_123",
        )
        assert decision.topic_id == "topic_auth_123"

    def test_context_source_field(self):
        decision = StrategyDecisionInput(
            action=TargetAction.draft,
            reason="Needs brief and commits context",
            context_source=ContextSourceSpec(
                types=["brief", "commits"],
            ),
        )
        assert decision.context_source is not None
        assert decision.context_source.types == ["brief", "commits"]
        assert decision.context_source.topic_id is None

    def test_context_source_with_topic(self):
        decision = StrategyDecisionInput(
            action=TargetAction.draft,
            reason="Topic-driven draft",
            context_source=ContextSourceSpec(
                types=["brief", "topic"],
                topic_id="topic_perf_456",
            ),
        )
        assert decision.context_source.topic_id == "topic_perf_456"


class TestContextSourceSpec:
    """ContextSourceSpec model tests."""

    def test_roundtrip(self):
        spec = ContextSourceSpec(
            types=["brief", "commits", "topic"],
            topic_id="topic_123",
        )
        data = spec.model_dump()
        restored = ContextSourceSpec.model_validate(data)
        assert restored.types == ["brief", "commits", "topic"]
        assert restored.topic_id == "topic_123"
        assert restored.suggestion_id is None

    def test_with_suggestion_id(self):
        spec = ContextSourceSpec(
            types=["operator_suggestion"],
            suggestion_id="sug_abc",
        )
        data = spec.model_dump()
        restored = ContextSourceSpec.model_validate(data)
        assert restored.suggestion_id == "sug_abc"

    def test_rejects_unknown_fields(self):
        """extra='forbid' rejects unknown fields."""
        with pytest.raises(ValidationError):
            ContextSourceSpec(
                types=["brief"],
                unknown_field="bad",
            )

    def test_minimal(self):
        spec = ContextSourceSpec(types=["brief"])
        assert spec.types == ["brief"]
        assert spec.topic_id is None
        assert spec.suggestion_id is None


class TestLogEvaluationInputDualKey:
    """LogEvaluationInput accepts both 'targets' and 'strategies' keys."""

    def _make_data(self, key: str) -> dict:
        return {
            "commit_analysis": {
                "summary": "Added feature X",
                "episode_tags": ["feature"],
            },
            key: {
                "default": {
                    "action": "draft",
                    "reason": "Worth posting",
                    "angle": "New feature",
                },
            },
        }

    def test_strategies_key(self):
        data = self._make_data("strategies")
        result = LogEvaluationInput.model_validate(data)
        assert "default" in result.strategies
        assert result.strategies["default"].action == TargetAction.draft

    def test_targets_key_remapped(self):
        """Old 'targets' key is remapped to 'strategies' by model_validator."""
        data = self._make_data("targets")
        result = LogEvaluationInput.model_validate(data)
        assert "default" in result.strategies
        assert result.strategies["default"].action == TargetAction.draft

    def test_old_db_record_deserialization(self):
        """Old Decision records stored with 'targets' key deserialize correctly."""
        stored_json = {
            "commit_analysis": {
                "summary": "Fixed bug",
                "episode_tags": ["bugfix"],
            },
            "targets": {
                "default": {
                    "action": "skip",
                    "reason": "Minor fix",
                },
            },
        }
        result = LogEvaluationInput.model_validate(stored_json)
        assert result.strategies["default"].action == TargetAction.skip

    def test_strategies_takes_precedence(self):
        """When both keys present, strategies is used (targets ignored)."""
        data = {
            "commit_analysis": {"summary": "Test"},
            "strategies": {
                "primary": {
                    "action": "draft",
                    "reason": "From strategies",
                },
            },
            "targets": {
                "default": {
                    "action": "skip",
                    "reason": "From targets",
                },
            },
        }
        result = LogEvaluationInput.model_validate(data)
        assert "primary" in result.strategies
        assert "default" not in result.strategies


class TestCommitAnalysisFreeformTags:
    """CommitAnalysis produces freeform tags (not from fixed enum)."""

    def test_freeform_tags(self):
        analysis = CommitAnalysis(
            summary="Added OAuth 2.0 support",
            episode_tags=["security", "authentication", "breaking-change"],
        )
        assert "security" in analysis.episode_tags
        assert "authentication" in analysis.episode_tags
        assert "breaking-change" in analysis.episode_tags

    def test_empty_tags(self):
        analysis = CommitAnalysis(summary="Minor fix")
        assert analysis.episode_tags == []


class TestMultiStrategyEvaluation:
    """Evaluator produces per-strategy decisions when strategies are provided."""

    def test_multi_strategy_decisions(self):
        data = {
            "commit_analysis": {
                "summary": "Added real-time notifications",
                "episode_tags": ["feature", "ux"],
            },
            "strategies": {
                "building-public": {
                    "action": "draft",
                    "reason": "Good technical story",
                    "angle": "Real-time push notifications",
                    "post_category": "arc",
                    "topic_id": "topic_notifications",
                    "context_source": {
                        "types": ["brief", "commits"],
                    },
                },
                "brand-primary": {
                    "action": "skip",
                    "reason": "Too technical for brand audience",
                },
            },
        }
        result = LogEvaluationInput.model_validate(data)
        assert len(result.strategies) == 2
        assert result.strategies["building-public"].action == TargetAction.draft
        assert result.strategies["brand-primary"].action == TargetAction.skip
        assert result.strategies["building-public"].topic_id == "topic_notifications"

    def test_single_default_strategy(self):
        """Backward compat: single 'default' strategy when no strategies configured."""
        data = {
            "commit_analysis": {"summary": "Minor cleanup"},
            "targets": {
                "default": {
                    "action": "skip",
                    "reason": "Routine",
                },
            },
        }
        result = LogEvaluationInput.model_validate(data)
        assert "default" in result.strategies


class TestToolSchema:
    """Tool schema includes new fields."""

    def test_schema_has_topic_id(self):
        schema = LogEvaluationInput.to_tool_schema()
        target_props = schema["input_schema"]["properties"]["targets"]["additionalProperties"][
            "properties"
        ]
        assert "topic_id" in target_props

    def test_schema_has_context_source(self):
        schema = LogEvaluationInput.to_tool_schema()
        target_props = schema["input_schema"]["properties"]["targets"]["additionalProperties"][
            "properties"
        ]
        assert "context_source" in target_props
        cs_props = target_props["context_source"]["properties"]
        assert "types" in cs_props
        assert "topic_id" in cs_props
        assert "suggestion_id" in cs_props

    def test_schema_keeps_targets_key(self):
        """LLM-facing schema uses 'targets' key (not 'strategies')."""
        schema = LogEvaluationInput.to_tool_schema()
        assert "targets" in schema["input_schema"]["properties"]
        assert "strategies" not in schema["input_schema"]["properties"]


class TestAssembleStrategyPostingState:
    """Tests for assemble_strategy_posting_state helper."""

    def test_empty_with_no_strategies(self):
        from social_hook.llm.prompts import assemble_strategy_posting_state

        assert assemble_strategy_posting_state({}, []) == ""

    def test_empty_with_no_posts(self):
        from social_hook.llm.prompts import assemble_strategy_posting_state

        assert assemble_strategy_posting_state({"default": object()}, None) == ""

    def test_renders_per_strategy_posting_state(self):
        from dataclasses import dataclass
        from datetime import datetime, timezone

        from social_hook.llm.prompts import assemble_strategy_posting_state

        @dataclass
        class FakePost:
            content: str
            posted_at: datetime
            target_id: str = ""
            external_url: str = ""

        @dataclass
        class FakeTarget:
            strategy: str = ""

        posts = [
            FakePost(
                content="First post about auth",
                posted_at=datetime(2026, 3, 23, tzinfo=timezone.utc),
                target_id="t-build",
            ),
            FakePost(
                content="Brand announcement",
                posted_at=datetime(2026, 3, 22, tzinfo=timezone.utc),
                target_id="t-brand",
            ),
        ]
        targets = {
            "t-build": FakeTarget(strategy="building-public"),
            "t-brand": FakeTarget(strategy="brand-primary"),
        }
        result = assemble_strategy_posting_state(
            {"building-public": object(), "brand-primary": object()},
            recent_posts=posts,
            targets=targets,
        )
        assert "Per-Strategy Posting State" in result
        assert "building-public" in result
        assert "brand-primary" in result
        assert "First post about auth" in result

    def test_renders_pending_drafts(self):
        from dataclasses import dataclass
        from datetime import datetime, timezone

        from social_hook.llm.prompts import assemble_strategy_posting_state

        @dataclass
        class FakeDraft:
            content: str
            target_id: str = ""
            suggested_time: datetime | None = None

        @dataclass
        class FakeTarget:
            strategy: str = ""

        drafts = [
            FakeDraft(
                content="Thread on testing patterns",
                target_id="t-build",
                suggested_time=datetime(2026, 3, 25, 14, 0, tzinfo=timezone.utc),
            ),
        ]
        targets = {"t-build": FakeTarget(strategy="building-public")}
        result = assemble_strategy_posting_state(
            {"building-public": object()},
            pending_drafts=drafts,
            targets=targets,
        )
        assert "Pending drafts: 1" in result
        assert "Thread on testing" in result

    def test_renders_held_topics(self):
        from dataclasses import dataclass

        from social_hook.llm.prompts import assemble_strategy_posting_state

        @dataclass
        class FakeTopic:
            topic: str
            strategy: str
            commit_count: int = 0
            last_commit_at: str | None = None
            status: str = "holding"

        topics = [
            FakeTopic(topic="auth system", strategy="building-public", commit_count=5),
        ]
        result = assemble_strategy_posting_state(
            {"building-public": object()},
            held_topics=topics,
        )
        assert "Held topics:" in result
        assert "auth system" in result
        assert "5 commits" in result

    def test_renders_active_arcs(self):
        from dataclasses import dataclass

        from social_hook.llm.prompts import assemble_strategy_posting_state

        @dataclass
        class FakeArc:
            theme: str
            strategy: str
            post_count: int = 0

        arcs = [
            FakeArc(theme="auth rework", strategy="building-public", post_count=3),
        ]
        result = assemble_strategy_posting_state(
            {"building-public": object()},
            active_arcs=arcs,
        )
        assert "Active arcs:" in result
        assert "auth rework" in result
        assert "3 posts" in result
