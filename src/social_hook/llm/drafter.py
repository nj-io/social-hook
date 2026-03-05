"""Drafter agent: creates social media content (T14)."""

from typing import TYPE_CHECKING, Any, Optional

from social_hook.config.project import ContextConfig

if TYPE_CHECKING:
    from social_hook.config.platforms import ResolvedPlatformConfig
    from social_hook.config.project import MediaToolGuidance
    from social_hook.config.yaml import MediaGenerationConfig
from social_hook.llm._usage_logger import log_usage
from social_hook.llm.base import LLMClient, extract_tool_call
from social_hook.llm.prompts import assemble_drafter_prompt, load_prompt
from social_hook.llm.schemas import CreateDraftInput
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
        arc_context: dict[str, Any] | None = None,
        config: ContextConfig | None = None,
        platform_config: Optional["ResolvedPlatformConfig"] = None,
        media_config: Optional["MediaGenerationConfig"] = None,
        media_guidance: dict[str, "MediaToolGuidance"] | None = None,
    ) -> CreateDraftInput:
        """Create a draft post for a post-worthy commit.

        Args:
            decision: Evaluation decision (evaluation result)
            project_context: Assembled project state
            commit: Git commit information
            db: Database context for usage logging
            platform: Target platform (x, linkedin)
            tier: Account tier (free, premium, premium_plus)
            arc_context: Arc metadata + posts (when post_category == 'arc')
            config: Context config for doc inclusion
            platform_config: Resolved platform configuration (when provided,
                builds platform-specific instructions from config)
            media_config: Media generation config (enabled tools)
            media_guidance: Per-tool content guidance

        Returns:
            Validated CreateDraftInput from the LLM
        """
        prompt = load_prompt("drafter")

        recent_posts = project_context.recent_posts

        system = assemble_drafter_prompt(
            prompt,
            decision,
            project_context,
            recent_posts,
            commit,
            arc_context=arc_context,
            config=config,
            media_config=media_config,
            media_guidance=media_guidance,
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

        if platform_config:
            # Build platform-specific instructions from resolved config
            platform_desc = f"Platform: {platform_config.name}"
            if platform_config.priority:
                platform_desc += f" ({platform_config.priority})"
            pc_tier = platform_config.account_tier or "free"
            if platform_config.account_tier:
                from social_hook.config.yaml import TIER_CHAR_LIMITS

                char_limit = TIER_CHAR_LIMITS.get(pc_tier, 25000)
                platform_desc += f", {pc_tier} tier, {char_limit} char limit"
            elif platform_config.max_length:
                platform_desc += f", max {platform_config.max_length} chars"
            if platform_config.format:
                platform_desc += f", format: {platform_config.format}"
            if platform_config.description:
                platform_desc += f"\nContext: {platform_config.description}"

            user_content = (
                f"{intro_info}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}{episode_info}\n"
                f"{platform_desc}"
            )

            # X free tier specific format guidance
            if platform == "x" and pc_tier == "free":
                user_content += (
                    "\nUse the Format Selection Framework: punchy (<100), detailed (240-280), "
                    "or set format_hint='thread' if this needs multiple beats (4+). "
                    "Avoid links in main post."
                )
            elif platform == "x":
                user_content += (
                    "\nUse the Format Selection Framework. Write at whatever length serves the narrative. "
                    "Set beat_count for narrative beats. format_hint='thread' for visual separation."
                )
        elif platform == "x" and tier == "free":
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
        )
        log_usage(
            db,
            "draft",
            getattr(self.client, "full_id", "unknown"),
            response.usage,
            project_context.project.id,
            commit.hash,
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
        media_config: Optional["MediaGenerationConfig"] = None,
        media_guidance: dict[str, "MediaToolGuidance"] | None = None,
    ) -> CreateDraftInput:
        """Create a thread (>= 4 tweets) for a post-worthy commit.

        Args:
            decision: Evaluation decision
            project_context: Assembled project state
            commit: Git commit information
            db: Database context for usage logging
            platform: Target platform
            media_config: Media generation config (enabled tools)
            media_guidance: Per-tool content guidance

        Returns:
            Validated CreateDraftInput with thread content
        """
        prompt = load_prompt("drafter")

        system = assemble_drafter_prompt(
            prompt,
            decision,
            project_context,
            project_context.recent_posts,
            commit,
            media_config=media_config,
            media_guidance=media_guidance,
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
        )
        log_usage(
            db,
            "draft_thread",
            getattr(self.client, "full_id", "unknown"),
            response.usage,
            project_context.project.id,
            commit.hash,
        )

        tool_input = extract_tool_call(response, "create_draft")
        return CreateDraftInput.validate(tool_input)
