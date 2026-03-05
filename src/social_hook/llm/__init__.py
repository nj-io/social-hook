"""LLM integration module for social-hook."""

from social_hook.llm.base import (
    LLMClient,
    NormalizedResponse,
    NormalizedToolCall,
    NormalizedUsage,
    ToolExtractionError,
    extract_tool_call,
)
from social_hook.llm.client import ClaudeClient
from social_hook.llm.drafter import Drafter
from social_hook.llm.dry_run import DryRunContext
from social_hook.llm.evaluator import Evaluator
from social_hook.llm.expert import Expert
from social_hook.llm.factory import create_client, parse_provider_model
from social_hook.llm.gatekeeper import Gatekeeper
from social_hook.llm.prompts import assemble_evaluator_context
from social_hook.llm.schemas import (
    CreateDraftInput,
    ExpertResponseInput,
    LogEvaluationInput,
    RouteActionInput,
)

__all__ = [
    "LLMClient",
    "NormalizedResponse",
    "NormalizedToolCall",
    "NormalizedUsage",
    "ToolExtractionError",
    "extract_tool_call",
    "create_client",
    "parse_provider_model",
    "ClaudeClient",
    "DryRunContext",
    "Evaluator",
    "Drafter",
    "Gatekeeper",
    "Expert",
    "assemble_evaluator_context",
    "CreateDraftInput",
    "LogEvaluationInput",
    "RouteActionInput",
    "ExpertResponseInput",
]
