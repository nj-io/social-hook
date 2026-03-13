"""Tests for drafter platform-agnostic instructions."""

from unittest.mock import MagicMock, patch

from social_hook.config.platforms import ResolvedPlatformConfig
from social_hook.llm.drafter import Drafter
from social_hook.models import CommitInfo


def _make_drafter_mocks():
    """Build common mocks for drafter tests."""
    client = MagicMock()

    # Mock response with tool_use content
    tool_content = MagicMock()
    tool_content.type = "tool_use"
    tool_content.name = "create_draft"
    tool_content.input = {
        "content": "Great feature!",
        "platform": "x",
        "reasoning": "Short and punchy",
    }
    response = MagicMock()
    response.content = [tool_content]
    client.complete.return_value = response

    commit = CommitInfo(
        hash="abc12345",
        message="Add feature",
        diff="+ new code",
    )

    project_context = MagicMock()
    project_context.recent_posts = []
    project_context.platform_introduced = {"x": True}
    project_context.all_introduced = True
    project_context.project.id = "p1"
    project_context.project.repo_path = None
    project_context.social_context = None
    project_context.memories = []
    project_context.context_notes = []
    project_context.session_narratives = []
    project_context.project_summary = None
    project_context.milestone_summaries = []
    project_context.lifecycle = None
    project_context.active_arcs = []
    project_context.narrative_debt = 0
    project_context.pending_drafts = []
    project_context.recent_decisions = []

    decision = MagicMock()
    decision.decision = "draft"
    decision.reasoning = "Good commit"
    decision.angle = "feature"
    decision.episode_type = "milestone"
    decision.post_category = "arc"
    decision.include_project_docs = False

    db = MagicMock()

    return client, commit, project_context, decision, db


class TestDrafterPlatformConfig:
    """Tests for platform_config parameter in create_draft."""

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_platform_config_instructions(self, mock_prompt):
        """Platform config info appears in user message."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        drafter = Drafter(client)

        rpc = ResolvedPlatformConfig(
            name="x",
            enabled=True,
            priority="primary",
            type="builtin",
            account_tier="free",
            description=None,
            format=None,
            max_length=None,
            filter="all",
            frequency="high",
            max_posts_per_day=3,
            min_gap_minutes=30,
            optimal_days=["Tue"],
            optimal_hours=[9],
        )

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="x",
            platform_config=rpc,
        )

        call_args = client.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "Platform: x (primary)" in user_msg
        assert "free tier" in user_msg

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_custom_platform_description(self, mock_prompt):
        """Custom platform description is included."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        drafter = Drafter(client)

        rpc = ResolvedPlatformConfig(
            name="blog",
            enabled=True,
            priority="secondary",
            type="custom",
            account_tier=None,
            description="My tech blog about ML",
            format="article",
            max_length=5000,
            filter="notable",
            frequency="moderate",
            max_posts_per_day=1,
            min_gap_minutes=120,
            optimal_days=["Tue"],
            optimal_hours=[9],
        )

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="blog",
            platform_config=rpc,
        )

        call_args = client.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "blog" in user_msg
        assert "My tech blog about ML" in user_msg
        assert "article" in user_msg
        assert "max 5000 chars" in user_msg

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_x_free_tier_with_config(self, mock_prompt):
        """X free tier instructions via platform_config."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        drafter = Drafter(client)

        rpc = ResolvedPlatformConfig(
            name="x",
            enabled=True,
            priority="primary",
            type="builtin",
            account_tier="free",
            description=None,
            format=None,
            max_length=None,
            filter="all",
            frequency="high",
            max_posts_per_day=3,
            min_gap_minutes=30,
            optimal_days=["Tue"],
            optimal_hours=[9],
        )

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="x",
            platform_config=rpc,
        )

        call_args = client.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "Format Selection Framework" in user_msg
        assert "Avoid links" in user_msg

    @patch("social_hook.llm.drafter.load_prompt", return_value="drafter prompt")
    def test_backward_compat_no_config(self, mock_prompt):
        """platform_config=None uses old logic (backward compat)."""
        client, commit, ctx, decision, db = _make_drafter_mocks()
        drafter = Drafter(client)

        drafter.create_draft(
            decision,
            ctx,
            commit,
            db,
            platform="x",
            tier="free",
        )

        call_args = client.complete.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]
        assert "Format Selection Framework" in user_msg
        assert "280 chars" in user_msg
