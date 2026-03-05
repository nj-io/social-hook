"""Tests for LLM factory and model string parser."""

from unittest.mock import MagicMock

import pytest

from social_hook.errors import ConfigError
from social_hook.llm.factory import create_client, parse_provider_model


class TestParseProviderModel:
    def test_parse_bare_name_raises(self):
        """Bare model names are not allowed."""
        with pytest.raises(ConfigError, match="must use provider/model-id format"):
            parse_provider_model("claude-opus-4-5")

    def test_parse_anthropic(self):
        assert parse_provider_model("anthropic/claude-opus-4-5") == ("anthropic", "claude-opus-4-5")

    def test_parse_claude_cli(self):
        assert parse_provider_model("claude-cli/sonnet") == ("claude-cli", "sonnet")

    def test_parse_openrouter(self):
        """OpenRouter models have nested slashes."""
        assert parse_provider_model("openrouter/anthropic/claude-sonnet-4.5") == (
            "openrouter",
            "anthropic/claude-sonnet-4.5",
        )

    def test_parse_openai(self):
        assert parse_provider_model("openai/gpt-4o") == ("openai", "gpt-4o")

    def test_parse_ollama(self):
        assert parse_provider_model("ollama/llama3.3") == ("ollama", "llama3.3")

    def test_parse_unknown_provider_raises(self):
        with pytest.raises(ConfigError, match="must use provider/model-id format"):
            parse_provider_model("unknown/some-model")

    def test_parse_empty_string_raises(self):
        with pytest.raises(ConfigError):
            parse_provider_model("")


class TestCreateClient:
    def _mock_config(self, **env_vars):
        config = MagicMock()
        config.env = env_vars
        return config

    def test_create_anthropic_client(self):
        config = self._mock_config(ANTHROPIC_API_KEY="sk-ant-test")
        client = create_client("anthropic/claude-opus-4-5", config)
        from social_hook.llm.client import ClaudeClient

        assert isinstance(client, ClaudeClient)
        assert client.model == "claude-opus-4-5"

    def test_create_cli_client(self):
        config = self._mock_config()
        client = create_client("claude-cli/sonnet", config)
        from social_hook.llm.claude_cli import ClaudeCliClient

        assert isinstance(client, ClaudeCliClient)
        assert client.model == "sonnet"

    def test_create_anthropic_missing_key(self):
        config = self._mock_config()
        with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY required"):
            create_client("anthropic/claude-opus-4-5", config)

    def test_create_openai_missing_key(self):
        config = self._mock_config()
        with pytest.raises(ConfigError, match="OPENAI_API_KEY required"):
            create_client("openai/gpt-4o", config)

    def test_create_openrouter_missing_key(self):
        config = self._mock_config()
        with pytest.raises(ConfigError, match="OPENROUTER_API_KEY required"):
            create_client("openrouter/anthropic/claude-sonnet-4.5", config)

    def test_create_ollama_no_key_needed(self):
        """Ollama doesn't require an API key."""
        pytest.importorskip("openai")
        config = self._mock_config()
        client = create_client("ollama/llama3.3", config)
        from social_hook.llm.openai_compat import OpenAICompatClient

        assert isinstance(client, OpenAICompatClient)
        assert client.model == "llama3.3"

    def test_create_openai_client(self):
        pytest.importorskip("openai")
        config = self._mock_config(OPENAI_API_KEY="sk-test")
        client = create_client("openai/gpt-4o", config)
        from social_hook.llm.openai_compat import OpenAICompatClient

        assert isinstance(client, OpenAICompatClient)

    def test_create_openrouter_client(self):
        pytest.importorskip("openai")
        config = self._mock_config(OPENROUTER_API_KEY="sk-or-test")
        client = create_client("openrouter/anthropic/claude-sonnet-4.5", config)
        from social_hook.llm.openai_compat import OpenAICompatClient

        assert isinstance(client, OpenAICompatClient)
        assert client.model == "anthropic/claude-sonnet-4.5"
