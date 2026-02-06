"""Drafter agent: creates social media content (T14)."""

from typing import Any, Optional

from social_hook.db import operations as ops
from social_hook.llm.client import ClaudeClient
from social_hook.llm.prompts import assemble_drafter_prompt, load_prompt
from social_hook.llm.schemas import CreateDraftInput, extract_tool_call
from social_hook.models import CommitInfo, ProjectContext


class Drafter:
    """Creates draft social media content from evaluation decisions.

    Args:
        client: ClaudeClient configured with the drafter model
    """

    def __init__(self, client: ClaudeClient) -> None:
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
        )

        user_content = (
            f"Create a {platform} post for this commit.\n"
            f"Commit: {commit.hash[:8]} - {commit.message}\n"
        )
        if tier != "premium_plus":
            user_content += (
                f"Account tier: {tier}. "
            )
            if platform == "x" and tier == "free":
                user_content += "Avoid links in main post (severe algorithm penalty)."

        response = self.client.complete(
            messages=[{"role": "user", "content": user_content}],
            tools=[CreateDraftInput.to_tool_schema()],
            system=system,
            operation_type="draft",
            db=db,
            project_id=project_context.project.id,
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
            f"Each tweet must be under 280 characters."
        )

        response = self.client.complete(
            messages=[{"role": "user", "content": user_content}],
            tools=[CreateDraftInput.to_tool_schema()],
            system=system,
            operation_type="draft_thread",
            db=db,
            project_id=project_context.project.id,
        )

        tool_input = extract_tool_call(response, "create_draft")
        return CreateDraftInput.validate(tool_input)
