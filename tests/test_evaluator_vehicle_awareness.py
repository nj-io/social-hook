"""Tests for Phase 5: Evaluator Vehicle Awareness.

Covers:
- StrategyDecisionInput.vehicle field validation
- LogEvaluationInput.to_tool_schema() vehicle in strategy properties
- build_platform_summaries() with tier, char limits, and vehicles
"""

from social_hook.llm.schemas import LogEvaluationInput, StrategyDecisionInput


class TestStrategyDecisionInputVehicle:
    """StrategyDecisionInput accepts and validates the vehicle field."""

    def test_vehicle_none_by_default(self):
        sd = StrategyDecisionInput(action="draft", reason="test")
        assert sd.vehicle is None

    def test_vehicle_single(self):
        sd = StrategyDecisionInput(action="draft", reason="test", vehicle="single")
        assert sd.vehicle == "single"

    def test_vehicle_thread(self):
        sd = StrategyDecisionInput(action="draft", reason="test", vehicle="thread")
        assert sd.vehicle == "thread"

    def test_vehicle_article(self):
        sd = StrategyDecisionInput(action="draft", reason="test", vehicle="article")
        assert sd.vehicle == "article"

    def test_vehicle_arbitrary_string_accepted(self):
        """vehicle is str | None, not an enum — arbitrary strings pass Pydantic."""
        sd = StrategyDecisionInput(action="draft", reason="test", vehicle="newsletter")
        assert sd.vehicle == "newsletter"

    def test_full_evaluation_with_vehicle(self):
        """Vehicle flows through LogEvaluationInput validation."""
        data = {
            "commit_analysis": {"summary": "Added new feature"},
            "targets": {
                "building-public": {
                    "action": "draft",
                    "reason": "Interesting feature",
                    "vehicle": "thread",
                    "angle": "Multi-step walkthrough",
                }
            },
        }
        result = LogEvaluationInput.validate(data)
        assert result.strategies["building-public"].vehicle == "thread"


class TestLogEvaluationToolSchemaVehicle:
    """LogEvaluationInput.to_tool_schema() includes vehicle in strategy properties."""

    def test_vehicle_in_target_properties(self):
        schema = LogEvaluationInput.to_tool_schema()
        target_props = schema["input_schema"]["properties"]["targets"]["additionalProperties"][
            "properties"
        ]
        assert "vehicle" in target_props

    def test_vehicle_schema_has_enum(self):
        schema = LogEvaluationInput.to_tool_schema()
        target_props = schema["input_schema"]["properties"]["targets"]["additionalProperties"][
            "properties"
        ]
        vehicle_schema = target_props["vehicle"]
        assert vehicle_schema["type"] == "string"
        assert set(vehicle_schema["enum"]) == {"single", "thread", "article"}

    def test_vehicle_schema_has_description(self):
        schema = LogEvaluationInput.to_tool_schema()
        target_props = schema["input_schema"]["properties"]["targets"]["additionalProperties"][
            "properties"
        ]
        vehicle_schema = target_props["vehicle"]
        assert "description" in vehicle_schema
        assert len(vehicle_schema["description"]) > 0


class TestBuildPlatformSummaries:
    """build_platform_summaries() includes tier, char limits, and vehicles."""

    def _make_config(self, platforms: dict):
        """Build a minimal Config-like object with platforms dict."""
        from types import SimpleNamespace

        from social_hook.config.platforms import OutputPlatformConfig

        platform_configs = {}
        for pname, overrides in platforms.items():
            kwargs = {"enabled": True, "priority": "primary"}
            kwargs.update(overrides)
            platform_configs[pname] = OutputPlatformConfig(**kwargs)

        return SimpleNamespace(platforms=platform_configs)

    def test_includes_tier_and_char_limit(self):
        from social_hook.trigger_context import build_platform_summaries

        config = self._make_config({"x": {"account_tier": "basic"}})
        summaries = build_platform_summaries(config)
        assert len(summaries) == 1
        assert "basic tier" in summaries[0]
        assert "25K chars" in summaries[0]

    def test_free_tier_default(self):
        from social_hook.trigger_context import build_platform_summaries

        config = self._make_config({"x": {}})
        summaries = build_platform_summaries(config)
        assert "free tier" in summaries[0]
        assert "280 chars" in summaries[0]

    def test_includes_vehicle_descriptions(self):
        from social_hook.trigger_context import build_platform_summaries

        config = self._make_config({"x": {"account_tier": "basic"}})
        summaries = build_platform_summaries(config)
        # x supports single, thread, article
        assert "vehicles:" in summaries[0]
        assert "Self-contained post" in summaries[0]
        assert "Multi-part narrative" in summaries[0]

    def test_linkedin_vehicles(self):
        from social_hook.trigger_context import build_platform_summaries

        config = self._make_config({"linkedin": {}})
        summaries = build_platform_summaries(config)
        assert "Self-contained post" in summaries[0]
        # linkedin doesn't support thread
        assert "Multi-part narrative" not in summaries[0]

    def test_custom_platform_no_vehicles(self):
        from social_hook.trigger_context import build_platform_summaries

        config = self._make_config(
            {
                "blog": {"type": "custom", "description": "My tech blog"},
            }
        )
        summaries = build_platform_summaries(config)
        assert "My tech blog" in summaries[0]
        # Unknown platform has no PLATFORM_VEHICLE_SUPPORT entry
        assert "vehicles:" not in summaries[0]

    def test_disabled_platform_excluded(self):
        from social_hook.trigger_context import build_platform_summaries

        config = self._make_config(
            {
                "x": {"enabled": False},
                "linkedin": {},
            }
        )
        summaries = build_platform_summaries(config)
        assert len(summaries) == 1
        assert summaries[0].startswith("linkedin")

    def test_multiple_platforms(self):
        from social_hook.trigger_context import build_platform_summaries

        config = self._make_config(
            {
                "x": {"account_tier": "premium", "priority": "primary"},
                "linkedin": {"priority": "secondary"},
            }
        )
        summaries = build_platform_summaries(config)
        assert len(summaries) == 2
        x_summary = [s for s in summaries if s.startswith("x")][0]
        li_summary = [s for s in summaries if s.startswith("linkedin")][0]
        assert "premium tier" in x_summary
        assert "primary" in x_summary
        assert "secondary" in li_summary
