"""Tests for Gatekeeper context enrichment (Chunk 2)."""

from unittest.mock import MagicMock, patch

import pytest

from social_hook.llm.prompts import assemble_gatekeeper_prompt
from social_hook.models import (
    Arc,
    Decision,
    Draft,
    Lifecycle,
    NarrativeDebt,
    Post,
    Project,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_draft():
    return Draft(
        id="draft_gk1",
        project_id="proj_gk1",
        decision_id="dec_gk1",
        platform="x",
        content="Just shipped the new auth module!",
    )


@pytest.fixture
def sample_decisions():
    return [
        Decision(
            id="dec_1",
            project_id="proj_gk1",
            commit_hash="abc12345deadbeef",
            decision="draft",
            reasoning="First commit on registered project with substantial feature",
            commit_message="Add WebSocket gateway for real-time updates",
            angle="Introducing Social Hook",
        ),
        Decision(
            id="dec_2",
            project_id="proj_gk1",
            commit_hash="def67890abcd1234",
            decision="skip",
            reasoning="Minor typo fix, not interesting for audience",
            commit_message="Fixed typo in README",
        ),
    ]


@pytest.fixture
def sample_posts():
    return [
        Post(
            id="post_1",
            draft_id="draft_1",
            project_id="proj_gk1",
            platform="x",
            content="Introducing Social Hook -- a tool that turns dev activity into social posts",
        ),
        Post(
            id="post_2",
            draft_id="draft_2",
            project_id="proj_gk1",
            platform="linkedin",
            content="Building in public: how I automated my social media workflow",
        ),
    ]


@pytest.fixture
def sample_arcs():
    return [
        Arc(
            id="arc_1",
            project_id="proj_gk1",
            theme="Building in public",
            post_count=4,
        ),
    ]


@pytest.fixture
def sample_linked_decision():
    return Decision(
        id="dec_linked",
        project_id="proj_gk1",
        commit_hash="linked123abc",
        decision="draft",
        reasoning="First commit on registered project with substantial WebSocket feature",
        angle="Introducing Social Hook",
    )


# =============================================================================
# Prompt Assembly: New Sections
# =============================================================================


class TestGatekeeperProjectState:
    """Gatekeeper prompt: Project State section."""

    def test_includes_lifecycle_phase(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            lifecycle_phase="build",
        )
        assert "## Project State" in result
        assert "Lifecycle phase: build" in result

    def test_includes_audience_introduced(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            audience_introduced=False,
        )
        assert "Audience introduced: False" in result

    def test_includes_narrative_debt(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            narrative_debt=3,
        )
        assert "Narrative debt: 3" in result

    def test_all_state_fields(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            lifecycle_phase="demo",
            audience_introduced=True,
            narrative_debt=0,
        )
        assert "## Project State" in result
        assert "Lifecycle phase: demo" in result
        assert "Audience introduced: True" in result
        assert "Narrative debt: 0" in result

    def test_no_state_no_section(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
        )
        assert "## Project State" not in result


class TestGatekeeperActiveArcs:
    """Gatekeeper prompt: Active Arcs section."""

    def test_includes_arcs(self, sample_draft, sample_arcs):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            active_arcs=sample_arcs,
        )
        assert "## Active Arcs" in result
        assert '"Building in public" (4 posts)' in result

    def test_no_arcs_no_section(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            active_arcs=[],
        )
        assert "## Active Arcs" not in result

    def test_none_arcs_no_section(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            active_arcs=None,
        )
        assert "## Active Arcs" not in result


class TestGatekeeperRecentDecisions:
    """Gatekeeper prompt: Recent Decisions section."""

    def test_includes_decisions(self, sample_draft, sample_decisions):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            recent_decisions=sample_decisions,
        )
        assert "## Recent Decisions (last 2)" in result
        assert "[draft] abc12345" in result
        assert "[skip] def67890" in result
        assert "Add WebSocket gateway" in result

    def test_no_decisions_no_section(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            recent_decisions=[],
        )
        assert "## Recent Decisions" not in result

    def test_none_decisions_no_section(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            recent_decisions=None,
        )
        assert "## Recent Decisions" not in result


class TestGatekeeperRecentPosts:
    """Gatekeeper prompt: Recent Posts section."""

    def test_includes_posts(self, sample_draft, sample_posts):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            recent_posts=sample_posts,
        )
        assert "## Recent Posts (last 2)" in result
        assert "[x] Introducing Social Hook" in result
        assert "[linkedin] Building in public" in result

    def test_no_posts_no_section(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            recent_posts=[],
        )
        assert "## Recent Posts" not in result


class TestGatekeeperLinkedDecision:
    """Gatekeeper prompt: Linked Decision section."""

    def test_includes_linked_decision(self, sample_draft, sample_linked_decision):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            linked_decision=sample_linked_decision,
        )
        assert "## Linked Decision (for current draft)" in result
        assert "Reasoning: First commit on registered project" in result
        assert "Angle: Introducing Social Hook" in result

    def test_linked_decision_no_angle(self, sample_draft):
        decision = Decision(
            id="dec_no_angle",
            project_id="proj_gk1",
            commit_hash="abc123",
            decision="draft",
            reasoning="Simple feature addition",
        )
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            linked_decision=decision,
        )
        assert "## Linked Decision" in result
        assert "Reasoning: Simple feature addition" in result
        assert "Angle:" not in result

    def test_no_linked_decision_no_section(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
            linked_decision=None,
        )
        assert "## Linked Decision" not in result


# =============================================================================
# Section Ordering
# =============================================================================


class TestGatekeeperSectionOrder:
    """Verify correct ordering of prompt sections."""

    def test_project_state_before_summary(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "test",
            lifecycle_phase="build",
            project_summary="My project summary.",
        )
        state_pos = result.index("## Project State")
        summary_pos = result.index("## Project Summary")
        assert state_pos < summary_pos

    def test_arcs_before_summary(self, sample_draft, sample_arcs):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "test",
            active_arcs=sample_arcs,
            project_summary="My project summary.",
        )
        arcs_pos = result.index("## Active Arcs")
        summary_pos = result.index("## Project Summary")
        assert arcs_pos < summary_pos

    def test_decisions_before_summary(self, sample_draft, sample_decisions):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "test",
            recent_decisions=sample_decisions,
            project_summary="My project summary.",
        )
        decisions_pos = result.index("## Recent Decisions")
        summary_pos = result.index("## Project Summary")
        assert decisions_pos < summary_pos

    def test_linked_decision_before_draft(self, sample_draft, sample_linked_decision):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "test",
            linked_decision=sample_linked_decision,
        )
        linked_pos = result.index("## Linked Decision")
        draft_pos = result.index("## Current Draft")
        assert linked_pos < draft_pos

    def test_snapshot_before_state(self, sample_draft):
        snapshot = "## System Status\n- Projects: test (active)"
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "test",
            system_snapshot=snapshot,
            lifecycle_phase="build",
        )
        snapshot_pos = result.index("## System Status")
        state_pos = result.index("## Project State")
        assert snapshot_pos < state_pos


# =============================================================================
# Backward Compatibility
# =============================================================================


class TestGatekeeperBackwardCompat:
    """Verify existing behavior is preserved when no new params are passed."""

    def test_no_new_params_no_new_sections(self, sample_draft):
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "approve",
        )
        assert "## Project State" not in result
        assert "## Active Arcs" not in result
        assert "## Recent Decisions" not in result
        assert "## Recent Posts" not in result
        assert "## Linked Decision" not in result
        # Original sections still present
        assert "## Current Draft" in result
        assert "## User Message" in result
        assert "approve" in result

    def test_existing_params_still_work(self, sample_draft):
        snapshot = "## System Status\n- Projects: test (active)"
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "what drafts?",
            project_summary="Auth project.",
            system_snapshot=snapshot,
            chat_history="## Recent Chat\n- User: hi",
        )
        assert "## System Status" in result
        assert "## Project Summary" in result
        assert "Auth project." in result
        assert "## Recent Chat" in result
        assert "## Current Draft" in result
        assert "## User Message" in result


# =============================================================================
# Full Enriched Prompt
# =============================================================================


class TestGatekeeperFullEnrichedPrompt:
    """Test with all enrichment parameters provided."""

    def test_all_sections_present(
        self,
        sample_draft,
        sample_decisions,
        sample_posts,
        sample_arcs,
        sample_linked_decision,
    ):
        snapshot = "## System Status\n- Projects: test (active)"
        result = assemble_gatekeeper_prompt(
            "# GK",
            sample_draft,
            "make it shorter",
            project_summary="A dev tool for social media.",
            system_snapshot=snapshot,
            chat_history="## Recent Chat\n- User: hello",
            recent_decisions=sample_decisions,
            recent_posts=sample_posts,
            lifecycle_phase="build",
            active_arcs=sample_arcs,
            narrative_debt=3,
            audience_introduced=False,
            linked_decision=sample_linked_decision,
        )
        assert "## System Status" in result
        assert "## Project State" in result
        assert "## Active Arcs" in result
        assert "## Recent Decisions" in result
        assert "## Recent Posts" in result
        assert "## Project Summary" in result
        assert "## Recent Chat" in result
        assert "## Linked Decision" in result
        assert "## Current Draft" in result
        assert "## User Message" in result
        assert "make it shorter" in result


# =============================================================================
# Gatekeeper.route() Parameter Forwarding
# =============================================================================


class TestGatekeeperRouteForwarding:
    """Verify Gatekeeper.route() forwards new params to prompt assembly."""

    @patch("social_hook.llm.gatekeeper.load_prompt", return_value="# Gatekeeper Prompt")
    @patch("social_hook.llm.gatekeeper.assemble_gatekeeper_prompt")
    def test_route_forwards_enrichment_params(self, mock_assemble, mock_load):
        from social_hook.llm.gatekeeper import Gatekeeper

        # Setup mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.name = "route_action"
        mock_tool_use.input = {
            "action": "handle_directly",
            "operation": "query",
            "params": {"answer": "Hello!"},
        }
        mock_response.content = [mock_tool_use]
        mock_client.complete.return_value = mock_response
        mock_assemble.return_value = "assembled prompt"

        gatekeeper = Gatekeeper(mock_client)

        decisions = [MagicMock()]
        posts = [MagicMock()]
        arcs = [MagicMock()]
        linked = MagicMock()

        gatekeeper.route(
            user_message="hello",
            draft_context={"content": "test", "platform": "x"},
            project_summary="Test project.",
            system_snapshot="## Status\n- ok",
            chat_history="## Chat\n- hi",
            recent_decisions=decisions,
            recent_posts=posts,
            lifecycle_phase="build",
            active_arcs=arcs,
            narrative_debt=5,
            audience_introduced=True,
            linked_decision=linked,
        )

        # Verify assemble_gatekeeper_prompt was called with all params
        mock_assemble.assert_called_once()
        call_kwargs = mock_assemble.call_args
        assert call_kwargs[1]["recent_decisions"] is decisions
        assert call_kwargs[1]["recent_posts"] is posts
        assert call_kwargs[1]["lifecycle_phase"] == "build"
        assert call_kwargs[1]["active_arcs"] is arcs
        assert call_kwargs[1]["narrative_debt"] == 5
        assert call_kwargs[1]["audience_introduced"] is True
        assert call_kwargs[1]["linked_decision"] is linked


# =============================================================================
# handle_message() Integration (DB-backed)
# =============================================================================


class TestHandleMessageEnrichedContext:
    """Verify handle_message fetches enriched context from DB and forwards it."""

    def test_fetches_enriched_context(self, temp_db):
        """Verify that handle_message queries DB for enriched context.

        Uses a real temp DB with real data, mocking only the LLM client
        and messaging adapter.
        """
        from social_hook.db import operations as ops
        from social_hook.messaging.base import InboundMessage

        # Setup test data in DB
        project = Project(id="proj_hm1", name="test-project", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        lifecycle = Lifecycle(project_id="proj_hm1", phase="build", confidence=0.8)
        ops.insert_lifecycle(temp_db, lifecycle)

        arc = Arc(id="arc_hm1", project_id="proj_hm1", theme="Auth arc", post_count=2)
        ops.insert_arc(temp_db, arc)

        debt = NarrativeDebt(project_id="proj_hm1", debt_counter=5)
        ops.insert_narrative_debt(temp_db, debt)

        decision = Decision(
            id="dec_hm1",
            project_id="proj_hm1",
            commit_hash="abc12345",
            decision="draft",
            reasoning="Added auth feature",
            commit_message="Add authentication module",
        )
        ops.insert_decision(temp_db, decision)

        msg = InboundMessage(
            chat_id="123",
            text="hello",
            sender_id="user1",
            sender_name="Test",
            message_id="msg1",
        )

        mock_config = MagicMock()
        mock_config.models.gatekeeper = "anthropic/claude-haiku-4-5"

        # Wrap temp_db to prevent handle_message from closing it (it's shared)
        class NoCloseConn:
            """Proxy that prevents close() from actually closing."""

            def __init__(self, conn):
                self._conn = conn

            def __getattr__(self, name):
                if name == "close":
                    return lambda: None
                return getattr(self._conn, name)

        wrapped_conn = NoCloseConn(temp_db)

        with (
            patch("social_hook.bot.commands._get_conn", return_value=wrapped_conn),
            patch("social_hook.bot.commands.get_chat_draft_context", return_value=None),
            patch("social_hook.bot.buttons.get_pending_edit", return_value=None),
            patch("social_hook.llm.factory.create_client"),
            patch("social_hook.llm.gatekeeper.Gatekeeper") as mock_gk_cls,
        ):
            # Setup gatekeeper mock
            mock_gk = MagicMock()
            mock_route_result = MagicMock()
            mock_route_result.action.value = "handle_directly"
            mock_route_result.operation = None
            mock_gk.route.return_value = mock_route_result
            mock_gk_cls.return_value = mock_gk

            adapter = MagicMock()
            adapter.send_message.return_value = MagicMock(success=True)

            from social_hook.bot.commands import handle_message

            handle_message(msg, adapter, mock_config)

            # Verify gatekeeper.route was called with enrichment params
            mock_gk.route.assert_called_once()
            call_kwargs = mock_gk.route.call_args[1]

            # Verify decisions were fetched (limit=10)
            assert call_kwargs["recent_decisions"] is not None
            assert len(call_kwargs["recent_decisions"]) == 1
            assert call_kwargs["recent_decisions"][0].commit_hash == "abc12345"

            # Verify lifecycle phase extracted
            assert call_kwargs["lifecycle_phase"] == "build"

            # Verify active arcs fetched
            assert call_kwargs["active_arcs"] is not None
            assert len(call_kwargs["active_arcs"]) == 1
            assert call_kwargs["active_arcs"][0].theme == "Auth arc"

            # Verify narrative debt extracted
            assert call_kwargs["narrative_debt"] == 5

            # Verify audience_introduced fetched
            assert call_kwargs["audience_introduced"] is False

            # No draft context → no linked decision
            assert call_kwargs["linked_decision"] is None
