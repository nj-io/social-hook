"""Section L: Multi-Provider scenarios."""

from e2e.constants import COMMITS


def run(harness, runner):
    """L1-L8: Multi-provider integration scenarios."""
    from social_hook.errors import ConfigError
    from social_hook.llm.factory import parse_provider_model
    from social_hook.trigger import run_trigger

    # Save original config
    config_path = harness.base / "config.yaml"
    original_config = config_path.read_text() if config_path.exists() else ""

    # L1: Claude CLI evaluator (if claude is in PATH)
    def l1():
        import shutil

        if not shutil.which("claude"):
            return "SKIP: Claude CLI not in PATH"
        harness.update_config(
            {
                "models": {
                    "evaluator": "claude-cli/sonnet",
                    "drafter": "anthropic/claude-sonnet-4-5",
                    "gatekeeper": "anthropic/claude-haiku-4-5",
                }
            }
        )
        try:
            exit_code = run_trigger(
                COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
            )
            assert exit_code == 0, f"Expected exit 0, got {exit_code}"
            return "CLI evaluator succeeded"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L1", "Claude CLI evaluator", l1, llm_call=True, isolate=True)

    # L2: Claude CLI full pipeline
    def l2():
        import shutil

        if not shutil.which("claude"):
            return "SKIP: Claude CLI not in PATH"
        harness.update_config(
            {
                "models": {
                    "evaluator": "claude-cli/sonnet",
                    "drafter": "claude-cli/sonnet",
                    "gatekeeper": "claude-cli/haiku",
                }
            }
        )
        try:
            exit_code = run_trigger(
                COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
            )
            assert exit_code == 0, f"Expected exit 0, got {exit_code}"
            return "Full CLI pipeline succeeded"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L2", "Claude CLI full pipeline", l2, llm_call=True, isolate=True)

    # L3: Mixed providers
    def l3():
        import shutil

        if not shutil.which("claude"):
            return "SKIP: Claude CLI not in PATH"
        harness.update_config(
            {
                "models": {
                    "evaluator": "anthropic/claude-haiku-4-5",
                    "drafter": "claude-cli/sonnet",
                    "gatekeeper": "anthropic/claude-haiku-4-5",
                }
            }
        )
        try:
            exit_code = run_trigger(
                COMMITS["significant"], str(harness.repo_path), verbose=runner.verbose
            )
            assert exit_code == 0, f"Expected exit 0, got {exit_code}"
            return "Mixed providers succeeded"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L3", "Mixed providers", l3, llm_call=True, isolate=True)

    # L4: Invalid provider -> graceful error
    def l4():
        harness.update_config(
            {
                "models": {
                    "evaluator": "invalid/model",
                    "drafter": "anthropic/claude-sonnet-4-5",
                    "gatekeeper": "anthropic/claude-haiku-4-5",
                }
            }
        )
        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code == 1, f"Expected exit 1, got {exit_code}"
            return f"Invalid provider -> exit {exit_code}"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L4", "Invalid provider -> graceful error", l4)

    # L5: Missing key for chosen provider
    def l5():
        # Explicitly set anthropic models so removing the key is meaningful
        harness.update_config(
            {
                "models": {
                    "evaluator": "anthropic/claude-haiku-4-5",
                    "drafter": "anthropic/claude-haiku-4-5",
                    "gatekeeper": "anthropic/claude-haiku-4-5",
                }
            }
        )
        env_path = harness.base / ".env"
        env_content = env_path.read_text()
        modified = "\n".join(
            line for line in env_content.splitlines() if not line.startswith("ANTHROPIC_API_KEY")
        )
        env_path.write_text(modified)
        try:
            exit_code = run_trigger(COMMITS["significant"], str(harness.repo_path))
            assert exit_code in (1, 3), f"Expected exit 1 or 3, got {exit_code}"
            return f"Missing key -> exit {exit_code}"
        finally:
            env_path.write_text(env_content)
            config_path.write_text(original_config)

    runner.run_scenario("L5", "Missing key -> error", l5)

    # L6: Bare model name -> config error
    def l6():
        harness.update_config(
            {
                "models": {
                    "evaluator": "claude-opus-4-5",
                    "drafter": "anthropic/claude-sonnet-4-5",
                    "gatekeeper": "anthropic/claude-haiku-4-5",
                }
            }
        )
        try:
            from social_hook.config.yaml import load_config

            try:
                load_config(config_path)
                raise AssertionError("Should have raised ConfigError")
            except ConfigError as e:
                assert "provider/model-id" in str(e).lower() or "invalid model" in str(e).lower()
                return f"Bare name rejected: {e}"
        finally:
            config_path.write_text(original_config)

    runner.run_scenario("L6", "Bare model name -> error", l6)

    # L7: Factory routing unit check
    def l7():
        assert parse_provider_model("anthropic/claude-opus-4-5") == ("anthropic", "claude-opus-4-5")
        assert parse_provider_model("claude-cli/sonnet") == ("claude-cli", "sonnet")
        assert parse_provider_model("openrouter/anthropic/claude-sonnet-4.5") == (
            "openrouter",
            "anthropic/claude-sonnet-4.5",
        )
        assert parse_provider_model("openai/gpt-4o") == ("openai", "gpt-4o")
        assert parse_provider_model("ollama/llama3.3") == ("ollama", "llama3.3")
        try:
            parse_provider_model("bare-model-name")
            raise AssertionError("Should raise ConfigError")
        except ConfigError:
            pass
        return "All parsing tests passed"

    runner.run_scenario("L7", "Factory routing unit check", l7)

    # L8: Provider auto-discovery
    def l8():
        from social_hook.setup.wizard import _discover_providers

        providers = _discover_providers({})
        provider_ids = [p["id"] for p in providers]
        # Should always have anthropic and openrouter (even if unconfigured)
        assert "anthropic" in provider_ids
        assert "openrouter" in provider_ids
        return f"Discovered {len(providers)} providers: {provider_ids}"

    runner.run_scenario("L8", "Provider auto-discovery", l8)
