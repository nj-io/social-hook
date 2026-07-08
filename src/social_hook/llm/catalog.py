"""Model catalog with rich metadata for all supported LLM providers.

This is the single source of truth for model display metadata and per-token
pricing across the app: the setup wizard, the web settings UI (via the
``/api/models`` endpoint), and cost estimation all read from here. Providers
that don't return a real per-call cost (Anthropic SDK) fall back to
``estimate_cost_cents`` so pricing lives in exactly one place.
"""

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
    """Provider compatibility flags (reference documentation).

    LiteLLM now handles request translation for the OpenAI-compatible
    providers, so these flags are informational — they document the quirks a
    hand-rolled client would need to honor, not runtime behavior.
    """

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
        id="claude-opus-4-8",
        provider="anthropic",
        full_id="anthropic/claude-opus-4-8",
        name="Claude Opus 4.8",
        description="Most capable Opus-tier model for complex reasoning and agentic work",
        tier="premium",
        context_window=200_000,
        max_output_tokens=64_000,
        cost_input=5.0,
        cost_output=25.0,
        supports_tools=True,
        supports_vision=True,
        supports_cache=True,
    ),
    ModelInfo(
        id="claude-sonnet-5",
        provider="anthropic",
        full_id="anthropic/claude-sonnet-5",
        name="Claude Sonnet 5",
        description="Balanced speed and intelligence, near-Opus on coding (intro pricing to 2026-08-31)",
        tier="standard",
        context_window=200_000,
        max_output_tokens=64_000,
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
        max_output_tokens=32_000,
        cost_input=1.0,
        cost_output=5.0,
        supports_tools=True,
        supports_vision=True,
        supports_cache=True,
    ),
    ModelInfo(
        id="claude-fable-5",
        provider="anthropic",
        full_id="anthropic/claude-fable-5",
        name="Claude Fable 5",
        description="Anthropic's most capable model for the hardest long-horizon work",
        tier="premium",
        context_window=200_000,
        max_output_tokens=64_000,
        cost_input=10.0,
        cost_output=50.0,
        supports_tools=True,
        supports_vision=True,
        supports_cache=True,
    ),
    # --- Claude CLI (subscription; $0 marginal cost) ---
    ModelInfo(
        id="opus",
        provider="claude-cli",
        full_id="claude-cli/opus",
        name="Claude Opus (CLI)",
        description="Opus via Claude Code subscription — no API key, $0 per call",
        tier="premium",
        context_window=200_000,
        max_output_tokens=64_000,
        supports_tools=True,
        supports_vision=False,
    ),
    ModelInfo(
        id="sonnet",
        provider="claude-cli",
        full_id="claude-cli/sonnet",
        name="Claude Sonnet (CLI)",
        description="Sonnet via Claude Code subscription — no API key, $0 per call",
        tier="standard",
        context_window=200_000,
        max_output_tokens=64_000,
        supports_tools=True,
        supports_vision=False,
    ),
    ModelInfo(
        id="haiku",
        provider="claude-cli",
        full_id="claude-cli/haiku",
        name="Claude Haiku (CLI)",
        description="Haiku via Claude Code subscription — no API key, $0 per call",
        tier="budget",
        context_window=200_000,
        max_output_tokens=32_000,
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
    # --- OpenRouter (provider/model slugs; pricing verified via OpenRouter) ---
    ModelInfo(
        id="z-ai/glm-5.2",
        provider="openrouter",
        full_id="openrouter/z-ai/glm-5.2",
        name="GLM-5.2 (OpenRouter)",
        description="Zhipu GLM-5.2 — strong open model, 1M context, native tool use",
        tier="standard",
        context_window=1_000_000,
        max_output_tokens=64_000,
        cost_input=0.93,
        cost_output=3.0,
        supports_tools=True,
        supports_vision=False,
    ),
    ModelInfo(
        id="z-ai/glm-4.6",
        provider="openrouter",
        full_id="openrouter/z-ai/glm-4.6",
        name="GLM-4.6 (OpenRouter)",
        description="Zhipu GLM-4.6 — affordable open model with tool use",
        tier="budget",
        context_window=202_752,
        max_output_tokens=32_000,
        cost_input=0.43,
        cost_output=1.74,
        supports_tools=True,
        supports_vision=False,
    ),
    ModelInfo(
        id="deepseek/deepseek-v3.2-exp",
        provider="openrouter",
        full_id="openrouter/deepseek/deepseek-v3.2-exp",
        name="DeepSeek V3.2 (OpenRouter)",
        description="DeepSeek V3.2 — very low cost, tool use",
        tier="budget",
        context_window=163_840,
        max_output_tokens=16_384,
        cost_input=0.27,
        cost_output=0.41,
        supports_tools=True,
        supports_vision=False,
    ),
    ModelInfo(
        id="google/gemini-2.5-flash",
        provider="openrouter",
        full_id="openrouter/google/gemini-2.5-flash",
        name="Gemini 2.5 Flash (OpenRouter)",
        description="Google Gemini 2.5 Flash — 1M context, vision, tool use",
        tier="budget",
        context_window=1_000_000,
        max_output_tokens=65_536,
        cost_input=0.30,
        cost_output=2.50,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="anthropic/claude-sonnet-5",
        provider="openrouter",
        full_id="openrouter/anthropic/claude-sonnet-5",
        name="Claude Sonnet 5 (OpenRouter)",
        description="Claude Sonnet 5 routed via OpenRouter",
        tier="standard",
        context_window=1_000_000,
        max_output_tokens=64_000,
        cost_input=2.0,
        cost_output=10.0,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="moonshotai/kimi-k2-0905",
        provider="openrouter",
        full_id="openrouter/moonshotai/kimi-k2-0905",
        name="Kimi K2 (OpenRouter)",
        description="Moonshot Kimi K2 — large context, tool use",
        tier="budget",
        context_window=262_144,
        max_output_tokens=16_384,
        cost_input=0.60,
        cost_output=2.50,
        supports_tools=True,
        supports_vision=False,
    ),
]

# Index models by provider and by full_id for fast lookup
_MODELS_BY_PROVIDER: dict[str, list[ModelInfo]] = {}
_MODELS_BY_FULL_ID: dict[str, ModelInfo] = {}
for _m in _MODELS:
    _MODELS_BY_PROVIDER.setdefault(_m.provider, []).append(_m)
    _MODELS_BY_FULL_ID[_m.full_id] = _m


# =============================================================================
# Public API
# =============================================================================


def get_all_models() -> list[ModelInfo]:
    """Return every static model in the catalog (all providers)."""
    return list(_MODELS)


def get_models_for_provider(provider_id: str) -> list[ModelInfo]:
    """Return all static models for a provider.

    Args:
        provider_id: Provider identifier (e.g., "anthropic", "openai")

    Returns:
        List of ModelInfo for the provider (empty for unknown/ollama)
    """
    return list(_MODELS_BY_PROVIDER.get(provider_id, []))


def get_model_by_full_id(full_id: str) -> ModelInfo | None:
    """Look up a model by its ``provider/model-id`` string.

    Args:
        full_id: e.g., "anthropic/claude-opus-4-8" or "openrouter/z-ai/glm-5.2"

    Returns:
        ModelInfo or None if not in the static catalog.
    """
    return _MODELS_BY_FULL_ID.get(full_id)


def estimate_cost_cents(
    full_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Estimate call cost in cents from the catalog's per-token pricing.

    This is the fallback cost source when a provider doesn't report a real
    per-call cost (e.g. the Anthropic SDK). Cache tokens use Anthropic's
    standard multipliers relative to the input rate — reads at 0.1x, writes
    at 1.25x — applied to whatever model's input price is on file. Returns
    0.0 for unknown or unpriced models.

    Args:
        full_id: ``provider/model-id`` string.
        input_tokens: Non-cached input tokens.
        output_tokens: Output tokens.
        cache_read_tokens: Tokens served from cache (billed at 0.1x input).
        cache_creation_tokens: Tokens written to cache (billed at 1.25x input).

    Returns:
        Estimated cost in cents.
    """
    model = get_model_by_full_id(full_id)
    if not model or (not model.cost_input and not model.cost_output):
        return 0.0
    dollars = (
        (input_tokens / 1_000_000) * model.cost_input
        + (output_tokens / 1_000_000) * model.cost_output
        + (cache_read_tokens / 1_000_000) * model.cost_input * 0.1
        + (cache_creation_tokens / 1_000_000) * model.cost_input * 1.25
    )
    return round(dollars * 100, 4)


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
        Human-readable string like "Claude Sonnet 5 - Balanced... [$3.00/M in]"
    """
    if model.cost_input > 0:
        cost_str = f" [${model.cost_input:.2f}/M in]"
    elif model.tier == "local":
        cost_str = " [free/local]"
    else:
        cost_str = " [subscription]"
    return f"{model.name} - {model.description}{cost_str}"
