"""Claude CLI provider client using claude -p subprocess."""

import json
import os
import subprocess
from typing import Any, Optional

from social_hook.errors import ConfigError, MalformedResponseError
from social_hook.llm.base import LLMClient, NormalizedResponse, NormalizedToolCall, NormalizedUsage


class ClaudeCliClient(LLMClient):
    """LLM client that uses the Claude Code CLI (claude -p) for completions."""

    provider = "claude-cli"

    def __init__(self, model: str = "sonnet"):
        self.model = model
        self.full_id = f"{self.provider}/{self.model}"

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        operation_type: Optional[str] = None,
        db: Optional[Any] = None,
        project_id: Optional[str] = None,
        commit_hash: Optional[str] = None,
    ) -> NormalizedResponse:
        # 0. Guard: claude -p --json-schema only supports a single tool schema
        if len(tools) != 1:
            raise ConfigError(
                f"Claude CLI supports exactly 1 tool schema, got {len(tools)}. "
                "Use anthropic/ provider for multi-tool calls."
            )

        # 1. Extract JSON schema from tools[0]["input_schema"]
        schema = json.dumps(tools[0]["input_schema"])
        tool_name = tools[0]["name"]

        # 2. Extract user message text
        user_msg = messages[-1]["content"]

        # 3. Build command
        cmd = [
            "claude", "-p", user_msg,
            "--model", self.model,
            "--output-format", "json",
            "--json-schema", schema,
            "--tools", "",
            "--no-session-persistence",
        ]
        if system:
            cmd += ["--system-prompt", system]

        # 4. Run subprocess with CLAUDECODE env var removed
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
        except FileNotFoundError:
            raise ConfigError("Claude CLI not found. Install Claude Code or use a different provider.")
        except subprocess.TimeoutExpired:
            raise MalformedResponseError("Claude CLI timed out (120s)")

        if result.returncode != 0:
            raise MalformedResponseError(f"Claude CLI error: {result.stderr}")

        # 5. Parse response envelope
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise MalformedResponseError(f"Claude CLI returned invalid JSON: {result.stdout[:200]}")

        structured_output = envelope.get("structured_output")
        if structured_output is None:
            raise MalformedResponseError("No structured output in CLI response")

        usage_data = envelope.get("usage", {})

        # 6. Build normalized response
        tool_call = NormalizedToolCall(name=tool_name, input=structured_output)
        usage = NormalizedUsage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
            cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens", 0),
        )

        # 7. Log usage if db context provided
        if db and operation_type:
            import sqlite3
            from social_hook.db import operations as ops
            from social_hook.filesystem import generate_id
            from social_hook.models import UsageLog

            usage_log = UsageLog(
                id=generate_id("usage"),
                project_id=project_id,
                operation_type=operation_type,
                model=self.full_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_input_tokens,
                cache_creation_tokens=usage.cache_creation_input_tokens,
                cost_cents=0.0,  # CLI uses subscription, no per-call cost
                commit_hash=commit_hash,
            )
            if hasattr(db, "insert_usage"):
                db.insert_usage(usage_log)
            elif isinstance(db, sqlite3.Connection):
                ops.insert_usage(db, usage_log)

        return NormalizedResponse(content=[tool_call], usage=usage, raw=envelope)
