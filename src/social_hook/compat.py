"""Compatibility adapter for LogEvaluationInput -> flat attribute namespace."""

from types import SimpleNamespace


def make_eval_compat(evaluation, decision_str: str, target_name: str = "default") -> SimpleNamespace:
    """Map LogEvaluationInput to flat attribute namespace for drafting pipeline.

    The drafting pipeline uses getattr() to read fields like episode_type,
    arc_id, media_tool. With the new evaluator format, these live under
    evaluation.targets[target_name]. This adapter preserves backward compat.
    """
    target = evaluation.targets.get(target_name)
    if target is None:
        raise KeyError(f"Evaluation missing target '{target_name}'")

    def _val(x):
        return x.value if hasattr(x, "value") else x

    return SimpleNamespace(
        decision=decision_str,
        reasoning=target.reason,
        angle=target.angle,
        episode_type=_val(target.episode_type),
        post_category=_val(target.post_category),
        arc_id=target.arc_id,
        new_arc_theme=target.new_arc_theme,
        media_tool=_val(target.media_tool),
        reference_posts=target.reference_posts,
        commit_summary=evaluation.commit_analysis.summary,
        include_project_docs=target.include_project_docs,
    )
