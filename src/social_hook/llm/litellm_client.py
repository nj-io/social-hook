"""LiteLLM-backed client for OpenAI-compatible providers (OpenAI, OpenRouter, Ollama).

A single ``complete()`` over LiteLLM covers every OpenAI-compatible / aggregator
provider. LiteLLM handles per-provider request translation (token-field naming,
tool-call format, reasoning params), so this client stays thin. The Anthropic
direct API (``ClaudeClient``) and the ``claude -p`` subscription path
(``ClaudeCliClient``) have their own clients — this one is only reached for
``openai`` / ``openrouter`` / ``ollama``.
"""

import sys
from typing import Any

from social_hook.errors import ConfigError, MalformedResponseError
from social_hook.llm.base import LLMClient, NormalizedResponse, NormalizedToolCall, NormalizedUsage
from social_hook.llm.catalog import estimate_cost_cents
from social_hook.parsing import extract_json_object, safe_json_loads


class _TextBlock:
    """Minimal text content block, shaped like the blocks ``ClaudeClient`` keeps.

    ``extract_tool_call`` ignores non-``tool_use`` blocks; text-fallback callers
    (e.g. the Gatekeeper's ``_extract_text_content``) read ``.type == "text"``
    and ``.text``. Returning one of these lets a prose reply flow through the
    same graceful path instead of raising.
    """

    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


def _convert_tool_schema(anthropic_tool: dict) -> dict:
    """Convert an Anthropic tool schema to OpenAI function-calling format.

    Anthropic: {"name": ..., "description": ..., "input_schema": {...}}
    OpenAI:    {"type": "function", "function": {"name", "description", "parameters"}}
    """
    return {
        "type": "function",
        "function": {
            "name": anthropic_tool["name"],
            "description": anthropic_tool.get("description", ""),
            "parameters": anthropic_tool.get("input_schema", {}),
        },
    }


def _translate_content_blocks(content: Any) -> Any:
    """Translate Anthropic-style content blocks into OpenAI format.

    The pipeline builds Anthropic-shaped messages (the default provider is
    Anthropic). LiteLLM expects OpenAI-format input and handles OpenAI ->
    per-provider translation itself, so this only bridges Anthropic -> OpenAI
    for vision-capable models:

    Anthropic text:  {"type": "text", "text": "..."} — identical in OpenAI.
    Anthropic image: {"type": "image", "source": {"type": "base64",
                      "media_type": "image/png", "data": "..."}}
        -> OpenAI:   {"type": "image_url",
                      "image_url": {"url": "data:image/png;base64,..."}}

    String ``content`` passes through unchanged. Unknown block types pass
    through verbatim — LiteLLM raises its own error if it cannot parse them.
    """
    if not isinstance(content, list):
        return content
    translated: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            translated.append(block)
            continue
        btype = block.get("type")
        if btype == "image" and isinstance(block.get("source"), dict):
            src = block["source"]
            media_type = src.get("media_type", "image/png")
            data = src.get("data", "")
            translated.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                }
            )
        else:
            translated.append(block)
    return translated


def _litellm_model_string(provider: str, model_id: str) -> str:
    """Map a social-hook ``provider`` + ``model_id`` to a LiteLLM model string."""
    if provider == "openrouter":
        return f"openrouter/{model_id}"
    if provider == "ollama":
        # Route Ollama through LiteLLM's generic OpenAI-compatible path so the
        # existing OLLAMA_BASE_URL (".../v1") convention keeps working.
        return f"openai/{model_id}"
    # openai (and any future OpenAI-compatible provider): bare model id.
    return model_id


class LiteLLMClient(LLMClient):
    """LLM client for OpenAI-compatible / aggregator providers via LiteLLM."""

    def __init__(
        self,
        model_id: str,
        provider_name: str,
        api_key: str | None = None,
        api_base: str | None = None,
        referer: str | None = None,
        app_title: str | None = None,
        verbose: bool = False,
    ) -> None:
        try:
            import litellm  # noqa: F401
        except ImportError as e:
            raise ConfigError(
                "litellm package required for openai/openrouter/ollama providers."
            ) from e
        self.provider = provider_name
        self.model = model_id
        # full_id is the social-hook identity (usage logging + catalog lookup),
        # NOT the litellm-mangled model string.
        self.full_id = f"{provider_name}/{model_id}"
        self._litellm_model = _litellm_model_string(provider_name, model_id)
        self._api_key = api_key
        self._api_base = api_base
        self._referer = referer
        self._app_title = app_title
        self.verbose = verbose

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> NormalizedResponse:
        import litellm

        openai_tools = [_convert_tool_schema(t) for t in tools]

        # Translate Anthropic-style content-block lists (text + image blocks)
        # into OpenAI's image_url data-URL format so vision-capable models see
        # images natively; LiteLLM then maps OpenAI -> the target provider.
        openai_messages: list[dict[str, Any]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        for msg in messages:
            translated = dict(msg)
            translated["content"] = _translate_content_blocks(msg.get("content"))
            openai_messages.append(translated)

        kwargs: dict[str, Any] = {
            "model": self._litellm_model,
            "messages": openai_messages,
            "tools": openai_tools,
            "max_tokens": max_tokens,
            # Let LiteLLM drop params a given provider/model doesn't support
            # (token-field naming, reasoning params) instead of erroring.
            "drop_params": True,
        }
        # The pipeline always passes exactly one tool — force it. drop_params
        # lets litellm drop a forced tool_choice the model can't honor; a model
        # that then answers in prose is recovered by the JSON-from-text fallback
        # in _extract_content. "required" covers the rare multi-tool case.
        if len(tools) == 1:
            kwargs["tool_choice"] = {"type": "function", "function": {"name": tools[0]["name"]}}
        elif tools:
            kwargs["tool_choice"] = "required"
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self.provider == "openrouter":
            headers = {}
            if self._referer:
                headers["HTTP-Referer"] = self._referer
            if self._app_title:
                headers["X-Title"] = self._app_title
            if headers:
                kwargs["extra_headers"] = headers

        try:
            response = litellm.completion(**kwargs)
        except Exception as e:
            raise MalformedResponseError(f"{self.provider} API error: {e}") from e

        content = self._extract_content(response, tools)
        usage = self._extract_usage(response)

        if self.verbose:
            print(
                f"       [litellm] {self.full_id}: in={usage.input_tokens} "
                f"out={usage.output_tokens} cost={usage.cost_cents:.4f}c "
                f"({usage.cost_source})",
                file=sys.stderr,
                flush=True,
            )

        return NormalizedResponse(content=content, usage=usage, raw=response)

    def _extract_content(self, response: Any, tools: list[dict[str, Any]]) -> list[Any]:
        """Normalize the reply into tool-call (and text) blocks.

        Primary path: native ``tool_calls``. Fallback: if the model answered in
        prose/JSON without a tool call and there is a single expected tool,
        parse a JSON object from the text and synthesize the tool call. If the
        text isn't JSON, return it as a text block (mirroring ``ClaudeClient``)
        so prose-fallback callers still work — this method never raises.
        """
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []

        blocks: list[Any] = []
        for tc in tool_calls:
            blocks.append(
                NormalizedToolCall(
                    name=tc.function.name,
                    input=safe_json_loads(
                        tc.function.arguments,
                        f"tool_call {tc.function.name} arguments",
                        default={},
                    ),
                )
            )
        if blocks:
            return blocks

        content = getattr(message, "content", None)
        text = content.strip() if isinstance(content, str) else ""
        if len(tools) == 1 and text:
            try:
                parsed = extract_json_object(text)
                return [NormalizedToolCall(name=tools[0]["name"], input=parsed)]
            except MalformedResponseError:
                pass
        if text:
            # Preserve prose so text-fallback callers (Gatekeeper) can read it.
            return [_TextBlock(text)]
        return []

    def _extract_usage(self, response: Any) -> NormalizedUsage:
        usage_obj = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
        ptd = getattr(usage_obj, "prompt_tokens_details", None)
        cache_read = int((getattr(ptd, "cached_tokens", 0) if ptd is not None else 0) or 0)
        # OpenAI-style prompt_tokens INCLUDES cached tokens; normalize to the
        # Anthropic-style disjoint accounting (non-cached input + separate
        # cache_read) so cost and usage logging are consistent across providers.
        input_tokens = max(prompt_tokens - cache_read, 0)

        cost_cents, cost_source = self._resolve_cost(
            response, input_tokens, output_tokens, cache_read
        )
        return NormalizedUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cost_cents=cost_cents,
            cost_source=cost_source,
        )

    def _resolve_cost(
        self, response: Any, input_tokens: int, output_tokens: int, cache_read: int
    ) -> tuple[float, str]:
        """Prefer LiteLLM's real cost; fall back to the catalog; never silent $0.

        Order: provider-reported ``response_cost`` -> ``litellm.completion_cost``
        -> catalog estimate -> ``unknown``. ``response_cost`` can be present but
        ``None`` (unmapped model) and ``completion_cost`` raises for unmapped
        models — GLM-5.2 and other new models are the likely cases — so both
        are guarded and the catalog fallback carries them.
        """
        hidden = getattr(response, "_hidden_params", None) or {}
        rc = hidden.get("response_cost")
        if rc is not None and rc > 0:
            return round(rc * 100, 4), "provider"

        try:
            import litellm

            computed = litellm.completion_cost(completion_response=response)
            if computed and computed > 0:
                return round(computed * 100, 4), "provider"
        except Exception:
            pass

        estimated = estimate_cost_cents(self.full_id, input_tokens, output_tokens, cache_read)
        if estimated > 0:
            return estimated, "registry"
        return 0.0, "unknown"
