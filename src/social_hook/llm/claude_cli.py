"""Claude CLI provider client using claude -p subprocess."""

import json
import os
import pwd
import re
import subprocess
import tempfile
from typing import Any

from social_hook.errors import ConfigError, MalformedResponseError
from social_hook.llm.base import LLMClient, NormalizedResponse, NormalizedToolCall, NormalizedUsage


def _extract_json(text: str) -> dict:
    """Extract a JSON object from model text output.

    Handles: raw JSON, markdown code-fenced JSON, or JSON embedded in text.
    Always returns a dict — if the parsed result is a list or scalar, falls
    through to brace-extraction to find the enclosing object.
    """
    text = text.strip()

    # 1. Try direct parse (must be a dict)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 3. Find outermost { ... } boundaries
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    raise MalformedResponseError(f"Could not extract JSON from CLI output: {text[:200]}")


def _extract_assistant_text(raw: list | dict) -> str | None:
    """Extract text from assistant message content blocks.

    The CLI's --output-format json returns an array of event objects.
    Assistant messages contain the full model output in content blocks.
    We use this instead of the envelope's "result" field because the
    result field is subject to stdout truncation (Claude Code CLI bug
    #2904: truncates large JSON lines at fixed character boundaries).

    Returns concatenated text from the last assistant message's text
    blocks, or None if no text content is found.
    """
    if not isinstance(raw, list):
        return None

    # Walk backwards to find the last assistant message with text content
    for el in reversed(raw):
        if not isinstance(el, dict) or el.get("type") != "assistant":
            continue
        content = el.get("message", {}).get("content", [])
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ]
        if texts:
            return "\n".join(texts)

    return None


class ClaudeCliClient(LLMClient):
    """LLM client that uses the Claude Code CLI (claude -p) for completions."""

    provider = "claude-cli"

    def __init__(self, model: str = "sonnet", verbose: bool = False):
        self.model = model
        self.full_id = f"{self.provider}/{self.model}"
        self.verbose = verbose

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> NormalizedResponse:
        # 0. Guard: claude -p --json-schema only supports a single tool schema
        if len(tools) != 1:
            raise ConfigError(
                f"Claude CLI supports exactly 1 tool schema, got {len(tools)}. "
                "Use anthropic/ provider for multi-tool calls."
            )

        # 1. Extract schema and tool name
        schema = tools[0]["input_schema"]
        tool_name = tools[0]["name"]

        # 2. Extract user message text
        user_msg = messages[-1]["content"]

        # 3. Build system prompt with embedded JSON output instructions.
        #    We do NOT use --json-schema because it forces the CLI into a
        #    multi-turn structured-output validation loop (3+ API round-trips
        #    minimum, 15-20+ for complex schemas). Instead we embed the schema
        #    in the prompt and parse JSON from the single-turn text output.
        json_instruction = (
            "\n\n---\n## Required Output Format\n"
            "You MUST respond with ONLY a valid JSON object matching this schema:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```\n"
            "Output ONLY the raw JSON object. No markdown code fences, "
            "no explanation, no text before or after the JSON."
        )
        effective_system = (system or "") + json_instruction

        # 4. Build command — no --json-schema (avoids multi-turn loop)
        #    Prompt is piped via stdin (not as a -p argument) to avoid
        #    the CLI's arg parser misinterpreting content that starts
        #    with dashes (e.g. "--- README.md ---") as flags.
        #    Uses stream-json (NDJSON) instead of json to avoid CLI bug #2904
        #    which truncates long string values in the JSON envelope.
        #    With stream-json, text arrives in small content_block_delta
        #    events that won't hit the truncation limit.
        cmd = [
            "claude",
            "-p",
            "--model",
            self.model,
            "--output-format",
            "stream-json",
            "--tools",
            "",
            "--no-session-persistence",
            "--setting-sources",
            "local",
            "--system-prompt",
            effective_system,
        ]

        # 5. Run subprocess with clean env for CLI auth
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        # Restore real HOME — the E2E harness or other callers may have
        # patched HOME to a temp dir for isolation, but the Claude CLI
        # needs the real home to find its authentication credentials.
        env["HOME"] = pwd.getpwuid(os.getuid()).pw_dir

        if self.verbose:
            import sys

            print(f"\n       [claude-cli] Model: {self.model}", file=sys.stderr, flush=True)
            print(f"       [claude-cli] Tool: {tool_name}", file=sys.stderr, flush=True)
            prompt_preview = user_msg[:200].replace("\n", " ")
            print(f"       [claude-cli] Prompt: {prompt_preview}...", file=sys.stderr, flush=True)
            print(
                "       [claude-cli] Calling claude -p (timeout 300s)...",
                file=sys.stderr,
                flush=True,
            )

        try:
            # Run in a new session so CLI doesn't share the terminal
            # (prevents notification sounds) and from temp dir so it
            # doesn't scan the project codebase.
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=tempfile.gettempdir(),
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(input=user_msg, timeout=300)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                proc.kill()
                proc.wait()
                if isinstance(exc, KeyboardInterrupt):
                    raise
                raise MalformedResponseError("Claude CLI timed out (300s)") from None
            result = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        except FileNotFoundError:
            raise ConfigError(
                "Claude CLI not found. Install Claude Code or use a different provider."
            ) from None

        if self.verbose:
            print(
                f"       [claude-cli] Exit code: {result.returncode}", file=sys.stderr, flush=True
            )
            if result.stderr:
                stderr_preview = result.stderr[:300].replace("\n", " ")
                print(f"       [claude-cli] Stderr: {stderr_preview}", file=sys.stderr, flush=True)

        if result.returncode != 0:
            detail = result.stderr or result.stdout[:500] if result.stdout else ""
            raise MalformedResponseError(f"Claude CLI error (exit {result.returncode}): {detail}")

        # 6. Parse NDJSON events from stream-json output.
        #    Each line is a separate JSON object. Text content arrives as
        #    small content_block_delta events that won't hit the CLI's
        #    string truncation limit (bug #2904).
        text_parts = []
        envelope = {}

        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Collect text from streaming delta events
            # Format: {"type":"stream_event","event":{"type":"content_block_delta",
            #          "delta":{"type":"text_delta","text":"chunk"}}}
            if event.get("type") == "stream_event":
                inner = event.get("event", {})
                if inner.get("type") == "content_block_delta":
                    delta = inner.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text_parts.append(delta.get("text", ""))

            # Capture the result envelope for usage data
            elif event.get("type") == "result":
                envelope = event

        result_text = "".join(text_parts)
        if not result_text:
            # Fallback: try the result field (may be truncated — bug #2904)
            result_text = envelope.get("result", "")
        if not result_text:
            raise MalformedResponseError("No text content in CLI response")

        structured_output = _extract_json(result_text)

        usage_data = envelope.get("usage", {})

        if self.verbose:
            turns = envelope.get("num_turns", "?")
            cost = envelope.get("total_cost_usd", 0)
            dur_ms = envelope.get("duration_ms", 0)
            api_ms = envelope.get("duration_api_ms", 0)
            overhead_ms = dur_ms - api_ms if dur_ms and api_ms else 0
            in_tok = usage_data.get("input_tokens", 0)
            out_tok = usage_data.get("output_tokens", 0)
            cache_read = usage_data.get("cache_read_input_tokens", 0)
            cache_create = usage_data.get("cache_creation_input_tokens", 0)
            print(
                f"       [claude-cli] Done: {turns} turns, ${cost:.4f}, "
                f"{dur_ms / 1000:.1f}s total ({api_ms / 1000:.1f}s API + {overhead_ms / 1000:.1f}s overhead)",
                file=sys.stderr,
                flush=True,
            )
            print(
                f"       [claude-cli] Tokens: in={in_tok} out={out_tok} cache_read={cache_read} cache_create={cache_create}",
                file=sys.stderr,
                flush=True,
            )
            output_preview = json.dumps(structured_output)[:300]
            print(f"       [claude-cli] Output: {output_preview}", file=sys.stderr, flush=True)

        # 7. Build normalized response
        tool_call = NormalizedToolCall(name=tool_name, input=structured_output)
        usage = NormalizedUsage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
            cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens", 0),
        )

        return NormalizedResponse(content=[tool_call], usage=usage, raw=envelope)
