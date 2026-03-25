"""Tests for notification grouping per evaluation cycle (Chunk 3)."""

import uuid
from unittest.mock import MagicMock, patch

from social_hook.bot.notifications import (
    format_evaluation_cycle,
    get_cycle_buttons,
)
from social_hook.messaging.base import (
    CallbackEvent,
    OutboundMessage,
    SendResult,
)
from social_hook.models import Draft

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft(
    draft_id: str = "",
    status: str = "draft",
    content: str = "Test content",
    platform: str = "x",
    project_id: str = "proj-1",
    evaluation_cycle_id: str | None = None,
) -> Draft:
    """Create a minimal Draft for testing."""
    return Draft(
        id=draft_id or f"draft-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        decision_id=f"dec-{uuid.uuid4().hex[:8]}",
        platform=platform,
        content=content,
        status=status,
        evaluation_cycle_id=evaluation_cycle_id,
    )


def _make_adapter():
    """Create a mock MessagingAdapter."""
    adapter = MagicMock()
    adapter.send_message.return_value = SendResult(success=True, message_id="msg-1")
    adapter.answer_callback.return_value = True
    return adapter


def _patch_conn(temp_db):
    """Patch _get_conn to return temp_db without closing it.

    The handler calls conn.close() in finally — we need to prevent that
    from closing the fixture connection so we can assert afterward.
    """
    mock_conn = MagicMock(wraps=temp_db)
    mock_conn.close = MagicMock()  # no-op close
    return patch("social_hook.bot.buttons._get_conn", return_value=mock_conn)


# ===========================================================================
# format_evaluation_cycle()
# ===========================================================================


class TestFormatEvaluationCycle:
    def test_includes_all_strategy_outcomes(self):
        outcomes = {
            "building-public": {"action": "draft", "reason": "Topic mature enough"},
            "brand-primary": {"action": "skip", "reason": "No value prop alignment"},
        }
        draft = _make_draft(content="Behind the scenes of the auth rework")
        result = format_evaluation_cycle(
            project_name="social-hook",
            trigger_description='Topic "auth" matured (5 commits)',
            strategy_outcomes=outcomes,
            drafts=[draft],
        )
        assert "building-public" in result
        assert "brand-primary" in result
        assert "draft" in result
        assert "skip" in result
        assert "No value prop alignment" in result

    def test_includes_arc_info_when_present(self):
        outcomes = {
            "building-public": {
                "action": "draft",
                "reason": "Continues the auth narrative",
                "arc_id": "arc-1",
                "arc_theme": "auth rework",
                "arc_post_number": 4,
                "arc_reasoning": "Continues the auth narrative — completes the retry rework",
            },
        }
        draft = _make_draft(content="Behind the scenes")
        result = format_evaluation_cycle(
            project_name="social-hook",
            trigger_description='Topic "auth" matured',
            strategy_outcomes=outcomes,
            drafts=[draft],
        )
        assert 'Arc: "auth rework"' in result
        assert "post 4 of ongoing" in result
        assert "Continues the auth narrative" in result

    def test_includes_queue_actions(self):
        outcomes = {"building-public": {"action": "draft", "reason": "topic ready"}}
        draft = _make_draft()
        result = format_evaluation_cycle(
            project_name="social-hook",
            trigger_description="Topic matured",
            strategy_outcomes=outcomes,
            drafts=[draft],
            queue_actions=[
                {
                    "type": "superseded",
                    "draft_id": "draft_123",
                    "reason": "Config changes post — replaced by broader refactor",
                }
            ],
        )
        assert "Queue actions:" in result
        assert "Superseded draft_123" in result
        assert "replaced by broader refactor" in result

    def test_includes_arc_proposal_with_approve_dismiss(self):
        outcomes = {"building-public": {"action": "draft", "reason": "ready"}}
        draft = _make_draft()
        result = format_evaluation_cycle(
            project_name="social-hook",
            trigger_description="Topic matured",
            strategy_outcomes=outcomes,
            drafts=[draft],
            arc_info={
                "arc_id": "arc-new-1",
                "theme": "auth rework series",
                "parts": 3,
                "reasoning": "Three auth commits form a coherent story",
            },
        )
        assert 'Arc proposed: "auth rework series" (3 parts)' in result
        assert "Three auth commits form a coherent story" in result

    def test_holding_status_emoji(self):
        outcomes = {
            "technical-deep-dive": {"action": "holding", "reason": "Waiting for more commits"},
        }
        result = format_evaluation_cycle(
            project_name="social-hook",
            trigger_description="Topic matured",
            strategy_outcomes=outcomes,
            drafts=[],
        )
        assert "holding" in result
        assert "\u23f8\ufe0f" in result

    def test_skip_status_emoji(self):
        outcomes = {"brand-primary": {"action": "skip", "reason": "Not aligned"}}
        result = format_evaluation_cycle(
            project_name="social-hook",
            trigger_description="Topic matured",
            strategy_outcomes=outcomes,
            drafts=[],
        )
        assert "\u23ed\ufe0f" in result


# ===========================================================================
# get_cycle_buttons()
# ===========================================================================


class TestGetCycleButtons:
    def test_buttons_rendered_correctly(self):
        cycle_id = "cycle-abc123"
        draft = _make_draft(draft_id="draft-xyz")
        buttons = get_cycle_buttons(cycle_id, [draft])
        assert len(buttons) >= 2

        # First row: Expand All + Approve All
        action_row = buttons[0]
        actions = [b.action for b in action_row.buttons]
        assert "cycle_expand" in actions
        assert "cycle_approve" in actions

        # Second row: View buttons per draft
        view_row = buttons[1]
        assert any(b.action == "cycle_view" for b in view_row.buttons)
        assert any(f"{cycle_id}:draft-xyz" in b.payload for b in view_row.buttons)

    def test_arc_proposal_buttons_rendered(self):
        cycle_id = "cycle-abc"
        draft = _make_draft()
        arc_info = {"arc_id": "arc-new-1", "theme": "auth", "parts": 3, "reasoning": ""}
        buttons = get_cycle_buttons(cycle_id, [draft], arc_info=arc_info)

        # Arc buttons should be first row
        arc_row = buttons[0]
        arc_actions = [b.action for b in arc_row.buttons]
        assert "arc_approve" in arc_actions
        assert "arc_dismiss" in arc_actions
        assert any(b.payload == "arc-new-1" for b in arc_row.buttons)


# ===========================================================================
# notify_evaluation_cycle()
# ===========================================================================


class TestNotifyEvaluationCycle:
    def test_dry_run_skips_send(self):
        from social_hook.notifications import notify_evaluation_cycle

        config = MagicMock()
        # Should not raise or send anything
        notify_evaluation_cycle(
            config=config,
            project_name="test",
            project_id="proj-1",
            cycle_id="cycle-1",
            trigger_description="test",
            strategy_outcomes={"s1": {"action": "skip", "reason": ""}},
            drafts=[],
            dry_run=True,
        )

    @patch("social_hook.notifications.broadcast_notification")
    def test_sends_notification(self, mock_broadcast):
        from social_hook.notifications import notify_evaluation_cycle

        config = MagicMock()
        draft = _make_draft(content="Test draft content")
        notify_evaluation_cycle(
            config=config,
            project_name="social-hook",
            project_id="proj-1",
            cycle_id="cycle-1",
            trigger_description='Topic "auth" matured',
            strategy_outcomes={
                "building-public": {"action": "draft", "reason": "Topic ready"},
            },
            drafts=[draft],
        )
        mock_broadcast.assert_called_once()
        args = mock_broadcast.call_args
        msg = args[0][1]  # second positional arg is OutboundMessage
        assert isinstance(msg, OutboundMessage)
        assert "building-public" in msg.text
        assert len(msg.buttons) > 0


# ===========================================================================
# Backward compat: legacy config → existing notification format
# ===========================================================================


class TestBackwardCompat:
    def test_legacy_notify_draft_review_unchanged(self):
        """Legacy format_draft_review still works and is not broken."""
        from social_hook.bot.notifications import format_draft_review

        result = format_draft_review(
            project_name="test-project",
            commit_hash="abc12345",
            commit_message="fix: something",
            platform="x",
            content="Test content here",
            draft_id="draft-123",
        )
        assert "New draft ready for review" in result
        assert "test-project" in result
        assert "abc12345" in result


# ===========================================================================
# Callback handlers
# ===========================================================================


class TestHandleCycleExpand:
    def test_expand_shows_all_drafts(self, temp_db):
        from social_hook.bot.buttons import handle_cycle_expand
        from social_hook.db import operations as ops

        # Insert a project and decision first
        from social_hook.models import Decision, Project

        project = Project(id="proj-1", name="test-proj", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)
        decision = Decision(
            id="dec-1",
            project_id="proj-1",
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(temp_db, decision)

        # Insert drafts with cycle_id
        cycle_id = "cycle-expand-1"
        d1 = _make_draft(
            draft_id="d1",
            content="Draft one",
            project_id="proj-1",
            evaluation_cycle_id=cycle_id,
        )
        d2 = _make_draft(
            draft_id="d2",
            content="Draft two",
            project_id="proj-1",
            evaluation_cycle_id=cycle_id,
        )
        d1.decision_id = "dec-1"
        d2.decision_id = "dec-1"
        ops.insert_draft(temp_db, d1)
        ops.insert_draft(temp_db, d2)

        adapter = _make_adapter()
        with _patch_conn(temp_db):
            handle_cycle_expand(adapter, "chat-1", "cb-1", cycle_id, None)

        # Should have sent expand message
        adapter.send_message.assert_called()
        sent_msg = (
            adapter.send_message.call_args[1].get("message") or adapter.send_message.call_args[0][1]
        )
        assert "Draft one" in sent_msg.text
        assert "Draft two" in sent_msg.text

    def test_expand_empty_cycle(self, temp_db):
        from social_hook.bot.buttons import handle_cycle_expand

        adapter = _make_adapter()
        with _patch_conn(temp_db):
            handle_cycle_expand(adapter, "chat-1", "cb-1", "no-such-cycle", None)

        adapter.send_message.assert_called()
        sent_msg = adapter.send_message.call_args[0][1]
        assert "No drafts found" in sent_msg.text


class TestHandleCycleApprove:
    def test_approves_editable_drafts(self, temp_db):
        from social_hook.bot.buttons import handle_cycle_approve
        from social_hook.db import operations as ops
        from social_hook.models import Decision, Project

        project = Project(id="proj-1", name="test-proj", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)
        decision = Decision(
            id="dec-1",
            project_id="proj-1",
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(temp_db, decision)

        cycle_id = "cycle-approve-1"
        d1 = _make_draft(
            draft_id="d-approve-1",
            status="draft",
            project_id="proj-1",
            evaluation_cycle_id=cycle_id,
        )
        d1.decision_id = "dec-1"
        ops.insert_draft(temp_db, d1)

        adapter = _make_adapter()
        with _patch_conn(temp_db):
            handle_cycle_approve(adapter, "chat-1", "cb-1", cycle_id, None)

        # Verify draft was approved
        updated = ops.get_draft(temp_db, "d-approve-1")
        assert updated.status == "approved"

        # Check response message
        sent_msg = adapter.send_message.call_args[0][1]
        assert "Approved 1" in sent_msg.text

    def test_mixed_statuses(self, temp_db):
        """Approve All with mixed statuses: approves editable, skips terminal, reports count."""
        from social_hook.bot.buttons import handle_cycle_approve
        from social_hook.db import operations as ops
        from social_hook.models import Decision, Project

        project = Project(id="proj-1", name="test-proj", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)
        decision = Decision(
            id="dec-1",
            project_id="proj-1",
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(temp_db, decision)

        cycle_id = "cycle-mixed-1"

        # Editable draft
        d1 = _make_draft(
            draft_id="d-edit-1",
            status="draft",
            project_id="proj-1",
            evaluation_cycle_id=cycle_id,
        )
        d1.decision_id = "dec-1"
        ops.insert_draft(temp_db, d1)

        # Already approved draft
        d2 = _make_draft(
            draft_id="d-already-1",
            status="approved",
            project_id="proj-1",
            evaluation_cycle_id=cycle_id,
        )
        d2.decision_id = "dec-1"
        ops.insert_draft(temp_db, d2)

        # Terminal (posted) draft
        d3 = _make_draft(
            draft_id="d-posted-1",
            status="posted",
            project_id="proj-1",
            evaluation_cycle_id=cycle_id,
        )
        d3.decision_id = "dec-1"
        ops.insert_draft(temp_db, d3)

        adapter = _make_adapter()
        with _patch_conn(temp_db):
            handle_cycle_approve(adapter, "chat-1", "cb-1", cycle_id, None)

        sent_msg = adapter.send_message.call_args[0][1]
        assert "Approved 1" in sent_msg.text
        assert "Already processed: 1" in sent_msg.text
        assert "Skipped (terminal): 1" in sent_msg.text


class TestHandleCycleView:
    def test_view_single_draft(self, temp_db):
        from social_hook.bot.buttons import handle_cycle_view
        from social_hook.db import operations as ops
        from social_hook.models import Decision, Project

        project = Project(id="proj-1", name="test-proj", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)
        decision = Decision(
            id="dec-1",
            project_id="proj-1",
            commit_hash="abc123",
            decision="draft",
            reasoning="test",
        )
        ops.insert_decision(temp_db, decision)

        d1 = _make_draft(
            draft_id="d-view-1",
            content="Viewable content",
            project_id="proj-1",
        )
        d1.decision_id = "dec-1"
        ops.insert_draft(temp_db, d1)

        adapter = _make_adapter()
        payload = "cycle-1:d-view-1"
        with _patch_conn(temp_db):
            handle_cycle_view(adapter, "chat-1", "cb-1", payload, None)

        sent_msg = adapter.send_message.call_args[0][1]
        assert "Viewable content" in sent_msg.text
        assert len(sent_msg.buttons) > 0  # Should have review buttons


class TestHandleArcApprove:
    def test_arc_approve_sets_active(self, temp_db):
        from social_hook.bot.buttons import handle_arc_approve
        from social_hook.db import operations as ops
        from social_hook.models import Arc, Project

        project = Project(id="proj-1", name="test-proj", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        arc = Arc(
            id="arc-approve-1",
            project_id="proj-1",
            theme="auth rework",
            status="proposed",
        )
        ops.insert_arc(temp_db, arc)

        adapter = _make_adapter()
        with _patch_conn(temp_db):
            handle_arc_approve(adapter, "chat-1", "cb-1", "arc-approve-1", None)

        updated = ops.get_arc(temp_db, "arc-approve-1")
        assert updated.status == "active"
        adapter.answer_callback.assert_called_with("cb-1", "Arc approved")


class TestHandleArcDismiss:
    def test_arc_dismiss_sets_abandoned(self, temp_db):
        from social_hook.bot.buttons import handle_arc_dismiss
        from social_hook.db import operations as ops
        from social_hook.models import Arc, Project

        project = Project(id="proj-1", name="test-proj", repo_path="/tmp/test")
        ops.insert_project(temp_db, project)

        arc = Arc(
            id="arc-dismiss-1",
            project_id="proj-1",
            theme="bad arc",
            status="proposed",
        )
        ops.insert_arc(temp_db, arc)

        adapter = _make_adapter()
        with _patch_conn(temp_db):
            handle_arc_dismiss(adapter, "chat-1", "cb-1", "arc-dismiss-1", None)

        updated = ops.get_arc(temp_db, "arc-dismiss-1")
        assert updated.status == "abandoned"
        adapter.answer_callback.assert_called_with("cb-1", "Arc dismissed")


class TestHandleCallbackRouting:
    """Verify new actions are routed through handle_callback."""

    def test_cycle_expand_routed(self):
        from social_hook.bot.buttons import handle_callback

        event = CallbackEvent(
            chat_id="chat-1",
            callback_id="cb-1",
            action="cycle_expand",
            payload="cycle-123",
        )
        adapter = _make_adapter()
        with patch("social_hook.bot.buttons.handle_cycle_expand") as mock_handler:
            handle_callback(event, adapter, config=None)
            mock_handler.assert_called_once()

    def test_arc_approve_routed(self):
        from social_hook.bot.buttons import handle_callback

        event = CallbackEvent(
            chat_id="chat-1",
            callback_id="cb-1",
            action="arc_approve",
            payload="arc-123",
        )
        adapter = _make_adapter()
        with patch("social_hook.bot.buttons.handle_arc_approve") as mock_handler:
            handle_callback(event, adapter, config=None)
            mock_handler.assert_called_once()

    def test_arc_dismiss_routed(self):
        from social_hook.bot.buttons import handle_callback

        event = CallbackEvent(
            chat_id="chat-1",
            callback_id="cb-1",
            action="arc_dismiss",
            payload="arc-123",
        )
        adapter = _make_adapter()
        with patch("social_hook.bot.buttons.handle_arc_dismiss") as mock_handler:
            handle_callback(event, adapter, config=None)
            mock_handler.assert_called_once()
