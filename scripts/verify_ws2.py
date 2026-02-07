#!/usr/bin/env python3
"""WS2 LLM Roles verification script.

Verifies the full WS2 pipeline end-to-end:
  --dry-run  Mock API calls, test all components (default)
  --live     Real API calls (~$0.50-$2.00, requires ANTHROPIC_API_KEY)

Usage:
  python scripts/verify_ws2.py --dry-run
  python scripts/verify_ws2.py --live
"""

import argparse
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Step tracking
# ---------------------------------------------------------------------------

_step = 0
_failures = 0


def step(label: str) -> None:
    global _step
    _step += 1
    print(f"\n  [{_step:2d}] {label}")


def ok(msg: str) -> None:
    print(f"       OK  {msg}")


def fail(msg: str) -> None:
    global _failures
    _failures += 1
    print(f"       FAIL  {msg}")


def check(condition: bool, pass_msg: str, fail_msg: str) -> None:
    if condition:
        ok(pass_msg)
    else:
        fail(fail_msg)


# ---------------------------------------------------------------------------
# Mock helpers for dry-run mode
# ---------------------------------------------------------------------------


def _mock_evaluator_response():
    """Build a mock Claude API response for the Evaluator."""
    tool_use = SimpleNamespace(
        type="tool_use",
        name="log_decision",
        input={
            "decision": "post_worthy",
            "reasoning": "Added user authentication - significant feature",
            "episode_type": "milestone",
            "post_category": "arc",
        },
    )
    usage = SimpleNamespace(
        input_tokens=1200,
        output_tokens=150,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[tool_use], usage=usage)


def _mock_drafter_response(platform: str = "x"):
    """Build a mock Claude API response for the Drafter."""
    content = (
        "Just shipped user auth. Sessions, password hashing, the works."
        if platform == "x"
        else "We just shipped user authentication for our project.\n\n"
        "This includes session management, secure password hashing, "
        "and role-based access control.\n\nHere's what we learned..."
    )
    tool_use = SimpleNamespace(
        type="tool_use",
        name="create_draft",
        input={
            "content": content,
            "platform": platform,
            "reasoning": "Milestone post about auth feature",
        },
    )
    usage = SimpleNamespace(
        input_tokens=2000,
        output_tokens=200,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[tool_use], usage=usage)


def _mock_drafter_thread_response():
    """Build a mock Claude API response for thread creation."""
    content = (
        "1/ Just shipped user auth for our project. Here's the story.\n\n"
        "2/ Started with session management. Evaluated JWT vs cookies.\n\n"
        "3/ Went with httpOnly cookies. More secure for our use case.\n\n"
        "4/ Password hashing uses bcrypt with 12 rounds. No shortcuts on security."
    )
    tool_use = SimpleNamespace(
        type="tool_use",
        name="create_draft",
        input={
            "content": content,
            "platform": "x",
            "reasoning": "Thread about auth implementation journey",
        },
    )
    usage = SimpleNamespace(
        input_tokens=2500,
        output_tokens=300,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[tool_use], usage=usage)


def _mock_gatekeeper_response(action: str, operation: str = None, **kwargs):
    """Build a mock Claude API response for the Gatekeeper."""
    input_data = {"action": action}
    if operation:
        input_data["operation"] = operation
    input_data.update(kwargs)
    tool_use = SimpleNamespace(
        type="tool_use",
        name="route_action",
        input=input_data,
    )
    usage = SimpleNamespace(
        input_tokens=500,
        output_tokens=50,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[tool_use], usage=usage)


def _mock_expert_response(action: str, **kwargs):
    """Build a mock Claude API response for the Expert."""
    input_data = {
        "action": action,
        "reasoning": f"Expert {action} response",
    }
    if action == "refine_draft":
        input_data["refined_content"] = "Refined: Just shipped auth. Clean, secure, done."
    elif action == "answer_question":
        input_data["answer"] = "We chose this angle because auth is a milestone feature."
    elif action == "save_context_note":
        input_data["context_note"] = "Wait for auth feature to ship before posting about security."
    input_data.update(kwargs)
    tool_use = SimpleNamespace(
        type="tool_use",
        name="expert_response",
        input=input_data,
    )
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=100,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[tool_use], usage=usage)


# ---------------------------------------------------------------------------
# Main verification
# ---------------------------------------------------------------------------


def verify(live: bool = False) -> bool:
    """Run verification steps. Returns True if all pass."""

    global _step, _failures
    _step = 0
    _failures = 0

    mode = "LIVE" if live else "DRY-RUN"
    print(f"\n{'='*60}")
    print(f"  WS2 LLM Roles Verification ({mode})")
    print(f"{'='*60}")

    # --- Setup temp DB and project directory ---
    tmpdir = tempfile.mkdtemp(prefix="ws2_verify_")
    tmp_path = Path(tmpdir)
    db_path = tmp_path / "test.db"
    repo_path = tmp_path / "test-project"
    repo_path.mkdir()
    config_dir = repo_path / ".social-hook"
    config_dir.mkdir()

    # Create a minimal social-context.md
    (config_dir / "social-context.md").write_text(
        "## Voice\nTechnical but approachable.\n\n## Audience\nDevelopers.\n"
    )

    # =========================================================================
    # Step 1: Database initialization
    # =========================================================================
    step("Database initialization")
    from social_hook.db import init_database

    conn = init_database(db_path)  # Mismatch #2 fixed: pass db_path
    check(conn is not None, "init_database(db_path) succeeded", "init_database failed")

    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models import (
        Arc,
        Decision,
        Draft,
        Lifecycle,
        NarrativeDebt,
        Post,
        Project,
        UsageLog,
    )

    project = Project(
        id="proj_verify1",
        name="test-project",
        repo_path=str(repo_path),
    )
    ops.insert_project(conn, project)
    ok("Project inserted")

    # =========================================================================
    # Step 2: Tool schema validation
    # =========================================================================
    step("Tool schema validation")
    from social_hook.llm.schemas import (  # Mismatch #5 fixed: *Input not *Schema
        CreateDraftInput,
        ExpertResponseInput,
        LogDecisionInput,
        RouteActionInput,
    )
    from social_hook.errors import MalformedResponseError  # Mismatch #7 fixed

    valid_decision = LogDecisionInput.validate({
        "decision": "post_worthy",
        "reasoning": "Interesting feature",
        "episode_type": "milestone",
        "post_category": "arc",
    })
    check(
        valid_decision.decision == "post_worthy",  # Mismatch #6 fixed: .decision not ["decision"]
        "LogDecisionInput validates post_worthy",
        "LogDecisionInput validation failed",
    )

    valid_route = RouteActionInput.validate({
        "action": "handle_directly",
        "operation": "schedule",
        "params": {"time": "2026-02-05T14:00:00Z"},
    })
    check(
        valid_route.operation == "schedule",  # Mismatch #6
        "RouteActionInput validates schedule",
        "RouteActionInput validation failed",
    )

    try:
        LogDecisionInput.validate({"decision": "invalid"})
        fail("Should have raised MalformedResponseError")  # Mismatch #7
    except MalformedResponseError:
        ok("Invalid decision raises MalformedResponseError")

    # =========================================================================
    # Step 3: DryRunContext setup
    # =========================================================================
    step("DryRunContext wraps DB operations")
    from social_hook.llm.dry_run import DryRunContext

    dry_db = DryRunContext(conn, dry_run=True)

    fetched = dry_db.get_project("proj_verify1")
    check(
        fetched is not None and fetched.id == "proj_verify1",
        "DryRunContext reads pass through",
        "DryRunContext read failed",
    )

    # Writes should be no-ops in dry-run
    fake_draft = Draft(
        id="draft_noop", project_id="proj_verify1",
        decision_id="dec_noop", platform="x", content="noop",
    )
    result = dry_db.insert_draft(fake_draft)
    check(result == "draft_noop", "Dry-run write returns ID", f"Got {result}")

    actual = ops.get_draft(conn, "draft_noop")
    check(actual is None, "Dry-run write did not persist", "Dry-run write persisted!")

    # =========================================================================
    # Step 4: ClaudeClient setup
    # =========================================================================
    step("ClaudeClient initialization")
    from social_hook.config import load_full_config
    from social_hook.llm.client import ClaudeClient

    if live:
        config = load_full_config()  # Reads ~/.social-hook/.env + config.yaml
        api_key = config.env.get("ANTHROPIC_API_KEY")
        if not api_key:
            fail("ANTHROPIC_API_KEY not found in ~/.social-hook/.env")
            return False
        # Mismatch #1, #3, #4 fixed: use config.env, pass both args
        client_eval = ClaudeClient(api_key=api_key, model=config.models.evaluator)
        client_draft = ClaudeClient(api_key=api_key, model=config.models.drafter)
        client_gk = ClaudeClient(api_key=api_key, model=config.models.gatekeeper)
        ok(f"ClaudeClients created (eval={config.models.evaluator}, draft={config.models.drafter}, gk={config.models.gatekeeper})")
    else:
        client_eval = MagicMock(spec=ClaudeClient)
        client_draft = MagicMock(spec=ClaudeClient)
        client_gk = MagicMock(spec=ClaudeClient)
        ok("Mock ClaudeClients created (dry-run)")

    # =========================================================================
    # Step 5: ProjectContext assembly
    # =========================================================================
    step("ProjectContext assembly")

    # Set up supporting data
    lifecycle = Lifecycle(project_id="proj_verify1", phase="build", confidence=0.8)
    ops.insert_lifecycle(conn, lifecycle)

    arc = Arc(id=generate_id("arc"), project_id="proj_verify1", theme="Auth system")
    ops.insert_arc(conn, arc)

    debt = NarrativeDebt(project_id="proj_verify1", debt_counter=1)
    ops.insert_narrative_debt(conn, debt)

    ops.update_project_summary(conn, "proj_verify1", "A test project building auth.")

    from social_hook.config.project import ProjectConfig, load_project_config
    from social_hook.llm.prompts import assemble_evaluator_context
    from social_hook.models import CommitInfo

    project_config = load_project_config(repo_path, global_base=tmp_path / "no-global")
    check(
        project_config.social_context is not None,
        "ProjectConfig loaded social_context",
        "social_context is None",
    )

    read_db = DryRunContext(conn, dry_run=False)
    project_context = assemble_evaluator_context(
        read_db, "proj_verify1", project_config,
    )
    check(project_context.project.id == "proj_verify1", "ProjectContext assembled", "Assembly failed")
    check(project_context.lifecycle.phase == "build", "Lifecycle loaded", "Lifecycle missing")
    check(len(project_context.active_arcs) == 1, "Arcs loaded", "Arcs missing")
    check(project_context.narrative_debt == 1, "Debt loaded", f"Debt={project_context.narrative_debt}")
    check(project_context.project_summary is not None, "Summary loaded", "Summary missing")

    # =========================================================================
    # Step 6: Evaluator
    # =========================================================================
    step("Evaluator evaluation")
    from social_hook.llm.evaluator import Evaluator

    commit = CommitInfo(
        hash="abc123def456",
        message="Add user authentication module",
        diff="+ def authenticate(user):\n+     return check_password(user)",
        files_changed=["src/auth.py", "tests/test_auth.py"],
        insertions=50,
        deletions=10,
    )

    evaluator = Evaluator(client_eval)
    eval_db = DryRunContext(conn, dry_run=True)

    if live:
        # Set up prompt files for live mode
        prompts_dir = Path.home() / ".social-hook" / "prompts"
        if not (prompts_dir / "evaluator.md").exists():
            fail("Missing ~/.social-hook/prompts/evaluator.md (run social-hook setup)")
            return False
        decision = evaluator.evaluate(commit, project_context, eval_db)  # Mismatch #8
    else:
        client_eval.complete.return_value = _mock_evaluator_response()
        with patch("social_hook.llm.evaluator.load_prompt", return_value="# Evaluator\nYou evaluate commits."):
            decision = evaluator.evaluate(commit, project_context, eval_db)  # Mismatch #8

    check(
        decision.decision in ("post_worthy", "not_post_worthy", "consolidate", "deferred"),
        f"Decision: {decision.decision}",
        f"Unexpected decision: {decision.decision}",
    )
    ok(f"Reasoning: {decision.reasoning[:60]}...")

    # =========================================================================
    # Step 7: Drafter (X platform)
    # =========================================================================
    step("Drafter - X platform")
    from social_hook.llm.drafter import Drafter

    drafter = Drafter(client_draft)

    if live:
        draft_result = drafter.create_draft(
            decision, project_context, commit, eval_db, platform="x",
        )  # Mismatch #9: add commit, db
    else:
        client_draft.complete.return_value = _mock_drafter_response("x")
        with patch("social_hook.llm.drafter.load_prompt", return_value="# Drafter\nYou draft content."):
            draft_result = drafter.create_draft(
                decision, project_context, commit, eval_db, platform="x",
            )  # Mismatch #9

    check(
        draft_result.content is not None and len(draft_result.content) > 0,
        f"Draft content ({len(draft_result.content)} chars)",
        "Draft content is empty",
    )
    ok(f"Content: {draft_result.content[:60]}...")

    # =========================================================================
    # Step 8: Drafter (LinkedIn)
    # =========================================================================
    step("Drafter - LinkedIn platform")

    if live:
        draft_li = drafter.create_draft(
            decision, project_context, commit, eval_db, platform="linkedin",
        )
    else:
        client_draft.complete.return_value = _mock_drafter_response("linkedin")
        with patch("social_hook.llm.drafter.load_prompt", return_value="# Drafter\nYou draft content."):
            draft_li = drafter.create_draft(
                decision, project_context, commit, eval_db, platform="linkedin",
            )

    check(
        draft_li.content is not None,
        f"LinkedIn draft ({len(draft_li.content)} chars)",
        "LinkedIn draft failed",
    )

    # =========================================================================
    # Step 9: Drafter thread creation
    # =========================================================================
    step("Drafter - Thread creation")

    if live:
        thread_result = drafter.create_thread(
            decision, project_context, commit, eval_db,
        )
    else:
        client_draft.complete.return_value = _mock_drafter_thread_response()
        with patch("social_hook.llm.drafter.load_prompt", return_value="# Drafter\nYou draft content."):
            thread_result = drafter.create_thread(
                decision, project_context, commit, eval_db,
            )

    # Mismatch #10 fixed: check content format, not .tweets attribute
    check(
        thread_result.content is not None and len(thread_result.content) > 0,
        f"Thread content ({len(thread_result.content)} chars)",
        "Thread content empty",
    )

    # =========================================================================
    # Step 10: Gatekeeper routing
    # =========================================================================
    step("Gatekeeper routing")
    from social_hook.llm.gatekeeper import Gatekeeper

    gatekeeper = Gatekeeper(client_gk)

    # Create a draft for context
    test_draft = Draft(
        id=generate_id("draft"), project_id="proj_verify1",
        decision_id="dec_001", platform="x",
        content="Just shipped auth!",
    )

    gk_tests = [
        ("approve", "handle_directly", "approve", {}),
        ("post at 3pm", "handle_directly", "schedule", {}),
        ("what's pending?", "handle_directly", "query", {}),
        ("cancel this", "handle_directly", "cancel", {}),
        ("make it punchier", "escalate_to_expert", None,
         {"escalation_reason": "Creative refinement requested"}),
    ]

    for msg, expected_action, expected_op, extra in gk_tests:
        if live:
            route = gatekeeper.route(msg, draft_context=test_draft)
        else:
            mock_resp = _mock_gatekeeper_response(expected_action, expected_op, **extra)
            client_gk.complete.return_value = mock_resp
            with patch("social_hook.llm.gatekeeper.load_prompt", return_value="# Gatekeeper\nYou route messages."):
                route = gatekeeper.route(msg, draft_context=test_draft)

        check(
            route.action == expected_action,
            f'"{msg}" -> {route.action}' + (f'/{route.operation}' if route.operation else ''),
            f'"{msg}" -> expected {expected_action}, got {route.action}',
        )

    # =========================================================================
    # Step 11: Expert handling
    # =========================================================================
    step("Expert handling (all 3 action types)")
    from social_hook.llm.expert import Expert

    expert = Expert(client_draft)  # Expert shares drafter model

    # Mismatch #11 fixed: expert.handle(draft, msg, reason) — no action arg
    expert_tests = [
        ("refine_draft", "make it punchier", "Creative refinement"),
        ("answer_question", "why this angle?", "Question about strategy"),
        ("save_context_note", "wait for auth feature", "Reject with context"),
    ]

    for expected_action, msg, reason in expert_tests:
        if live:
            result = expert.handle(
                test_draft, msg, escalation_reason=reason,
            )
        else:
            client_draft.complete.return_value = _mock_expert_response(expected_action)
            with patch("social_hook.llm.expert.load_prompt", return_value="# Drafter\nYou draft content."):
                result = expert.handle(
                    test_draft, msg, escalation_reason=reason,
                )

        check(
            result.action == expected_action,
            f"Expert {expected_action}: OK",
            f"Expert expected {expected_action}, got {result.action}",
        )

        if expected_action == "refine_draft":
            check(result.refined_content is not None, "refined_content present", "refined_content missing")
        elif expected_action == "answer_question":
            check(result.answer is not None, "answer present", "answer missing")
        elif expected_action == "save_context_note":
            check(result.context_note is not None, "context_note present", "context_note missing")

    # =========================================================================
    # Step 12: Prompt assembly
    # =========================================================================
    step("Prompt assembly")
    from social_hook.llm.prompts import (  # Mismatch #12 fixed: assemble_evaluator_prompt
        assemble_evaluator_prompt,
        assemble_drafter_prompt,
        assemble_gatekeeper_prompt,
        assemble_expert_prompt,
    )

    assembled = assemble_evaluator_prompt(
        "# Evaluator\nBase prompt.", project_context, commit,
    )
    check("## Project Context" in assembled, "Evaluator prompt has project context", "Missing context")
    check("## Recent History" in assembled, "Evaluator prompt has recent history", "Missing history")
    check("## Current Commit" in assembled, "Evaluator prompt has commit", "Missing commit")

    # =========================================================================
    # Step 13: Lifecycle detection
    # =========================================================================
    step("Lifecycle detection")
    from social_hook.narrative.lifecycle import detect_lifecycle_phase

    lc = detect_lifecycle_phase({
        "tests_growing": True,
        "architecture_stabilizing": True,
    })
    check(
        lc.phase in ("research", "build", "demo", "launch", "post_launch"),
        f"Phase: {lc.phase} (confidence: {lc.confidence})",
        f"Invalid phase: {lc.phase}",
    )
    check(0.0 <= lc.confidence <= 1.0, "Confidence in range", "Confidence out of range")

    # =========================================================================
    # Step 14: Strategy triggers
    # =========================================================================
    step("Strategy triggers")
    from social_hook.narrative.lifecycle import check_strategy_triggers, record_strategy_moment

    triggers = check_strategy_triggers(conn, "proj_verify1")
    check(isinstance(triggers, list), f"Triggers: {triggers}", "Triggers not a list")

    record_strategy_moment(conn, "proj_verify1")
    ok("Strategy moment recorded")

    # =========================================================================
    # Step 15: Onboarding flags
    # =========================================================================
    step("Onboarding flags")
    from social_hook.narrative.lifecycle import get_audience_introduced, set_audience_introduced

    check(
        get_audience_introduced(conn, "proj_verify1") is False,
        "Default: audience not introduced",
        "Default should be False",
    )
    set_audience_introduced(conn, "proj_verify1", True)
    check(
        get_audience_introduced(conn, "proj_verify1") is True,
        "Set audience_introduced=True",
        "Failed to set True",
    )

    # =========================================================================
    # Step 16: Arc management
    # =========================================================================
    step("Arc management")
    from social_hook.narrative.arcs import create_arc, update_arc, get_active_arcs

    arc_id = create_arc(conn, "proj_verify1", "Testing framework")
    update_arc(conn, arc_id, post_count=1)
    arcs = get_active_arcs(conn, "proj_verify1")
    check(
        1 <= len(arcs) <= 3,
        f"Active arcs: {len(arcs)}",
        f"Arc count out of range: {len(arcs)}",
    )

    # =========================================================================
    # Step 17: Narrative debt
    # =========================================================================
    step("Narrative debt")
    from social_hook.narrative.debt import (
        get_narrative_debt,
        increment_narrative_debt,
        reset_narrative_debt,
    )

    d = increment_narrative_debt(conn, "proj_verify1")
    check(d >= 1, f"Incremented debt: {d}", "Debt increment failed")

    reset_narrative_debt(conn, "proj_verify1")
    check(
        get_narrative_debt(conn, "proj_verify1") == 0,
        "Debt reset to 0",
        "Debt reset failed",
    )

    # =========================================================================
    # Step 18: Draft superseding
    # =========================================================================
    step("Draft superseding")

    # Insert a decision for FK constraint
    dec_for_drafts = Decision(
        id="dec_001", project_id="proj_verify1",
        commit_hash="abc123", decision="post_worthy",
        reasoning="Test decision for draft superseding",
    )
    ops.insert_decision(conn, dec_for_drafts)

    draft1 = Draft(
        id=generate_id("draft"), project_id="proj_verify1",
        decision_id="dec_001", platform="x",  # Mismatch #16 fixed: required fields
        content="First draft",
    )
    draft2 = Draft(
        id=generate_id("draft"), project_id="proj_verify1",
        decision_id="dec_001", platform="x",  # Mismatch #16 fixed
        content="Second draft (supersedes first)",
    )
    ops.insert_draft(conn, draft1)
    ops.insert_draft(conn, draft2)

    ops.supersede_draft(conn, draft1.id, draft2.id)
    old = ops.get_draft(conn, draft1.id)
    check(old.status == "superseded", "Old draft superseded", f"Status: {old.status}")
    check(old.superseded_by == draft2.id, "superseded_by set", "superseded_by wrong")

    # =========================================================================
    # Step 19: Memories wrapper
    # =========================================================================
    step("Memories read/write")
    from social_hook.narrative.memories import add_memory, parse_memories_file

    # Mismatch #17 fixed: pass repo_path, not project_id
    add_memory(repo_path, "Technical post", '"Too formal"', "draft_verify1")
    memories = parse_memories_file(repo_path)
    check(len(memories) >= 1, f"Memories: {len(memories)}", "No memories found")
    check(
        len(memories) <= 100,
        "Under 100 memory cap",
        f"Over cap: {len(memories)}",
    )

    # =========================================================================
    # Step 20: Context notes
    # =========================================================================
    step("Context notes persistence")
    from social_hook.config.project import save_context_note, load_context_notes

    save_context_note(repo_path, "Wait for auth feature before security posts", "expert:draft_001")
    notes = load_context_notes(repo_path)
    check(len(notes) == 1, "Context note saved", f"Notes: {len(notes)}")
    check(
        notes[0]["note"] == "Wait for auth feature before security posts",
        "Note content correct",
        f"Note: {notes[0].get('note')}",
    )

    # =========================================================================
    # Step 21: Usage logging
    # =========================================================================
    step("Usage logging")

    usage_log = UsageLog(  # Mismatch #14 fixed: UsageLog not UsageRecord
        id=generate_id("usage"),
        project_id="proj_verify1",
        operation_type="evaluate",
        model="claude-opus-4-5",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=10,
        cache_creation_tokens=5,
        cost_cents=0.5,  # Mismatch #15 fixed: calculated separately, not on response
    )
    ops.insert_usage(conn, usage_log)
    summary = ops.get_usage_summary(conn, days=30)
    check(summary is not None, f"Usage summary: {len(summary)} model(s)", "Usage summary failed")

    # =========================================================================
    # Step 22: Milestone summaries in prompt
    # =========================================================================
    step("Milestone summaries in evaluator prompt")
    project_context.milestone_summaries = [
        {
            "milestone_type": "post",
            "summary": "First post about auth module.",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
        },
    ]
    assembled_ms = assemble_evaluator_prompt(
        "# Evaluator\nBase prompt.", project_context, commit,
    )
    check(
        "## Milestone Summaries" in assembled_ms,
        "Milestone summaries section present",
        "Missing milestone summaries",
    )
    check(
        "First post about auth module" in assembled_ms,
        "Milestone content included",
        "Milestone content missing",
    )

    # =========================================================================
    # Cleanup and summary
    # =========================================================================
    conn.close()

    print(f"\n{'='*60}")
    if _failures == 0:
        print(f"  ALL {_step} STEPS PASSED")
    else:
        print(f"  {_failures} FAILURE(S) out of {_step} steps")
    print(f"{'='*60}\n")

    return _failures == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="WS2 LLM Roles verification")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Mock API calls (default)",
    )
    group.add_argument(
        "--live", action="store_true",
        help="Real API calls (~$0.50-$2.00, requires ANTHROPIC_API_KEY)",
    )
    args = parser.parse_args()

    success = verify(live=args.live)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
