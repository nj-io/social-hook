"""Tests for LLM model catalog data integrity."""

from unittest.mock import MagicMock, patch

from social_hook.llm.catalog import (
    ModelInfo,
    ProviderCompat,
    ProviderInfo,
    discover_ollama_models,
    format_model_choice,
    get_all_providers,
    get_models_for_provider,
    get_provider_compat,
    get_provider_info,
)

# =============================================================================
# Provider / model consistency
# =============================================================================

STATIC_PROVIDERS = ["anthropic", "claude-cli", "openai", "openrouter"]


class TestProviderModelConsistency:
    """All static providers have models and IDs are consistent."""

    def test_all_static_providers_have_models(self):
        for pid in STATIC_PROVIDERS:
            models = get_models_for_provider(pid)
            assert len(models) > 0, f"Provider {pid} has no models"

    def test_ollama_has_no_static_models(self):
        assert get_models_for_provider("ollama") == []

    def test_model_full_ids_match_format(self):
        for pid in STATIC_PROVIDERS:
            for m in get_models_for_provider(pid):
                assert m.full_id == f"{m.provider}/{m.id}", (
                    f"Model {m.id}: full_id {m.full_id!r} != {m.provider}/{m.id}"
                )

    def test_model_provider_matches_query(self):
        for pid in STATIC_PROVIDERS:
            for m in get_models_for_provider(pid):
                assert m.provider == pid

    def test_unknown_provider_returns_empty(self):
        assert get_models_for_provider("nonexistent") == []


# =============================================================================
# get_provider_info
# =============================================================================


class TestGetProviderInfo:
    """get_provider_info returns correct data."""

    def test_anthropic(self):
        info = get_provider_info("anthropic")
        assert isinstance(info, ProviderInfo)
        assert info.id == "anthropic"
        assert info.env_key == "ANTHROPIC_API_KEY"
        assert info.api_format == "anthropic"

    def test_openai(self):
        info = get_provider_info("openai")
        assert info is not None
        assert info.id == "openai"
        assert info.env_key == "OPENAI_API_KEY"
        assert info.api_format == "openai"

    def test_openrouter(self):
        info = get_provider_info("openrouter")
        assert info is not None
        assert info.env_key == "OPENROUTER_API_KEY"
        assert info.api_format == "openai"

    def test_claude_cli(self):
        info = get_provider_info("claude-cli")
        assert info is not None
        assert info.api_format == "cli"
        assert info.env_key == ""

    def test_ollama(self):
        info = get_provider_info("ollama")
        assert info is not None
        assert info.api_format == "ollama"

    def test_unknown_returns_none(self):
        assert get_provider_info("nonexistent") is None


# =============================================================================
# get_provider_compat
# =============================================================================


class TestGetProviderCompat:
    """get_provider_compat returns correct flags."""

    def test_anthropic_compat(self):
        compat = get_provider_compat("anthropic")
        assert isinstance(compat, ProviderCompat)
        assert compat.system_in_messages is False
        assert compat.tool_schema_format == "anthropic"
        assert compat.supports_cache is True

    def test_openai_compat(self):
        compat = get_provider_compat("openai")
        assert compat is not None
        assert compat.system_in_messages is True
        assert compat.tool_schema_format == "openai"
        assert compat.max_tokens_field == "max_completion_tokens"

    def test_openrouter_compat(self):
        compat = get_provider_compat("openrouter")
        assert compat is not None
        assert compat.system_in_messages is True
        assert compat.tool_schema_format == "openai"

    def test_ollama_compat(self):
        compat = get_provider_compat("ollama")
        assert compat is not None
        assert compat.system_in_messages is True
        assert compat.tool_schema_format == "openai"

    def test_unknown_returns_none(self):
        assert get_provider_compat("nonexistent") is None


# =============================================================================
# get_all_providers
# =============================================================================


class TestGetAllProviders:
    """get_all_providers returns all known providers."""

    def test_returns_all_five(self):
        providers = get_all_providers()
        ids = {p.id for p in providers}
        assert ids == {"anthropic", "claude-cli", "openai", "openrouter", "ollama"}

    def test_returns_provider_info_instances(self):
        for p in get_all_providers():
            assert isinstance(p, ProviderInfo)


# =============================================================================
# format_model_choice
# =============================================================================


class TestFormatModelChoice:
    """format_model_choice produces readable output."""

    def test_paid_model_shows_cost(self):
        model = get_models_for_provider("anthropic")[0]
        result = format_model_choice(model)
        assert model.name in result
        assert "$" in result

    def test_cli_model_shows_subscription(self):
        model = get_models_for_provider("claude-cli")[0]
        result = format_model_choice(model)
        assert "subscription" in result

    def test_local_model_shows_free(self):
        local = ModelInfo(
            id="test",
            provider="ollama",
            full_id="ollama/test",
            name="Test Model",
            description="A test",
            tier="local",
            context_window=4096,
            max_output_tokens=2048,
        )
        result = format_model_choice(local)
        assert "free/local" in result

    def test_includes_description(self):
        model = get_models_for_provider("openai")[0]
        result = format_model_choice(model)
        assert model.description in result


# =============================================================================
# discover_ollama_models
# =============================================================================


class TestDiscoverOllamaModels:
    """discover_ollama_models handles mock responses correctly."""

    @patch("social_hook.llm.catalog.requests.get")
    def test_discovers_models(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "models": [
                {
                    "name": "llama3:latest",
                    "size": 4_000_000_000,
                    "details": {
                        "parameter_size": "8B",
                        "context_length": 8192,
                    },
                },
                {
                    "name": "codellama:7b",
                    "size": 3_800_000_000,
                    "details": {
                        "parameter_size": "7B",
                        "context_length": 4096,
                    },
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        models = discover_ollama_models("http://localhost:11434")
        assert len(models) == 2

        # First model: :latest suffix stripped
        assert models[0].id == "llama3"
        assert models[0].full_id == "ollama/llama3"
        assert models[0].provider == "ollama"
        assert models[0].tier == "local"
        assert models[0].context_window == 8192
        assert "8B" in models[0].description

        # Second model: tag kept as-is
        assert models[1].id == "codellama:7b"
        assert models[1].full_id == "ollama/codellama:7b"

    @patch("social_hook.llm.catalog.requests.get")
    def test_handles_connection_error(self, mock_get):
        import requests as req

        mock_get.side_effect = req.ConnectionError("refused")
        models = discover_ollama_models()
        assert models == []

    @patch("social_hook.llm.catalog.requests.get")
    def test_handles_empty_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        models = discover_ollama_models()
        assert models == []

    @patch("social_hook.llm.catalog.requests.get")
    def test_skips_models_without_name(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "models": [
                {"name": "", "size": 100},
                {"name": "valid-model", "size": 200, "details": {}},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        models = discover_ollama_models()
        assert len(models) == 1
        assert models[0].id == "valid-model"


# =============================================================================
# Provider ID consistency
# =============================================================================


class TestProviderIdConsistency:
    """Provider IDs are consistent between models and provider info."""

    def test_all_model_providers_have_info(self):
        all_providers = get_all_providers()
        provider_ids = {p.id for p in all_providers}
        for pid in STATIC_PROVIDERS:
            for m in get_models_for_provider(pid):
                assert m.provider in provider_ids, (
                    f"Model {m.id} references provider {m.provider!r} which has no ProviderInfo"
                )

    def test_all_model_providers_have_compat(self):
        for pid in STATIC_PROVIDERS:
            for m in get_models_for_provider(pid):
                compat = get_provider_compat(m.provider)
                assert compat is not None, (
                    f"Model {m.id} references provider {m.provider!r} which has no ProviderCompat"
                )

    def test_all_providers_have_compat(self):
        for p in get_all_providers():
            assert get_provider_compat(p.id) is not None, (
                f"Provider {p.id} has no ProviderCompat entry"
            )
