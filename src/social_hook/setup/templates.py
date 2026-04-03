"""Content strategy templates — single source of truth.

Used by CLI wizard, served to web frontend via GET /api/wizard/templates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyDefaults:
    """Default values pre-filled by a strategy template."""

    identity: str = "myself"
    voice_tone: str = ""
    audience: str = ""
    technical_level: str = "intermediate"
    platform_filter: str = "all"
    platform_frequency: str = "moderate"
    post_when: str = ""
    avoid: str = ""
    example_intro_hook: str = ""


@dataclass
class StrategyTemplate:
    """A content strategy template with default values."""

    id: str
    name: str
    description: str
    defaults: StrategyDefaults = field(default_factory=StrategyDefaults)


STRATEGY_TEMPLATES: list[StrategyTemplate] = [
    StrategyTemplate(
        id="building-public",
        name="Build in Public",
        description="Share your journey transparently \u2014 struggles, decisions, and progress",
        defaults=StrategyDefaults(
            identity="myself",
            voice_tone="Conversational, honest, journey-focused. Shows the messy parts.",
            audience="Developers, indie hackers, builders",
            technical_level="intermediate",
            platform_filter="all",
            platform_frequency="high",
            post_when="All development activity \u2014 decisions, struggles, progress, mistakes",
            avoid="Corporate speak, polished-only outcomes, hype",
            example_intro_hook=(
                "Hi, I'm [name]. I'm building [project] and sharing the journey "
                "\u2014 the wins, the mistakes, and everything in between."
            ),
        ),
    ),
    StrategyTemplate(
        id="product-news",
        name="Release Updates",
        description="Announce features, improvements, and milestones professionally",
        defaults=StrategyDefaults(
            identity="company",
            voice_tone="Clear, professional, outcome-focused. Emphasizes value to users.",
            audience="Users and developers interested in the product",
            technical_level="intermediate",
            platform_filter="significant",
            platform_frequency="low",
            post_when="Features, improvements, launches, milestones",
            avoid="Internal refactoring, process narratives, struggles",
            example_intro_hook=(
                "We're [company], building [project]. Follow along for feature updates "
                "and what's coming next."
            ),
        ),
    ),
    StrategyTemplate(
        id="technical-deep-dive",
        name="Curated Technical",
        description="Polished technical posts about architecture, patterns, and implementations",
        defaults=StrategyDefaults(
            identity="myself",
            voice_tone="Technical, detailed, confident. Shows depth without being dry.",
            audience="Senior developers, architects, technical leads",
            technical_level="advanced",
            platform_filter="notable",
            platform_frequency="moderate",
            post_when=(
                "Architecture decisions, interesting patterns, deep implementations, trade-offs"
            ),
            avoid="Surface-level updates, announcements without technical substance",
            example_intro_hook=(
                "I'm [name], [role]. I write about the technical decisions behind "
                "[project] \u2014 architecture, patterns, and trade-offs."
            ),
        ),
    ),
    StrategyTemplate(
        id="brand-primary",
        name="Brand & Marketing",
        description="High-level marketing content — hooks, outcomes, visual proof. Scroll-stoppers.",
        defaults=StrategyDefaults(
            identity="company",
            voice_tone=(
                "Confident, concise, visual-first. Every post earns the scroll-stop. "
                "Open with an outcome or provocation, never a description of what changed."
            ),
            audience="Developers and engineering leaders evaluating tools in this space",
            technical_level="intermediate",
            platform_filter="significant",
            platform_frequency="low",
            post_when=(
                "Only when a user-facing feature demonstrates a core value prop. "
                "Skip all internal work, refactoring, and incremental improvements. "
                "During pre-launch: hold all content until hero launch is ready. "
                "Post-launch: feature spotlights with visual proof and concrete outcomes."
            ),
            avoid=(
                "Developer diary tone, implementation details, anything without visual proof, "
                "anything that doesn't earn a scroll-stop. Never post just because a commit landed."
            ),
            example_intro_hook=(
                "At [company], we're solving [pain point] for [audience]. "
                "Here's what that looks like."
            ),
        ),
    ),
    StrategyTemplate(
        id="custom",
        name="Custom",
        description="Start from scratch with your own content strategy",
        defaults=StrategyDefaults(
            identity="myself",
            voice_tone="",
            audience="",
            technical_level="intermediate",
            platform_filter="all",
            platform_frequency="moderate",
            post_when="",
            avoid="",
            example_intro_hook="",
        ),
    ),
]

# Strategy template classification for topic scoping.
# Positioning strategies get product topics (seeded from brief).
# Code-driven strategies get implementation topics (created from commit tags).
# Custom and unrecognized strategies default to code-driven.
POSITIONING_TEMPLATES = frozenset({"brand-primary", "product-news"})
CODE_DRIVEN_TEMPLATES = frozenset({"building-public", "technical-deep-dive"})


def get_template(template_id: str) -> StrategyTemplate | None:
    """Look up a template by id."""
    for t in STRATEGY_TEMPLATES:
        if t.id == template_id:
            return t
    return None


def get_template_defaults(strategy_name: str) -> dict | None:
    """Get the default field values for a strategy that was derived from a built-in template.

    Returns None if the strategy doesn't match any template.
    Used by 'strategy reset' CLI command and web UI reset button.
    """
    template = get_template(strategy_name)
    if template is None:
        return None
    d = template.defaults
    return {
        "identity": d.identity,
        "voice_tone": d.voice_tone,
        "audience": d.audience,
        "technical_level": d.technical_level,
        "platform_filter": d.platform_filter,
        "platform_frequency": d.platform_frequency,
        "post_when": d.post_when,
        "avoid": d.avoid,
        "example_intro_hook": d.example_intro_hook,
    }


def templates_to_dicts() -> list[dict[str, Any]]:
    """Serialize templates for API responses."""
    result = []
    for t in STRATEGY_TEMPLATES:
        result.append(
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "defaults": {
                    "identity": t.defaults.identity,
                    "voiceTone": t.defaults.voice_tone,
                    "audience": t.defaults.audience,
                    "technicalLevel": t.defaults.technical_level,
                    "platformFilter": t.defaults.platform_filter,
                    "platformFrequency": t.defaults.platform_frequency,
                    "postWhen": t.defaults.post_when,
                    "avoid": t.defaults.avoid,
                    "exampleIntroHook": t.defaults.example_intro_hook,
                },
            }
        )
    return result
