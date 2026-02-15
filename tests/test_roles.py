"""Tests for LLM agent roles: Evaluator, Drafter, Gatekeeper, Expert (T13-T16)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_hook.errors import MalformedResponseError
from social_hook.llm.base import LLMClient
from social_hook.llm.drafter import Drafter
from social_hook.llm.evaluator import Evaluator
from social_hook.llm.expert import Expert
from social_hook.llm.gatekeeper import Gatekeeper
from social_hook.llm.schemas import (
    CreateDraftInput,
    ExpertResponseInput,
    LogDecisionInput,
    RouteActionInput,
)
from social_hook.models import (
    Arc,
    CommitInfo,
    Decision,
    Draft,
    Lifecycle,
    Post,
    Project,
    ProjectContext,
)


# =============================================================================
# Helpers
# =============================================================================


def _mock_response(tool_name: str, tool_input: dict):
    """Create a mock Claude API response with a tool call."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input

    response = MagicMock()
    response.content = [tool_block]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    response.usage.cache_read_input_tokens = 0
    response.usage.cache_creation_input_tokens = 0
    return response


def _mock_response_no_tool():
    """Create a mock response with text only (no tool call)."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I couldn't make a decision."

    response = MagicMock()
    response.content = [text_block]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    response.usage.cache_read_input_tokens = 0
    response.usage.cache_creation_input_tokens = 0
    return response


@pytest.fixture
def mock_client():
    """Create a mocked ClaudeClient."""
    client = MagicMock(spec=LLMClient)
    client.model = "claude-opus-4-5"
    return client


@pytest.fixture
def mock_db():
    """Create a mock DryRunContext.

    Note: Can't use spec=DryRunContext because __getattr__ delegation
    means MagicMock can't discover dynamic methods. We validate the
    interface separately in TestMockDbInterface.
    """
    db = MagicMock()
    db.get_summary_freshness.return_value = {
        "commits_since_summary": 5,
        "days_since_summary": 3,
    }
    return db


@pytest.fixture
def sample_commit():
    return CommitInfo(
        hash="abc123def456",
        message="Add user authentication",
        diff="+ def auth(): pass",
        files_changed=["src/auth.py"],
        insertions=20,
        deletions=5,
    )


@pytest.fixture
def sample_context():
    project = Project(id="proj_test1", name="test", repo_path="/tmp/test")
    return ProjectContext(
        project=project,
        social_context="Technical voice.",
        lifecycle=Lifecycle(project_id="proj_test1", phase="build", confidence=0.8),
        active_arcs=[],
        narrative_debt=0,
        audience_introduced=True,
        pending_drafts=[],
        recent_decisions=[],
        recent_posts=[],
        project_summary="A test project.",
        memories=[],
    )


@pytest.fixture
def prompts_dir(temp_dir):
    """Create temp prompts directory with all prompt files."""
    prompts = temp_dir / ".social-hook" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "evaluator.md").write_text("# Evaluator\nEvaluate commits.")
    (prompts / "drafter.md").write_text("# Drafter\nCreate content.")
    (prompts / "gatekeeper.md").write_text("# Gatekeeper\nRoute messages.")
    return prompts


# =============================================================================
# T13: Evaluator Tests
# =============================================================================


class TestEvaluator:
    """T13: Evaluator agent."""

    def test_evaluate_post_worthy(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("log_decision", {
            "decision": "post_worthy",
            "reasoning": "Major new feature",
            "episode_type": "milestone",
            "post_category": "opportunistic",
            "media_tool": "ray_so",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            evaluator = Evaluator(mock_client)
            result = evaluator.evaluate(sample_commit, sample_context, mock_db)

        assert isinstance(result, LogDecisionInput)
        assert result.decision.value == "post_worthy"
        assert result.episode_type.value == "milestone"
        assert result.post_category.value == "opportunistic"
        mock_client.complete.assert_called_once()

    def test_evaluate_not_post_worthy(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("log_decision", {
            "decision": "not_post_worthy",
            "reasoning": "Minor formatting fix",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            evaluator = Evaluator(mock_client)
            result = evaluator.evaluate(sample_commit, sample_context, mock_db)

        assert result.decision.value == "not_post_worthy"
        assert "formatting" in result.reasoning

    def test_evaluate_consolidate(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("log_decision", {
            "decision": "consolidate",
            "reasoning": "Part of a larger auth change",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            evaluator = Evaluator(mock_client)
            result = evaluator.evaluate(sample_commit, sample_context, mock_db)

        assert result.decision.value == "consolidate"

    def test_evaluate_no_tool_call_raises(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response_no_tool()

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            evaluator = Evaluator(mock_client)
            with pytest.raises(MalformedResponseError):
                evaluator.evaluate(sample_commit, sample_context, mock_db)

    def test_evaluate_invalid_response_raises(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("log_decision", {
            "decision": "invalid_value",
            "reasoning": "test",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            evaluator = Evaluator(mock_client)
            with pytest.raises(MalformedResponseError):
                evaluator.evaluate(sample_commit, sample_context, mock_db)

    def test_evaluate_passes_usage_tracking(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("log_decision", {
            "decision": "post_worthy",
            "reasoning": "Test",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            evaluator = Evaluator(mock_client)
            evaluator.evaluate(sample_commit, sample_context, mock_db)

        call_kwargs = mock_client.complete.call_args[1]
        assert call_kwargs["operation_type"] == "evaluate"
        assert call_kwargs["project_id"] == "proj_test1"

    def test_evaluate_includes_freshness_hint(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        """T20a: Evaluator includes summary freshness in user message."""
        mock_db.get_summary_freshness.return_value = {
            "commits_since_summary": 12,
            "days_since_summary": 7,
        }
        mock_client.complete.return_value = _mock_response("log_decision", {
            "decision": "post_worthy",
            "reasoning": "Test",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            evaluator = Evaluator(mock_client)
            evaluator.evaluate(sample_commit, sample_context, mock_db)

        call_kwargs = mock_client.complete.call_args[1]
        user_msg = call_kwargs["messages"][0]["content"]
        assert "12 commits since last update" in user_msg
        assert "7 days since update" in user_msg

    def test_evaluate_no_freshness_when_unavailable(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        """T20a: Evaluator works without freshness data."""
        mock_db.get_summary_freshness.return_value = None
        mock_client.complete.return_value = _mock_response("log_decision", {
            "decision": "post_worthy",
            "reasoning": "Test",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            evaluator = Evaluator(mock_client)
            evaluator.evaluate(sample_commit, sample_context, mock_db)

        call_kwargs = mock_client.complete.call_args[1]
        user_msg = call_kwargs["messages"][0]["content"]
        assert "Summary freshness" not in user_msg


# =============================================================================
# T14: Drafter Tests
# =============================================================================


class TestDrafter:
    """T14: Drafter agent."""

    def test_create_draft_x(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("create_draft", {
            "content": "Just shipped auth! 🔐",
            "platform": "x",
            "reasoning": "Milestone worth sharing",
        })

        decision = LogDecisionInput.validate({
            "decision": "post_worthy",
            "reasoning": "Major feature",
            "episode_type": "milestone",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            drafter = Drafter(mock_client)
            result = drafter.create_draft(
                decision, sample_context, sample_commit, mock_db,
            )

        assert isinstance(result, CreateDraftInput)
        assert "auth" in result.content.lower()
        assert result.platform.value == "x"

    def test_create_draft_linkedin(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("create_draft", {
            "content": "Implemented user authentication using JWT...",
            "platform": "linkedin",
            "reasoning": "Professional audience",
        })

        decision = LogDecisionInput.validate({
            "decision": "post_worthy", "reasoning": "Test",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            drafter = Drafter(mock_client)
            result = drafter.create_draft(
                decision, sample_context, sample_commit, mock_db,
                platform="linkedin",
            )

        assert result.platform.value == "linkedin"

    def test_create_draft_with_media(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("create_draft", {
            "content": "Auth flow diagram",
            "platform": "x",
            "reasoning": "Visual explanation",
            "media_type": "mermaid",
            "media_spec": {"diagram": "graph LR; A-->B"},
        })

        decision = LogDecisionInput.validate({
            "decision": "post_worthy", "reasoning": "Test",
            "media_tool": "mermaid",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            drafter = Drafter(mock_client)
            result = drafter.create_draft(
                decision, sample_context, sample_commit, mock_db,
            )

        assert result.media_type.value == "mermaid"

    def test_create_thread(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        thread_content = (
            "1/ Just shipped user authentication for my project.\n\n"
            "2/ The tricky part was handling token refresh without losing state.\n\n"
            "3/ Ended up using a rotating token strategy.\n\n"
            "4/ Full breakdown in the thread below."
        )
        mock_client.complete.return_value = _mock_response("create_draft", {
            "content": thread_content,
            "platform": "x",
            "reasoning": "Complex topic needs thread",
        })

        decision = LogDecisionInput.validate({
            "decision": "post_worthy", "reasoning": "Test",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            drafter = Drafter(mock_client)
            result = drafter.create_thread(
                decision, sample_context, sample_commit, mock_db,
            )

        assert isinstance(result, CreateDraftInput)
        # Verify the user message requested a thread
        call_kwargs = mock_client.complete.call_args[1]
        user_msg = call_kwargs["messages"][0]["content"]
        assert "thread" in user_msg.lower()
        assert "minimum 4" in user_msg

    def test_create_draft_free_tier_link_warning(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response("create_draft", {
            "content": "Test post",
            "platform": "x",
            "reasoning": "Test",
        })

        decision = LogDecisionInput.validate({
            "decision": "post_worthy", "reasoning": "Test",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            drafter = Drafter(mock_client)
            drafter.create_draft(
                decision, sample_context, sample_commit, mock_db,
                platform="x", tier="free",
            )

        call_kwargs = mock_client.complete.call_args[1]
        user_msg = call_kwargs["messages"][0]["content"]
        assert "Avoid links in main post" in user_msg

    def test_create_draft_no_tool_raises(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        mock_client.complete.return_value = _mock_response_no_tool()

        decision = LogDecisionInput.validate({
            "decision": "post_worthy", "reasoning": "Test",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            drafter = Drafter(mock_client)
            with pytest.raises(MalformedResponseError):
                drafter.create_draft(
                    decision, sample_context, sample_commit, mock_db,
                )

    def test_create_draft_with_arc_context(
        self, mock_client, mock_db, sample_commit, sample_context, prompts_dir
    ):
        """T20c: Arc posts include arc context in drafter."""
        mock_client.complete.return_value = _mock_response("create_draft", {
            "content": "Continuing the auth arc...",
            "platform": "x",
            "reasoning": "Advances auth arc",
        })

        decision = LogDecisionInput.validate({
            "decision": "post_worthy", "reasoning": "Arc post",
            "post_category": "arc", "arc_id": "arc_1",
        })

        arc = Arc(id="arc_1", project_id="proj_test1", theme="Auth arc", post_count=3)
        arc_ctx = {
            "arc": arc,
            "posts": [
                Post(id="p1", draft_id="d1", project_id="proj_test1",
                     platform="x", content="Previous auth post"),
            ],
        }

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            drafter = Drafter(mock_client)
            result = drafter.create_draft(
                decision, sample_context, sample_commit, mock_db,
                arc_context=arc_ctx,
            )

        assert isinstance(result, CreateDraftInput)


# =============================================================================
# T15: Gatekeeper Tests
# =============================================================================


class TestGatekeeper:
    """T15: Gatekeeper agent."""

    def test_route_approve(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("route_action", {
            "action": "handle_directly",
            "operation": "approve",
        })

        draft = Draft(
            id="draft_1", project_id="proj_1", decision_id="dec_1",
            platform="x", content="Test post",
        )

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            gk = Gatekeeper(mock_client)
            result = gk.route("looks good", draft_context=draft)

        assert isinstance(result, RouteActionInput)
        assert result.action.value == "handle_directly"
        assert result.operation.value == "approve"

    def test_route_schedule(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("route_action", {
            "action": "handle_directly",
            "operation": "schedule",
            "params": {"time": "2026-01-15T14:00:00"},
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            gk = Gatekeeper(mock_client)
            result = gk.route("schedule for 2pm tomorrow")

        assert result.operation.value == "schedule"
        assert result.params["time"] == "2026-01-15T14:00:00"

    def test_route_reject(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("route_action", {
            "action": "handle_directly",
            "operation": "reject",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            gk = Gatekeeper(mock_client)
            result = gk.route("no, skip this")

        assert result.operation.value == "reject"

    def test_route_cancel(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("route_action", {
            "action": "handle_directly",
            "operation": "cancel",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            gk = Gatekeeper(mock_client)
            result = gk.route("cancel")

        assert result.operation.value == "cancel"

    def test_route_escalate(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("route_action", {
            "action": "escalate_to_expert",
            "escalation_reason": "Creative request",
            "escalation_context": "User wants more casual tone",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            gk = Gatekeeper(mock_client)
            result = gk.route("make it more fun and casual")

        assert result.action.value == "escalate_to_expert"
        assert result.escalation_reason == "Creative request"

    def test_route_reject_with_context_escalates(self, mock_client, prompts_dir):
        """T20e: Reject with context escalates to expert."""
        mock_client.complete.return_value = _mock_response("route_action", {
            "action": "escalate_to_expert",
            "escalation_reason": "Reject with context",
            "escalation_context": "Too similar to yesterday's post",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            gk = Gatekeeper(mock_client)
            result = gk.route("no - too similar to yesterday's post")

        assert result.action.value == "escalate_to_expert"

    def test_route_with_project_summary(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("route_action", {
            "action": "handle_directly",
            "operation": "approve",
        })

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            gk = Gatekeeper(mock_client)
            result = gk.route(
                "approve", project_summary="Auth project for developers.",
            )

        # Verify summary was included in system prompt
        call_kwargs = mock_client.complete.call_args[1]
        assert "Auth project" in call_kwargs["system"]

    def test_route_no_tool_raises(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response_no_tool()

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            gk = Gatekeeper(mock_client)
            with pytest.raises(MalformedResponseError):
                gk.route("test message")


# =============================================================================
# T16: Expert Tests
# =============================================================================


class TestExpert:
    """T16: Expert agent."""

    def test_handle_refine_draft(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("expert_response", {
            "action": "refine_draft",
            "reasoning": "Adjusted tone per user request",
            "refined_content": "Updated auth post with casual tone!",
        })

        draft = Draft(
            id="draft_1", project_id="proj_1", decision_id="dec_1",
            platform="x", content="Original auth post.",
        )

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            expert = Expert(mock_client)
            result = expert.handle(
                draft, "make it more casual",
                escalation_reason="Creative request",
            )

        assert isinstance(result, ExpertResponseInput)
        assert result.action.value == "refine_draft"
        assert "casual" in result.refined_content

    def test_handle_answer_question(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("expert_response", {
            "action": "answer_question",
            "reasoning": "User asked about decision logic",
            "answer": "The commit was skipped because it was a minor fix.",
        })

        draft = {"content": "N/A", "platform": "x"}

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            expert = Expert(mock_client)
            result = expert.handle(
                draft, "why was my last commit skipped?",
                escalation_reason="Question about reasoning",
            )

        assert result.action.value == "answer_question"
        assert "skipped" in result.answer

    def test_handle_save_context_note(self, mock_client, prompts_dir):
        """T20e: Expert saves context note from reject-with-context."""
        mock_client.complete.return_value = _mock_response("expert_response", {
            "action": "save_context_note",
            "reasoning": "User provided feedback about post similarity",
            "context_note": "Author prefers more variety between consecutive posts",
        })

        draft = Draft(
            id="draft_1", project_id="proj_1", decision_id="dec_1",
            platform="x", content="Similar post content.",
        )

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            expert = Expert(mock_client)
            result = expert.handle(
                draft, "no - too similar to yesterday",
                escalation_reason="Reject with context",
                escalation_context="Post repetition feedback",
            )

        assert result.action.value == "save_context_note"
        assert "variety" in result.context_note

    def test_handle_with_project_summary(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response("expert_response", {
            "action": "refine_draft",
            "reasoning": "Test",
            "refined_content": "Refined content",
        })

        draft = {"content": "Test", "platform": "x"}

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            expert = Expert(mock_client)
            expert.handle(
                draft, "edit this",
                escalation_reason="Edit request",
                project_summary="Auth project summary.",
            )

        call_kwargs = mock_client.complete.call_args[1]
        assert "Auth project summary" in call_kwargs["system"]

    def test_handle_no_tool_raises(self, mock_client, prompts_dir):
        mock_client.complete.return_value = _mock_response_no_tool()

        draft = {"content": "Test", "platform": "x"}

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            expert = Expert(mock_client)
            with pytest.raises(MalformedResponseError):
                expert.handle(
                    draft, "test",
                    escalation_reason="Test",
                )

    def test_expert_shares_drafter_prompt(self, mock_client, prompts_dir):
        """Expert uses drafter.md, not its own prompt file."""
        mock_client.complete.return_value = _mock_response("expert_response", {
            "action": "refine_draft",
            "reasoning": "Test",
            "refined_content": "Test",
        })

        draft = {"content": "Test", "platform": "x"}

        with patch("social_hook.llm.prompts.Path.home",
                    return_value=prompts_dir.parent.parent):
            expert = Expert(mock_client)
            expert.handle(
                draft, "test",
                escalation_reason="Test",
            )

        call_kwargs = mock_client.complete.call_args[1]
        assert "# Drafter" in call_kwargs["system"]


# =============================================================================
# Interface validation: verify mock_db methods exist on real DryRunContext
# =============================================================================


class TestMockDbInterface:
    """Verify that methods called on mock_db exist on real DryRunContext."""

    def test_mocked_methods_exist_on_real_db(self, temp_db):
        """All methods called on mock_db in role tests must resolve via DryRunContext."""
        from social_hook.llm.dry_run import DryRunContext

        db = DryRunContext(temp_db, dry_run=True)
        # These are the methods role tests call on mock_db
        methods = ["get_summary_freshness", "insert_usage"]
        for method in methods:
            resolved = getattr(db, method, None)
            assert resolved is not None, f"DryRunContext missing method: {method}"
