"""Evaluation result inspection for E2E scenarios.

Queries and formats per-strategy evaluator decisions after run_trigger().
Use in any E2E scenario that calls run_trigger() and needs to inspect
the evaluator's output — not just targets-specific tests.

Example::

    from e2e.helpers.decisions import get_latest_evaluation, format_evaluation_summary

    run_trigger(commit_hash, repo_path)
    result = get_latest_evaluation(harness, commit_hash)

    # Structured output for operator
    print(format_evaluation_summary(result))

    # Assertions per strategy
    for strategy_name, decision in result["strategies"].items():
        if strategy_name == "brand-primary":
            assert decision["action"] == "skip"

    # Human review
    runner.add_review_item(
        scenario_id="V16",
        title="Major feature evaluation",
        decisions=result["strategies"],
        review_question="Are the per-strategy decisions sensible?",
    )
"""

import json

from social_hook.db import operations as ops
from social_hook.parsing import safe_json_loads


def get_latest_evaluation(harness, commit_hash=None):
    """Get the most recent evaluation with parsed strategy decisions.

    Args:
        harness: E2EHarness with ``conn`` and ``project_id``.
        commit_hash: If provided, find the decision for this specific
            commit. Otherwise returns the most recent decision.

    Returns:
        Dict with keys:
        - ``decision``: the Decision model instance
        - ``strategies``: parsed dict of strategy_name -> {action, reason, topic_id, ...}
        - ``overall_action``: the decision.decision field ("draft", "hold", "skip")
        - ``drafts``: list of Draft objects produced by this decision
        - ``tags``: list of episode_tags from the decision
        - ``cycle_id``: evaluation_cycle_id from the first draft (if any)

    Returns None if no matching decision found.
    """
    if commit_hash:
        # Find decision by commit hash (prefix match)
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=50)
        decision = None
        for d in decisions:
            if d.commit_hash and d.commit_hash.startswith(commit_hash[:7]):
                decision = d
                break
    else:
        decisions = ops.get_recent_decisions(harness.conn, harness.project_id, limit=1)
        decision = decisions[0] if decisions else None

    if decision is None:
        return None

    # Parse per-strategy decisions from targets JSON
    strategies = safe_json_loads(
        json.dumps(decision.targets) if isinstance(decision.targets, dict) else decision.targets,
        "decision.targets",
        default={},
    )

    # Get drafts produced by this decision
    all_drafts = ops.get_pending_drafts(harness.conn, harness.project_id)
    decision_drafts = [d for d in all_drafts if d.decision_id == decision.id]

    # Get episode tags
    tags = []
    if hasattr(decision, "episode_tags") and decision.episode_tags:
        if isinstance(decision.episode_tags, list):
            tags = decision.episode_tags
        elif isinstance(decision.episode_tags, str):
            tags = safe_json_loads(decision.episode_tags, "episode_tags", default=[])

    # Get cycle_id from first draft if available
    cycle_id = None
    if decision_drafts:
        cycle_id = getattr(decision_drafts[0], "evaluation_cycle_id", None)

    return {
        "decision": decision,
        "strategies": strategies,
        "overall_action": decision.decision,
        "drafts": decision_drafts,
        "tags": tags,
        "cycle_id": cycle_id,
    }


def format_evaluation_summary(result, commit_desc=""):
    """Format a structured evaluation summary for terminal display.

    Args:
        result: Dict from ``get_latest_evaluation()``.
        commit_desc: Optional one-line description (e.g., "feat: preview overhaul").

    Returns:
        Formatted multi-line string. Example::

            Evaluation: feat: preview overhaul
            Tags: [architecture, feature, platform]
            Overall: draft

              building-public:      draft    "Interesting architecture change worth narrating"
              technical-deep-dive:  hold     "Waiting for more platform work"
              brand-primary:        skip     "Internal refactoring, no user-facing value prop"

            Drafts: 1 produced
    """
    if result is None:
        return "  (no evaluation result found)"

    lines = []

    if commit_desc:
        lines.append(f"  Evaluation: {commit_desc}")

    tags = result.get("tags", [])
    if tags:
        lines.append(f"  Tags: [{', '.join(tags)}]")

    lines.append(f"  Overall: {result['overall_action']}")
    lines.append("")

    strategies = result.get("strategies", {})
    if strategies:
        # Find max strategy name length for alignment
        max_name = max(len(name) for name in strategies) if strategies else 0

        for name, strat in strategies.items():
            action = strat.get("action", "?") if isinstance(strat, dict) else "?"
            reason = strat.get("reason", "") if isinstance(strat, dict) else ""
            # Truncate reason to 60 chars
            if len(reason) > 60:
                reason = reason[:57] + "..."
            lines.append(f'    {name:<{max_name + 2}} {action:<8} "{reason}"')
    else:
        lines.append("    (no per-strategy decisions — legacy single-target evaluation)")

    lines.append("")
    draft_count = len(result.get("drafts", []))
    lines.append(f"  Drafts: {draft_count} produced")

    return "\n".join(lines)


def assert_strategy_actions(result, expected, scenario_id=""):
    """Assert expected actions for each strategy.

    Args:
        result: Dict from ``get_latest_evaluation()``.
        expected: Dict mapping strategy_name -> expected action string
            (or list of acceptable actions). Example::

                {"building-public": "draft", "brand-primary": "skip",
                 "technical-deep-dive": ["draft", "hold"]}

        scenario_id: For error messages.

    Raises:
        AssertionError with detailed message if any assertion fails.
    """
    strategies = result.get("strategies", {})

    for strategy_name, expected_action in expected.items():
        if strategy_name not in strategies:
            raise AssertionError(
                f"[{scenario_id}] Strategy '{strategy_name}' not in evaluation result. "
                f"Available: {list(strategies.keys())}"
            )

        strat = strategies[strategy_name]
        actual_action = strat.get("action", "?") if isinstance(strat, dict) else "?"

        if isinstance(expected_action, list):
            if actual_action not in expected_action:
                reason = strat.get("reason", "") if isinstance(strat, dict) else ""
                raise AssertionError(
                    f"[{scenario_id}] {strategy_name}: expected one of {expected_action}, "
                    f"got '{actual_action}' (reason: {reason})"
                )
        elif actual_action != expected_action:
            reason = strat.get("reason", "") if isinstance(strat, dict) else ""
            raise AssertionError(
                f"[{scenario_id}] {strategy_name}: expected '{expected_action}', "
                f"got '{actual_action}' (reason: {reason})"
            )
