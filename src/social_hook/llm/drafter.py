"""Drafter agent: creates social media content (T14)."""

from typing import Any, Optional

from social_hook.config.project import ContextConfig
from social_hook.db import operations as ops
from social_hook.llm.base import LLMClient
from social_hook.llm.prompts import assemble_drafter_prompt, load_prompt
from social_hook.llm.schemas import CreateDraftInput, extract_tool_call
from social_hook.models import CommitInfo, ProjectContext


class Drafter:
    """Creates draft social media content from evaluation decisions.

    Args:
        client: ClaudeClient configured with the drafter model
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def create_draft(
        self,
        decision: Any,
        project_context: ProjectContext,
        commit: CommitInfo,
        db: Any,
        platform: str = "x",
        tier: str = "free",
        arc_context: Optional[dict[str, Any]] = None,
        config: Optional[ContextConfig] = None,
    ) -> CreateDraftInput:
        """Create a draft post for a post-worthy commit.

        Args:
            decision: Evaluation decision (LogDecisionInput)
            project_context: Assembled project state
            commit: Git commit information
            db: Database context for usage logging
            platform: Target platform (x, linkedin)
            tier: Account tier (free, premium, premium_plus)
            arc_context: Arc metadata + posts (when post_category == 'arc')

        Returns:
            Validated CreateDraftInput from the LLM
        """
        prompt = load_prompt("drafter")

        recent_posts = project_context.recent_posts

        system = assemble_drafter_prompt(
            prompt, decision, project_context,
            recent_posts, commit, arc_context=arc_context,
            config=config,
        )

        # Build narrative-aware user message
        episode_info = ""
        if hasattr(decision, "episode_type") and decision.episode_type:
            episode_info += f"Episode type: {decision.episode_type}. "
        if hasattr(decision, "post_category") and decision.post_category:
            episode_info += f"Post category: {decision.post_category}. "

        # Include evaluator's angle if available
        angle_info = ""
        if hasattr(decision, "angle") and decision.angle:
            angle_info = f"Angle: {decision.angle}\n"

        # Introduction context for first-ever posts
        intro_info = ""
        if not project_context.audience_introduced:
            intro_info = (
                "IMPORTANT: This is the FIRST POST for this project. "
                "The audience has never heard of it. Write an introductory "
                "post that tells the story of what this project is, what "
                "problem it solves, and why it matters. Don't just summarize "
                "the commit — introduce the project. Use the README and "
                "project documentation in the system prompt for context.\n"
            )

        if platform == "x" and tier == "free":
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            char_limit = TIER_CHAR_LIMITS[tier]
            user_content = (
                f"{intro_info}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}"
                f"{episode_info}\n"
                f"Platform: X (free tier). Single post limit: {char_limit} chars. "
                f"Use the Format Selection Framework: punchy (<100), detailed (240-280), "
                f"or set format_hint='thread' if this needs multiple beats (4+). "
                f"Avoid links in main post."
            )
        elif platform == "x":
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            char_limit = TIER_CHAR_LIMITS[tier]
            user_content = (
                f"{intro_info}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}"
                f"{episode_info}\n"
                f"Platform: X ({tier} tier). Single post limit: {char_limit} chars. "
                f"Use the Format Selection Framework. For multi-beat content, you can write "
                f"a single flowing post OR set format_hint='thread' for visual beat separation. "
                f"Set beat_count to indicate how many narrative beats your content has. "
                f"Write at whatever length serves the narrative."
            )
        else:
            user_content = (
                f"{intro_info}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}"
                f"{episode_info}"
            )

        response = self.client.complete(
            messages=[{"role": "user", "content": user_content}],
            tools=[CreateDraftInput.to_tool_schema()],
            system=system,
            operation_type="draft",
            db=db,
            project_id=project_context.project.id,
            commit_hash=commit.hash,
        )

        tool_input = extract_tool_call(response, "create_draft")
        return CreateDraftInput.validate(tool_input)

    def create_thread(
        self,
        decision: Any,
        project_context: ProjectContext,
        commit: CommitInfo,
        db: Any,
        platform: str = "x",
    ) -> CreateDraftInput:
        """Create a thread (>= 4 tweets) for a post-worthy commit.

        Args:
            decision: Evaluation decision
            project_context: Assembled project state
            commit: Git commit information
            db: Database context for usage logging
            platform: Target platform

        Returns:
            Validated CreateDraftInput with thread content
        """
        prompt = load_prompt("drafter")

        system = assemble_drafter_prompt(
            prompt, decision, project_context,
            project_context.recent_posts, commit,
        )

        user_content = (
            f"Create a {platform} thread (minimum 4 tweets, numbered 1/, 2/, etc.) "
            f"for this commit.\n"
            f"Commit: {commit.hash[:8]} - {commit.message}\n"
            f"Each tweet must be ≤280 characters. "
            f"One beat per tweet. Structure for visual separation."
        )

        response = self.client.complete(
            messages=[{"role": "user", "content": user_content}],
            tools=[CreateDraftInput.to_tool_schema()],
            system=system,
            operation_type="draft_thread",
            db=db,
            project_id=project_context.project.id,
            commit_hash=commit.hash,
        )

        tool_input = extract_tool_call(response, "create_draft")
        return CreateDraftInput.validate(tool_input)
