"""Factory for creating LLM provider clients from model strings."""

from social_hook.errors import ConfigError
from social_hook.llm.base import LLMClient

KNOWN_PROVIDERS = {"anthropic", "claude-cli", "openai", "openrouter", "ollama"}


def parse_provider_model(model_str: str) -> tuple[str, str]:
    """Parse 'provider/model-id' into (provider, model_id).

    Provider prefix is REQUIRED:
      'anthropic/claude-opus-4-5' -> ('anthropic', 'claude-opus-4-5')
      'claude-cli/sonnet' -> ('claude-cli', 'sonnet')
      'openrouter/anthropic/claude-sonnet-4.5' -> ('openrouter', 'anthropic/claude-sonnet-4.5')
      'openai/gpt-4o' -> ('openai', 'gpt-4o')
      'ollama/llama3.3' -> ('ollama', 'llama3.3')

    Bare names raise ConfigError -- no backward compat needed.
    """
    for prefix in sorted(KNOWN_PROVIDERS, key=len, reverse=True):
        if model_str.startswith(prefix + "/"):
            return prefix, model_str[len(prefix) + 1:]

    raise ConfigError(
        f"Invalid model '{model_str}': must use provider/model-id format "
        f"(e.g., 'anthropic/claude-opus-4-5', 'claude-cli/sonnet')"
    )


def create_client(model_str: str, config, verbose: bool = False) -> LLMClient:
    """Create the appropriate LLM client from a provider/model string.

    Args:
        model_str: Provider/model-id string (e.g., 'anthropic/claude-opus-4-5')
        config: Config object with .env dict containing API keys
        verbose: If True, enable verbose logging on the client

    Returns:
        Configured LLMClient instance

    Raises:
        ConfigError: If provider unknown or required API key missing
    """
    provider, model_id = parse_provider_model(model_str)

    if provider == "anthropic":
        from social_hook.llm.client import ClaudeClient

        api_key = config.env.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ConfigError("ANTHROPIC_API_KEY required for anthropic/ models")
        return ClaudeClient(api_key=api_key, model=model_id)

    elif provider == "claude-cli":
        from social_hook.llm.claude_cli import ClaudeCliClient

        return ClaudeCliClient(model=model_id, verbose=verbose)

    elif provider == "openai":
        from social_hook.llm.openai_compat import OpenAICompatClient

        api_key = config.env.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ConfigError("OPENAI_API_KEY required for openai/ models")
        return OpenAICompatClient(api_key, model_id, "https://api.openai.com/v1",
                                  provider_name="openai")

    elif provider == "openrouter":
        from social_hook.llm.openai_compat import OpenAICompatClient

        api_key = config.env.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ConfigError("OPENROUTER_API_KEY required for openrouter/ models")
        return OpenAICompatClient(api_key, model_id, "https://openrouter.ai/api/v1",
                                  provider_name="openrouter")

    elif provider == "ollama":
        from social_hook.llm.openai_compat import OpenAICompatClient

        base_url = config.env.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return OpenAICompatClient("unused", model_id, base_url,
                                  provider_name="ollama")

    else:
        raise ConfigError(f"Unknown provider '{provider}' in model string '{model_str}'")
