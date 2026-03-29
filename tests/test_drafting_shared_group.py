"""Tests for shared-group drafting pipeline: _pick_lead_platform, _unthread_content, _draft_shared_group, preview_mode."""

from unittest.mock import MagicMock, patch

from social_hook.drafting import (
    _draft_for_resolved_platforms,
    _pick_lead_platform,
    _unthread_content,
)
from social_hook.models.core import CommitInfo

# =============================================================================
# Helpers
# =============================================================================


def _make_rpcfg(max_length=None, account_tier=None, name="x", **kwargs):
    """Build a resolved platform config mock."""
    rpcfg = MagicMock()
    rpcfg.max_length = max_length
    rpcfg.account_tier = account_tier
    rpcfg.name = name
    rpcfg.max_posts_per_day = 3
    rpcfg.min_gap_minutes = 30
    rpcfg.optimal_days = None
    rpcfg.optimal_hours = None
    for k, v in kwargs.items():
        setattr(rpcfg, k, v)
    return rpcfg


def _make_config(platforms=None):
    config = MagicMock()
    config.platforms = platforms or {}
    config.scheduling.timezone = "UTC"
    config.scheduling.max_per_week = 10
    config.scheduling.thread_min_tweets = 4
    config.media_generation.enabled = False
    config.models.drafter = "anthropic/claude-sonnet-4-5"
    config.env = {}
    return config


def _make_context(project):
    ctx = MagicMock()
    ctx.project = project
    ctx.platform_introduced = {"x": True, "linkedin": True}
    ctx.recent_posts = []
    return ctx


def _make_evaluation():
    ev = MagicMock()
    ev.decision = "draft"
    ev.reasoning = "good commit"
    ev.angle = "angle"
    ev.episode_type = "milestone"
    ev.post_category = "standalone"
    ev.media_tool = None
    ev.arc_id = None
    ev.platforms = {}
    ev.episode_tags = ["test"]
    ev.reference_posts = None
    return ev


# =============================================================================
# _pick_lead_platform
# =============================================================================


class TestPickLeadPlatform:
    """Tests for _pick_lead_platform."""

    def test_picks_lowest_max_length(self):
        """Should pick the platform with the lowest max_length."""
        platforms = {
            "linkedin": _make_rpcfg(max_length=3000, name="linkedin"),
            "x": _make_rpcfg(max_length=280, name="x"),
        }
        name, rpcfg = _pick_lead_platform(platforms)
        assert name == "x"

    def test_uses_tier_char_limits_when_no_max_length(self):
        """When max_length is None, tier limits are used."""
        platforms = {
            "linkedin": _make_rpcfg(max_length=3000, name="linkedin"),
            "x": _make_rpcfg(max_length=None, account_tier="free", name="x"),
        }
        name, _ = _pick_lead_platform(platforms)
        # X free tier = 280, LinkedIn = 3000 -> X wins
        assert name == "x"

    def test_tier_limit_combines_with_max_length(self):
        """tier limit should be combined via min() with max_length."""
        platforms = {
            "x": _make_rpcfg(max_length=500, account_tier="free", name="x"),
        }
        name, _ = _pick_lead_platform(platforms)
        assert name == "x"
        # The effective limit is min(500, 280) = 280 from free tier

    def test_all_unconstrained_picks_first(self):
        """When all platforms are unconstrained, pick the first one."""
        platforms = {
            "a": _make_rpcfg(max_length=None, name="a"),
            "b": _make_rpcfg(max_length=None, name="b"),
        }
        name, _ = _pick_lead_platform(platforms)
        assert name == "a"

    def test_single_platform(self):
        """Single platform is always the lead."""
        platforms = {
            "linkedin": _make_rpcfg(max_length=3000, name="linkedin"),
        }
        name, _ = _pick_lead_platform(platforms)
        assert name == "linkedin"


# =============================================================================
# _unthread_content
# =============================================================================


class TestUnthreadContent:
    """Tests for _unthread_content."""

    def test_simple_numbered_thread(self):
        """1/ first\n\n2/ second -> first\n\nsecond"""
        thread = "1/ first\n\n2/ second"
        result = _unthread_content(thread)
        assert result == "first\n\nsecond"

    def test_three_part_thread(self):
        thread = "1/ Alpha\n\n2/ Beta\n\n3/ Gamma"
        result = _unthread_content(thread)
        assert result == "Alpha\n\nBeta\n\nGamma"

    def test_preserves_content_within_tweets(self):
        """Content within tweets should remain intact."""
        thread = "1/ This has multiple lines\nwithin it\n\n2/ And so does this"
        result = _unthread_content(thread)
        assert "This has multiple lines" in result
        assert "And so does this" in result

    def test_single_paragraph_no_markers(self):
        """Content without markers passes through cleanly."""
        content = "Just a single paragraph with no thread markers."
        result = _unthread_content(content)
        assert result == "Just a single paragraph with no thread markers."

    def test_empty_string(self):
        result = _unthread_content("")
        assert result == ""


# =============================================================================
# _draft_shared_group: preview_mode for accountless targets
# =============================================================================


class TestDraftSharedGroupPreviewMode:
    """preview_mode is set for accountless targets in shared group drafting."""

    def test_preview_mode_set_on_draft_object(self):
        """The Draft object gets preview_mode=True when target is in preview_targets."""
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Draft

        # This is the exact logic from _draft_for_resolved_platforms line 349:
        # preview_mode=bool(preview_targets and pname in preview_targets)
        preview_targets = {"x-feed", "linkedin-preview"}
        pname = "x-feed"

        draft = Draft(
            id=generate_id("draft"),
            project_id="proj-1",
            decision_id="dec-1",
            platform="x",
            content="Test content",
            status="draft",
            preview_mode=bool(preview_targets and pname in preview_targets),
        )
        assert draft.preview_mode is True

    def test_preview_mode_false_when_not_in_set(self):
        """Draft gets preview_mode=False when target is not in preview_targets."""
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Draft

        preview_targets = {"linkedin-preview"}
        pname = "x-feed"

        draft = Draft(
            id=generate_id("draft"),
            project_id="proj-1",
            decision_id="dec-1",
            platform="x",
            content="Test content",
            status="draft",
            preview_mode=bool(preview_targets and pname in preview_targets),
        )
        assert draft.preview_mode is False

    def test_preview_mode_false_when_preview_targets_none(self):
        """Draft gets preview_mode=False when preview_targets is None."""
        from social_hook.filesystem import generate_id
        from social_hook.models.core import Draft

        preview_targets = None
        pname = "x-feed"

        draft = Draft(
            id=generate_id("draft"),
            project_id="proj-1",
            decision_id="dec-1",
            platform="x",
            content="Test content",
            status="draft",
            preview_mode=bool(preview_targets and pname in preview_targets),
        )
        assert draft.preview_mode is False


# =============================================================================
# _draft_shared_group: one LLM call, N drafts out
# =============================================================================


class TestDraftSharedGroupOneLLMCall:
    """Shared group makes one LLM call for lead, adapts for remaining."""

    @patch("social_hook.drafting._draft_shared_group")
    @patch("social_hook.llm.factory.create_client")
    def test_shared_group_flag_triggers_shared_path(
        self,
        mock_create_client,
        mock_shared_group,
    ):
        """When shared_group=True and >1 platforms, _draft_shared_group is called."""
        mock_create_client.return_value = MagicMock()
        mock_shared_group.return_value = []

        config = _make_config()
        project = MagicMock(id="proj-1")
        context = _make_context(project)
        evaluation = _make_evaluation()
        commit = CommitInfo(hash="abc", message="test", diff="")
        db = MagicMock()

        platforms = {
            "x": _make_rpcfg(name="x"),
            "linkedin": _make_rpcfg(name="linkedin"),
        }

        _draft_for_resolved_platforms(
            platforms,
            config,
            MagicMock(),  # conn
            db,
            project,
            decision_id="dec-1",
            evaluation=evaluation,
            context=context,
            commit=commit,
            shared_group=True,
        )
        mock_shared_group.assert_called_once()

    @patch("social_hook.drafting._draft_shared_group")
    @patch("social_hook.llm.factory.create_client")
    def test_single_platform_skips_shared_group(
        self,
        mock_create_client,
        mock_shared_group,
    ):
        """With only one platform, shared_group doesn't trigger _draft_shared_group."""
        mock_create_client.return_value = MagicMock()
        mock_shared_group.return_value = []

        config = _make_config()
        project = MagicMock(id="proj-1")
        context = _make_context(project)
        context.platform_introduced = {"x": True}
        evaluation = _make_evaluation()
        commit = CommitInfo(hash="abc", message="test", diff="")
        db = MagicMock()

        platforms = {
            "x": _make_rpcfg(name="x"),
        }

        _draft_for_resolved_platforms(
            platforms,
            config,
            MagicMock(),
            db,
            project,
            decision_id="dec-1",
            evaluation=evaluation,
            context=context,
            commit=commit,
            shared_group=True,
        )
        # With only 1 platform, _draft_shared_group is NOT called
        mock_shared_group.assert_not_called()


# =============================================================================
# draft_for_platforms legacy deprecation warning
# =============================================================================


class TestDraftForPlatformsLegacyWarning:
    """draft_for_platforms() logs a deprecation warning."""

    @patch("social_hook.drafting._resolve_and_filter_platforms", return_value={})
    def test_deprecation_warning_logged(self, mock_resolve, caplog):
        """draft_for_platforms() logs 'Using legacy platform-based drafting'."""
        import logging

        from social_hook.drafting import draft_for_platforms

        config = _make_config()

        with caplog.at_level(logging.WARNING, logger="social_hook.drafting"):
            draft_for_platforms(
                config=config,
                conn=MagicMock(),
                db=MagicMock(),
                project=MagicMock(id="p1"),
                decision_id="d1",
                evaluation=_make_evaluation(),
                context=MagicMock(),
                commit=CommitInfo(hash="abc", message="test", diff=""),
            )

        assert any("legacy platform-based drafting" in r.message.lower() for r in caplog.records)
