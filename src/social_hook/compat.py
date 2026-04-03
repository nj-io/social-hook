"""Compatibility adapter for LogEvaluationInput -> flat attribute namespace."""

from types import SimpleNamespace


def evaluation_from_decision(decision, override_decision: str | None = None) -> SimpleNamespace:
    """Build a flat evaluation namespace from a DB decision row.

    Used by manual draft, create-draft endpoint, consolidation, intro lifecycle,
    and promote — anywhere we re-enter the drafting pipeline from an existing decision.

    Args:
        decision: DB decision row (or any object with the expected attributes).
        override_decision: Override the decision field. Defaults to None, which
            preserves the original decision.decision value.
    """
    return SimpleNamespace(
        decision=override_decision if override_decision is not None else decision.decision,
        reasoning=decision.reasoning,
        angle=decision.angle,
        episode_type=None,
        post_category=decision.post_category,
        arc_id=getattr(decision, "arc_id", None),
        new_arc_theme=None,
        media_tool=getattr(decision, "media_tool", None),
        reference_posts=getattr(decision, "reference_posts", None),
        include_project_docs=True,
        commit_summary=getattr(decision, "commit_summary", None),
    )


def make_eval_compat(
    evaluation, decision_str: str, target_name: str = "default"
) -> SimpleNamespace:
    """Map LogEvaluationInput to flat attribute namespace for drafting pipeline.

    The drafting pipeline uses getattr() to read fields like arc_id,
    media_tool. With the new evaluator format, these live under
    evaluation.strategies[target_name]. This adapter preserves backward compat.
    """
    # Use .strategies directly; fall back to .targets for SimpleNamespace callers
    strategies = getattr(evaluation, "strategies", None)
    if strategies is None:
        strategies = getattr(evaluation, "targets", None)
    if strategies is None:
        raise KeyError("Evaluation has no strategies or targets")
    target = strategies.get(target_name)
    if target is None:
        raise KeyError(f"Evaluation missing target '{target_name}'")

    from social_hook.parsing import enum_value

    return SimpleNamespace(
        decision=decision_str,
        reasoning=target.reason,
        angle=target.angle,
        episode_type=None,
        post_category=enum_value(target.post_category),
        arc_id=target.arc_id,
        new_arc_theme=target.new_arc_theme,
        media_tool=enum_value(target.media_tool),
        reference_posts=target.reference_posts,
        commit_summary=evaluation.commit_analysis.summary,
        include_project_docs=target.include_project_docs,
    )
