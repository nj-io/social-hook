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
from social_hook.models.context import ProjectContext
from social_hook.models.core import CommitInfo


class Drafter:
    """Creates draft social media content from evaluation decisions.

    Args:
        client: ClaudeClient configured with the drafter model
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _build_platform_entries(
        platform_configs: list[tuple[str, Any]],
        intro_states: dict[str, dict] | None = None,
    ):
        """Yield (platform_name, config, intro_state) tuples, deduplicated by platform name."""
        seen: set[str] = set()
        states = intro_states or {}
        for pname, pconfig in platform_configs:
            if pname in seen:
                continue
            seen.add(pname)
            yield pname, pconfig, states.get(pname, {})

    def create_draft(
        self,
        decision: Any,
        project_context: ProjectContext,
        commit: CommitInfo,
        db: Any,
        platform: str = "x",
        tier: str = "free",
        vehicle: str | None = None,
        arc_context: dict[str, Any] | None = None,
        config: ContextConfig | None = None,
        platform_config: Optional["ResolvedPlatformConfig"] = None,
        platform_configs: list[tuple[str, Any]] | None = None,
        media_config: Optional["MediaGenerationConfig"] = None,
        media_guidance: dict[str, "MediaToolGuidance"] | None = None,
        referenced_posts: list | None = None,
        platform_introduced: bool | None = None,
        identity: Any | None = None,
        target_post_count: int = 0,
        is_first_post: bool = False,
        first_post_date: str | None = None,
        content_source_context: dict[str, str] | None = None,
        platform_intro_states: dict[str, dict] | None = None,
        project_docs_text: str | None = None,
    ) -> CreateDraftInput:
        """Create a draft post for a post-worthy commit (1-pass, all vehicles).

        Args:
            decision: Evaluation decision (evaluation result)
            project_context: Assembled project state
            commit: Git commit information
            db: Database context for usage logging
            platform: Target platform (x, linkedin)
            tier: Account tier (free, premium, premium_plus)
            vehicle: Content vehicle preference ("single", "thread", "article", or None)
            arc_context: Arc metadata + posts (when post_category == 'arc')
            config: Context config for doc inclusion
            platform_config: Resolved platform configuration
            platform_configs: Multiple platform configs for shared group calls
            media_config: Media generation config (enabled tools)
            media_guidance: Per-tool content guidance
            referenced_posts: Posts to reference in the draft
            platform_introduced: Whether this platform has been introduced
            identity: Resolved IdentityConfig for this platform
            target_post_count: Posts published on this platform
            is_first_post: Whether this is the first post
            first_post_date: Earliest posted_at for this platform
            content_source_context: Resolved content source context
            platform_intro_states: Per-platform intro state for shared groups

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
            referenced_posts=referenced_posts,
            platform_name=platform,
            identity=identity,
            target_post_count=target_post_count,
            is_first_post=is_first_post,
            first_post_date=first_post_date,
            content_source_context=content_source_context,
            project_docs_text=project_docs_text,
        )

        # Build narrative-aware user message
        episode_info = ""
        if hasattr(decision, "post_category") and decision.post_category:
            episode_info += f"Post category: {decision.post_category}. "

        # Include evaluator's angle if available
        angle_info = ""
        if hasattr(decision, "angle") and decision.angle:
            angle_info = f"Angle: {decision.angle}\n"

        # Introduction context for first-ever posts on this platform
        intro_info = ""
        is_intro = (
            platform_introduced is False
            if platform_introduced is not None
            else not project_context.all_introduced
        )
        if is_intro:
            intro_info = (
                "IMPORTANT: This is the FIRST POST for this project on this platform. "
                "The audience has never heard of it. Write a substantial introductory "
                "post that tells the story of what this project is, what "
                "problem it solves, and why it matters. Give the reader enough depth "
                "to understand and care. Don't just summarize "
                "the commit — introduce the project. Use the README and "
                "project documentation in the system prompt for context.\n"
            )

        # Vehicle-specific instructions injected into user message
        vehicle_instruction = ""
        if vehicle == "thread":
            vehicle_instruction = (
                "\nVehicle: THREAD. Write as a thread (minimum 4 parts, numbered 1/, 2/, etc.). "
                "Each part must be ≤280 characters. One beat per part. Structure for visual separation.\n"
            )
        elif vehicle == "article":
            vehicle_instruction = (
                "\nVehicle: ARTICLE. Write long-form structured content. "
                "Use headings, sections, and full paragraphs. No character limits. "
                "Aim for depth and completeness.\n"
            )
        else:
            vehicle_instruction = (
                "\nChoose the best vehicle for this content and set the `vehicle` field accordingly:\n"
                "- `single`: Self-contained post. Best for punchy insights, quick updates, opinions.\n"
                "- `thread`: Multi-part narrative (4+ connected posts, numbered 1/, 2/). Best for walkthroughs, step-by-step, breakdowns.\n"
                "- `article`: Long-form structured content with sections. Best for deep dives, tutorials, comprehensive analyses.\n"
                "Note whether the Angle already defines a preference for the desired vehicle.\n"
            )

        if platform_configs:
            # Multi-platform shared group: build user message with all platform constraints
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            platform_blocks = []
            for i, (pname, pconfig, pintro_state) in enumerate(
                self._build_platform_entries(platform_configs, platform_intro_states), 1
            ):
                pc_tier = pconfig.account_tier or "free"
                char_limit = TIER_CHAR_LIMITS.get(pc_tier, 25000)
                block = f"{i}. {pname} ({pc_tier} tier, {char_limit} char limit)"
                # Platform-specific guidance
                if pname == "x" and pc_tier == "free":
                    block += " — use Format Selection Framework: punchy (<100), detailed (240-280), or thread (4+ beats)"
                elif pname == "x":
                    block += " — use Format Selection Framework, write at whatever length serves the narrative"
                elif pname == "linkedin":
                    block += " — professional tone, 3-5 hashtags, max 3000 chars"
                # Per-platform intro state
                if pintro_state.get("is_first"):
                    block += "\n   First post on this platform. Write an introductory post."
                elif pintro_state.get("post_count"):
                    block += f"\n   {pintro_state['post_count']} previous posts on this platform."
                platform_blocks.append(block)

            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create content for this commit across multiple platforms.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}{episode_info}\n"
                f"Platform variants needed:\n"
                + "\n".join(platform_blocks)
                + "\n\nUse the `variants` array to produce one content variant per platform.\n"
                "Share the same angle/narrative but optimize format and length per platform.\n"
                "Media is shared — set media_type/media_spec once at the top level."
            )
        elif platform_config and platform_config.name == "preview":
            # Generic preview: no platform constraints
            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a social media post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}{episode_info}\n"
                f"This is a preview draft — no platform constraints. "
                f"Write at whatever length and format best serves the content. "
                f"Do not apply character limits or thread formatting."
            )
        elif platform_config:
            # Build platform-specific instructions from resolved config
            pname = platform_config.name
            platform_desc = f"Platform: {pname}"
            if platform_config.priority:
                platform_desc += f" ({platform_config.priority})"
            pc_tier = platform_config.account_tier or "free"
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            char_limit = TIER_CHAR_LIMITS.get(pc_tier, 25000)
            platform_desc += f", {pc_tier} tier, {char_limit} char limit"
            if platform_config.max_length:
                platform_desc += f", max {platform_config.max_length} chars"
            if platform_config.format:
                platform_desc += f", format: {platform_config.format}"
            if platform_config.description:
                platform_desc += f"\nContext: {platform_config.description}"

            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a {pname} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}{episode_info}\n"
                f"{platform_desc}"
            )

            # X free tier specific format guidance (only if no vehicle override)
            if not vehicle:
                if pname == "x" and pc_tier == "free":
                    user_content += (
                        "\nUse the Format Selection Framework: punchy (<100), detailed (240-280), "
                        "or set vehicle='thread' if this needs multiple beats (4+). "
                        "Avoid links in main post."
                    )
                elif pname == "x":
                    user_content += (
                        "\nUse the Format Selection Framework. Write at whatever length serves the narrative. "
                        "Set beat_count for narrative beats. vehicle='thread' for visual separation."
                    )
        elif platform == "x" and tier == "free":
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            char_limit = TIER_CHAR_LIMITS[tier]
            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}"
                f"{episode_info}\n"
                f"Platform: X (free tier). Single post limit: {char_limit} chars. "
            )
            if not vehicle:
                user_content += (
                    "Use the Format Selection Framework: punchy (<100), detailed (240-280), "
                    "or set vehicle='thread' if this needs multiple beats (4+). "
                    "Avoid links in main post."
                )
        elif platform == "x":
            from social_hook.config.yaml import TIER_CHAR_LIMITS

            char_limit = TIER_CHAR_LIMITS[tier]
            user_content = (
                f"{intro_info}{vehicle_instruction}"
                f"Create a {platform} post for this commit.\n"
                f"Commit: {commit.hash[:8]} - {commit.message}\n"
                f"{angle_info}"
                f"{episode_info}\n"
                f"Platform: X ({tier} tier). Single post limit: {char_limit} chars. "
            )
            if not vehicle:
                user_content += (
                    "Use the Format Selection Framework. For multi-beat content, you can write "
                    "a single flowing post OR set vehicle='thread' for visual beat separation. "
                    "Set beat_count to indicate how many narrative beats your content has. "
                    "Write at whatever length serves the narrative."
                )
        else:
            user_content = (
                f"{intro_info}{vehicle_instruction}"
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
