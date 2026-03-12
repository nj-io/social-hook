"""Model catalog with rich metadata for all supported LLM providers."""

from dataclasses import dataclass

import requests


@dataclass
class ModelInfo:
    """Per-model metadata."""

    id: str
    provider: str
    full_id: str
    name: str
    description: str
    tier: str  # "premium", "standard", "budget", "local"
    context_window: int
    max_output_tokens: int
    cost_input: float = 0.0  # per 1M tokens in dollars
    cost_output: float = 0.0  # per 1M tokens in dollars
    supports_tools: bool = True
    supports_vision: bool = False
    supports_cache: bool = False


@dataclass
class ProviderInfo:
    """Per-provider metadata."""

    id: str
    name: str
    description: str
    env_key: str
    base_url: str
    api_format: str  # "anthropic", "openai", "cli", "ollama"


@dataclass
class ProviderCompat:
    """Provider compatibility flags for request building."""

    system_in_messages: bool = False
    tool_schema_format: str = "anthropic"  # "anthropic" or "openai"
    max_tokens_field: str = "max_tokens"
    supports_cache: bool = False


# =============================================================================
# Static Catalog Data
# =============================================================================

_PROVIDERS: dict[str, ProviderInfo] = {
    "anthropic": ProviderInfo(
        id="anthropic",
        name="Anthropic",
        description="Direct Anthropic API access",
        env_key="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com",
        api_format="anthropic",
    ),
    "claude-cli": ProviderInfo(
        id="claude-cli",
        name="Claude CLI",
        description="Uses Claude CLI with subscription (no API key needed)",
        env_key="",
        base_url="",
        api_format="cli",
    ),
    "openai": ProviderInfo(
        id="openai",
        name="OpenAI",
        description="Direct OpenAI API access",
        env_key="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        api_format="openai",
    ),
    "openrouter": ProviderInfo(
        id="openrouter",
        name="OpenRouter",
        description="Multi-provider aggregator with unified API",
        env_key="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
        api_format="openai",
    ),
    "ollama": ProviderInfo(
        id="ollama",
        name="Ollama",
        description="Local models via Ollama server",
        env_key="",
        base_url="http://localhost:11434",
        api_format="ollama",
    ),
}

_PROVIDER_COMPAT: dict[str, ProviderCompat] = {
    "anthropic": ProviderCompat(
        system_in_messages=False,
        tool_schema_format="anthropic",
        max_tokens_field="max_tokens",
        supports_cache=True,
    ),
    "claude-cli": ProviderCompat(
        system_in_messages=False,
        tool_schema_format="anthropic",
        max_tokens_field="max_tokens",
        supports_cache=False,
    ),
    "openai": ProviderCompat(
        system_in_messages=True,
        tool_schema_format="openai",
        max_tokens_field="max_completion_tokens",
        supports_cache=False,
    ),
    "openrouter": ProviderCompat(
        system_in_messages=True,
        tool_schema_format="openai",
        max_tokens_field="max_tokens",
        supports_cache=False,
    ),
    "ollama": ProviderCompat(
        system_in_messages=True,
        tool_schema_format="openai",
        max_tokens_field="max_tokens",
        supports_cache=False,
    ),
}

_MODELS: list[ModelInfo] = [
    # --- Anthropic (direct API) ---
    ModelInfo(
        id="claude-opus-4-5",
        provider="anthropic",
        full_id="anthropic/claude-opus-4-5",
        name="Claude Opus 4.5",
        description="Most capable Claude model for complex reasoning",
        tier="premium",
        context_window=200_000,
        max_output_tokens=32_000,
        cost_input=15.0,
        cost_output=75.0,
        supports_tools=True,
        supports_vision=True,
        supports_cache=True,
    ),
    ModelInfo(
        id="claude-sonnet-4-5",
        provider="anthropic",
        full_id="anthropic/claude-sonnet-4-5",
        name="Claude Sonnet 4.5",
        description="Balanced performance and cost",
        tier="standard",
        context_window=200_000,
        max_output_tokens=16_000,
        cost_input=3.0,
        cost_output=15.0,
        supports_tools=True,
        supports_vision=True,
        supports_cache=True,
    ),
    ModelInfo(
        id="claude-haiku-4-5",
        provider="anthropic",
        full_id="anthropic/claude-haiku-4-5",
        name="Claude Haiku 4.5",
        description="Fast and affordable for simple tasks",
        tier="budget",
        context_window=200_000,
        max_output_tokens=8_192,
        cost_input=0.80,
        cost_output=4.0,
        supports_tools=True,
        supports_vision=True,
        supports_cache=True,
    ),
    # --- Claude CLI ---
    ModelInfo(
        id="opus",
        provider="claude-cli",
        full_id="claude-cli/opus",
        name="Claude Opus (CLI)",
        description="Opus via CLI subscription",
        tier="premium",
        context_window=200_000,
        max_output_tokens=32_000,
        supports_tools=True,
        supports_vision=False,
    ),
    ModelInfo(
        id="sonnet",
        provider="claude-cli",
        full_id="claude-cli/sonnet",
        name="Claude Sonnet (CLI)",
        description="Sonnet via CLI subscription",
        tier="standard",
        context_window=200_000,
        max_output_tokens=16_000,
        supports_tools=True,
        supports_vision=False,
    ),
    ModelInfo(
        id="haiku",
        provider="claude-cli",
        full_id="claude-cli/haiku",
        name="Claude Haiku (CLI)",
        description="Haiku via CLI subscription",
        tier="budget",
        context_window=200_000,
        max_output_tokens=8_192,
        supports_tools=True,
        supports_vision=False,
    ),
    # --- OpenAI ---
    ModelInfo(
        id="gpt-4o",
        provider="openai",
        full_id="openai/gpt-4o",
        name="GPT-4o",
        description="OpenAI flagship multimodal model",
        tier="standard",
        context_window=128_000,
        max_output_tokens=16_384,
        cost_input=2.50,
        cost_output=10.0,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="gpt-4o-mini",
        provider="openai",
        full_id="openai/gpt-4o-mini",
        name="GPT-4o Mini",
        description="Small, fast, affordable OpenAI model",
        tier="budget",
        context_window=128_000,
        max_output_tokens=16_384,
        cost_input=0.15,
        cost_output=0.60,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="o3",
        provider="openai",
        full_id="openai/o3",
        name="o3",
        description="OpenAI reasoning model",
        tier="premium",
        context_window=200_000,
        max_output_tokens=100_000,
        cost_input=10.0,
        cost_output=40.0,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="o4-mini",
        provider="openai",
        full_id="openai/o4-mini",
        name="o4-mini",
        description="OpenAI small reasoning model",
        tier="standard",
        context_window=200_000,
        max_output_tokens=100_000,
        cost_input=1.10,
        cost_output=4.40,
        supports_tools=True,
        supports_vision=True,
    ),
    # --- OpenRouter ---
    ModelInfo(
        id="anthropic/claude-sonnet-4.5",
        provider="openrouter",
        full_id="openrouter/anthropic/claude-sonnet-4.5",
        name="Claude Sonnet 4.5 (OpenRouter)",
        description="Claude Sonnet 4.5 via OpenRouter",
        tier="standard",
        context_window=200_000,
        max_output_tokens=16_000,
        cost_input=3.0,
        cost_output=15.0,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="openai/gpt-4o",
        provider="openrouter",
        full_id="openrouter/openai/gpt-4o",
        name="GPT-4o (OpenRouter)",
        description="GPT-4o via OpenRouter",
        tier="standard",
        context_window=128_000,
        max_output_tokens=16_384,
        cost_input=2.50,
        cost_output=10.0,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="google/gemini-2.5-flash",
        provider="openrouter",
        full_id="openrouter/google/gemini-2.5-flash",
        name="Gemini 2.5 Flash (OpenRouter)",
        description="Google Gemini 2.5 Flash via OpenRouter",
        tier="budget",
        context_window=1_000_000,
        max_output_tokens=65_536,
        cost_input=0.15,
        cost_output=0.60,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="deepseek/deepseek-chat-v3",
        provider="openrouter",
        full_id="openrouter/deepseek/deepseek-chat-v3",
        name="DeepSeek Chat V3 (OpenRouter)",
        description="DeepSeek V3 via OpenRouter",
        tier="budget",
        context_window=64_000,
        max_output_tokens=8_192,
        cost_input=0.27,
        cost_output=1.10,
        supports_tools=True,
        supports_vision=False,
    ),
    ModelInfo(
        id="meta-llama/llama-3.3-70b-instruct",
        provider="openrouter",
        full_id="openrouter/meta-llama/llama-3.3-70b-instruct",
        name="Llama 3.3 70B (OpenRouter)",
        description="Meta Llama 3.3 70B via OpenRouter",
        tier="budget",
        context_window=128_000,
        max_output_tokens=4_096,
        cost_input=0.39,
        cost_output=0.39,
        supports_tools=True,
        supports_vision=False,
    ),
]

# Index models by provider for fast lookup
_MODELS_BY_PROVIDER: dict[str, list[ModelInfo]] = {}
for _m in _MODELS:
    _MODELS_BY_PROVIDER.setdefault(_m.provider, []).append(_m)


# =============================================================================
# Public API
# =============================================================================


def get_models_for_provider(provider_id: str) -> list[ModelInfo]:
    """Return all static models for a provider.

    Args:
        provider_id: Provider identifier (e.g., "anthropic", "openai")

    Returns:
        List of ModelInfo for the provider (empty for unknown/ollama)
    """
    return list(_MODELS_BY_PROVIDER.get(provider_id, []))


def get_provider_info(provider_id: str) -> ProviderInfo | None:
    """Return provider metadata.

    Args:
        provider_id: Provider identifier

    Returns:
        ProviderInfo or None if unknown
    """
    return _PROVIDERS.get(provider_id)


def get_provider_compat(provider_id: str) -> ProviderCompat | None:
    """Return provider compatibility flags.

    Args:
        provider_id: Provider identifier

    Returns:
        ProviderCompat or None if unknown
    """
    return _PROVIDER_COMPAT.get(provider_id)


def get_all_providers() -> list[ProviderInfo]:
    """Return all registered providers.

    Returns:
        List of ProviderInfo for all known providers
    """
    return list(_PROVIDERS.values())


def discover_ollama_models(base_url: str = "http://localhost:11434") -> list[ModelInfo]:
    """Discover models available on an Ollama server.

    Calls GET /api/tags on the Ollama server and builds ModelInfo
    for each available model.

    Args:
        base_url: Ollama server URL (default: http://localhost:11434)

    Returns:
        List of ModelInfo for discovered models (empty on error)
    """
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    models = []
    for entry in data.get("models", []):
        model_name = entry.get("name", "")
        if not model_name:
            continue
        # Strip :latest tag for cleaner id
        clean_name = model_name.removesuffix(":latest")
        size = entry.get("size", 0)
        details = entry.get("details", {})
        param_size = details.get("parameter_size", "")

        models.append(
            ModelInfo(
                id=clean_name,
                provider="ollama",
                full_id=f"ollama/{clean_name}",
                name=f"{clean_name} (Ollama)",
                description=f"Local {param_size} model"
                if param_size
                else f"Local model ({size // (1024 * 1024)}MB)",
                tier="local",
                context_window=int(details.get("context_length", 4096)),
                max_output_tokens=4096,
                supports_tools=True,
                supports_vision=False,
            )
        )
    return models


def format_model_choice(model: ModelInfo) -> str:
    """Format a model for display in selection UI.

    Args:
        model: ModelInfo to format

    Returns:
        Human-readable string like "Claude Sonnet 4.5 - Balanced performance and cost [$3.00/M in]"
    """
    if model.cost_input > 0:
        cost_str = f" [${model.cost_input:.2f}/M in]"
    elif model.tier == "local":
        cost_str = " [free/local]"
    else:
        cost_str = " [subscription]"
    return f"{model.name} - {model.description}{cost_str}"
