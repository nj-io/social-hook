"""Constants and shared utilities for the E2E test suite."""

import time

# Test commits from this repo's git history
COMMITS = {
    "significant": "0d50ea7",  # Implement WS1 Foundation
    "major_feature": "93fbd11",  # Implement WS3 adapters
    "large_feature": "d47c089",  # WS4 gap fix
    "bugfix": "409bf74",  # Fix setup wizard UX
    "docs_only": "3b85806",  # Fix section nav scroll reliability and gitignore
    "docs_only_2": "8c139a1",  # Fix E2E A10: pass repo root
    "initial": "c085a12",  # Initial commit: Research documentation
    "web_dashboard": "07c85d9",  # Add web dashboard + per-platform pipeline
    "arc_llm_roles": "c180f7a",  # WS2: introduces entire LLM layer
    "arc_journey": "0399e55",  # New subsystem: dev journey capture
    "arc_multi_provider": "f9267e2",  # New abstraction: provider layer
    "arc_media_pipeline": "1ef0058",  # New pipeline: media generation
}

SECTION_MAP = {
    "onboarding": "A",
    "pipeline": "B",
    "narrative": "C",
    "draft": "D",
    "scheduler": "E",
    "bot": "FGH",
    "setup": "I",
    "cli": "J",
    "crosscutting": "K",
    "multiprovider": "L",
    "journey": "M",
    "web": "N",
    "queue": "Q",
    "hooks": "R",
    "crosspost": "S",
    "ratelimits": "T",
}

# Provider presets: maps --provider flag to model configs
PROVIDER_PRESETS = {
    "claude-cli": {
        "evaluator": "claude-cli/sonnet",
        "drafter": "claude-cli/sonnet",
        "gatekeeper": "claude-cli/haiku",
        "cost": "$0 (uses Claude Code subscription)",
    },
    "anthropic": {
        "evaluator": "anthropic/claude-sonnet-4-5",
        "drafter": "anthropic/claude-sonnet-4-5",
        "gatekeeper": "anthropic/claude-haiku-4-5",
        "cost": "~$3-9 (Anthropic API credits)",
    },
}

LLM_COOLDOWN_SECONDS = 20


def rate_limit_cooldown():
    """Wait between LLM calls to avoid rate limiting."""
    print(f"       (waiting {LLM_COOLDOWN_SECONDS}s for rate limit cooldown)")
    time.sleep(LLM_COOLDOWN_SECONDS)
