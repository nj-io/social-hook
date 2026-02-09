"""Prompt loading and context assembly for LLM agents (T17)."""

from pathlib import Path
from typing import Any, Optional

from social_hook.config.project import (
    ContextConfig,
    ProjectConfig,
    _parse_context_notes,
    _parse_memories,
)
from social_hook.errors import PromptNotFoundError
from social_hook.models import CommitInfo, ProjectContext


def load_prompt(role: str) -> str:
    """Load a prompt template from ~/.social-hook/prompts/{role}.md.

    Args:
        role: Agent role name (evaluator, drafter, gatekeeper)

    Returns:
        Prompt template content

    Raises:
        PromptNotFoundError: If prompt file does not exist
    """
    prompt_path = Path.home() / ".social-hook" / "prompts" / f"{role}.md"
    if not prompt_path.exists():
        raise PromptNotFoundError(
            f"Prompt file not found: {prompt_path}. "
            f"Run 'social-hook setup' to create default prompts."
        )
    return prompt_path.read_text(encoding="utf-8")


def count_tokens(text: str) -> int:
    """Approximate token count for text.

    Uses chars/4 heuristic. Sufficient for context budgeting.
    """
    return len(text) // 4


def assemble_evaluator_prompt(
    prompt: str,
    project_context: ProjectContext,
    commit: CommitInfo,
    config: Optional[ContextConfig] = None,
) -> str:
    """Assemble full evaluator system prompt with context.

    Per TECH_ARCH L1553-1580: Includes lifecycle, arcs, debt, pending drafts,
    recent history, and commit details.

    Args:
        prompt: Base evaluator prompt template
        project_context: Assembled project state
        commit: Current commit information
        config: Context config for limits

    Returns:
        Complete system prompt string
    """
    if config is None:
        config = ContextConfig()

    sections = [prompt]

    # Project context
    sections.append("\n---\n## Project Context")
    if project_context.social_context:
        sections.append(project_context.social_context)

    # Current state
    sections.append("\n---\n## Current State")
    if project_context.lifecycle:
        lc = project_context.lifecycle
        sections.append(
            f"- Lifecycle phase: {lc.phase} (confidence: {lc.confidence})"
        )
    sections.append(f"- Narrative debt: {project_context.narrative_debt}")
    sections.append(
        f"- Audience introduced: {project_context.audience_introduced}"
    )

    if project_context.active_arcs:
        arc_summaries = ", ".join(
            f"{a.theme} ({a.post_count} posts)" for a in project_context.active_arcs
        )
        sections.append(f"- Active arcs: [{arc_summaries}]")

    if project_context.pending_drafts:
        draft_summaries = ", ".join(
            f"{d.platform}:{d.status}" for d in project_context.pending_drafts
        )
        sections.append(f"- Pending drafts: [{draft_summaries}]")

    # Memories
    if project_context.memories:
        sections.append("\n---\n## Voice Memories")
        for m in project_context.memories[-10:]:  # Last 10 memories
            sections.append(
                f"- {m.get('date', 'N/A')}: {m.get('context', '')} → "
                f"{m.get('feedback', '')}"
            )

    # Context Notes
    if project_context.context_notes:
        sections.append("\n---\n## Context Notes")
        for n in project_context.context_notes[-10:]:  # Last 10 notes
            sections.append(
                f"- [{n.get('date', 'N/A')}] ({n.get('source', 'unknown')}): "
                f"{n.get('note', '')}"
            )

    # Recent history
    sections.append("\n---\n## Recent History")
    if project_context.recent_decisions:
        sections.append("### Recent Decisions")
        for d in project_context.recent_decisions[:config.recent_decisions]:
            sections.append(
                f"- [{d.decision}] {d.commit_hash[:8]}: {d.reasoning[:100]}"
            )
    if project_context.recent_posts:
        sections.append("### Recent Posts")
        for p in project_context.recent_posts[:config.recent_posts]:
            sections.append(f"- [{p.platform}] {p.content[:100]}")

    # Project summary
    if project_context.project_summary:
        sections.append("\n---\n## Project Summary")
        sections.append(project_context.project_summary)

    # Milestone summaries (compacted narrative history)
    if project_context.milestone_summaries:
        sections.append("\n---\n## Milestone Summaries")
        for ms in project_context.milestone_summaries:
            ms_type = ms.get("milestone_type", "milestone")
            ms_text = ms.get("summary", "")
            period = ""
            if ms.get("period_start") and ms.get("period_end"):
                period = f" ({ms['period_start']} to {ms['period_end']})"
            sections.append(f"- [{ms_type}]{period}: {ms_text}")

    # Documentation (T20d: include_readme, include_claude_md, max_doc_tokens)
    if project_context.project.repo_path:
        repo = Path(project_context.project.repo_path)
        if config.include_readme:
            readme_path = repo / "README.md"
            if readme_path.exists():
                readme_text = readme_path.read_text(encoding="utf-8")
                if count_tokens(readme_text) > config.max_doc_tokens:
                    readme_text = (
                        readme_text[: config.max_doc_tokens * 4]
                        + "\n[...truncated]"
                    )
                sections.append("\n---\n## README")
                sections.append(readme_text)
        if config.include_claude_md:
            claude_path = repo / "CLAUDE.md"
            if claude_path.exists():
                claude_text = claude_path.read_text(encoding="utf-8")
                if count_tokens(claude_text) > config.max_doc_tokens:
                    claude_text = (
                        claude_text[: config.max_doc_tokens * 4]
                        + "\n[...truncated]"
                    )
                sections.append("\n---\n## CLAUDE.md")
                sections.append(claude_text)

    # Current commit
    sections.append("\n---\n## Current Commit")
    sections.append(f"- Hash: {commit.hash}")
    sections.append(f"- Message: {commit.message}")
    sections.append(
        f"- Changes: {len(commit.files_changed)} files, "
        f"+{commit.insertions}/-{commit.deletions}"
    )
    if commit.files_changed:
        sections.append(f"- Files: {', '.join(commit.files_changed[:20])}")
    if commit.diff:
        diff_text = commit.diff
        max_diff_tokens = config.max_tokens // 4  # Reserve budget for diff
        if count_tokens(diff_text) > max_diff_tokens:
            diff_text = diff_text[: max_diff_tokens * 4] + "\n[...truncated]"
        sections.append(f"\n### Diff\n```\n{diff_text}\n```")

    result = "\n".join(sections)

    # Apply compaction if over budget
    if count_tokens(result) > config.max_tokens:
        result = compact_by_truncation(result, config.max_tokens)

    return result


def assemble_drafter_prompt(
    prompt: str,
    decision: Any,
    project_context: ProjectContext,
    recent_posts: list[Any],
    commit: CommitInfo,
    arc_context: Optional[dict[str, Any]] = None,
) -> str:
    """Assemble full drafter system prompt with context.

    Per TECH_ARCH L1582-1607: Includes evaluation result, arc context (when
    post_category == 'arc'), recent posts, and commit details.

    Args:
        prompt: Base drafter prompt template
        decision: Evaluation decision (LogDecisionInput or dict)
        project_context: Assembled project state
        recent_posts: Recent posts for voice consistency
        commit: Current commit information
        arc_context: Arc metadata + posts (when post_category == 'arc')

    Returns:
        Complete system prompt string
    """
    sections = [prompt]

    # Project context
    sections.append("\n---\n## Project Context")
    if project_context.social_context:
        sections.append(project_context.social_context)

    # Memories
    if project_context.memories:
        sections.append("\n---\n## Voice Memories")
        for m in project_context.memories[-10:]:
            sections.append(
                f"- {m.get('date', 'N/A')}: {m.get('context', '')} → "
                f"{m.get('feedback', '')}"
            )

    # Context Notes
    if project_context.context_notes:
        sections.append("\n---\n## Context Notes")
        for n in project_context.context_notes[-10:]:
            sections.append(
                f"- [{n.get('date', 'N/A')}] ({n.get('source', 'unknown')}): "
                f"{n.get('note', '')}"
            )

    # Evaluation result
    sections.append("\n---\n## Evaluation Result")
    if hasattr(decision, "decision"):
        sections.append(f"- Decision: {decision.decision}")
        sections.append(f"- Reasoning: {decision.reasoning}")
        if hasattr(decision, "episode_type") and decision.episode_type:
            sections.append(f"- Episode type: {decision.episode_type}")
        if hasattr(decision, "post_category") and decision.post_category:
            sections.append(f"- Post category: {decision.post_category}")
        if hasattr(decision, "media_tool") and decision.media_tool:
            sections.append(f"- Suggested media: {decision.media_tool}")
    elif isinstance(decision, dict):
        for k, v in decision.items():
            if v is not None:
                sections.append(f"- {k}: {v}")

    # Arc context (T20c: when post_category == 'arc')
    if arc_context:
        sections.append("\n---\n## Arc Context")
        if "arc" in arc_context:
            arc = arc_context["arc"]
            sections.append(f"- Theme: {arc.theme}")
            sections.append(f"- Post count: {arc.post_count}")
            if arc.started_at:
                sections.append(f"- Started: {arc.started_at}")
        if "posts" in arc_context:
            sections.append("### Previous Arc Posts")
            for p in arc_context["posts"][:5]:  # Last 5 arc posts
                sections.append(f"- [{p.platform}] {p.content[:100]}")

    # Recent posts
    if recent_posts:
        sections.append("\n---\n## Recent Posts")
        for p in recent_posts[:15]:
            sections.append(f"- [{p.platform}] {p.content[:100]}")

    # Current commit
    sections.append("\n---\n## Current Commit")
    sections.append(f"- Hash: {commit.hash}")
    sections.append(f"- Message: {commit.message}")
    sections.append(
        f"- Changes: {len(commit.files_changed)} files, "
        f"+{commit.insertions}/-{commit.deletions}"
    )
    if commit.diff:
        # Limit diff for drafter (doesn't need full diff)
        diff_text = commit.diff[:8000]
        if len(commit.diff) > 8000:
            diff_text += "\n[...truncated]"
        sections.append(f"\n### Diff\n```\n{diff_text}\n```")

    return "\n".join(sections)


def assemble_gatekeeper_prompt(
    prompt: str,
    draft: Any,
    user_message: str,
    project_summary: Optional[str] = None,
) -> str:
    """Assemble gatekeeper system prompt with minimal context.

    Per TECH_ARCH L1632-1654: Pre-injected project summary, current draft,
    and user message.

    Args:
        prompt: Base gatekeeper prompt template
        draft: Current draft object
        user_message: Telegram message to process
        project_summary: Pre-injected project summary (~500 tokens)

    Returns:
        Complete system prompt string
    """
    sections = [prompt]

    if project_summary:
        sections.append("\n---\n## Project Summary")
        sections.append(project_summary)

    sections.append("\n---\n## Current Draft")
    if hasattr(draft, "content"):
        sections.append(f"- Platform: {draft.platform}")
        sections.append(f"- Content: {draft.content}")
        if hasattr(draft, "suggested_time") and draft.suggested_time:
            sections.append(f"- Suggested time: {draft.suggested_time}")
    elif isinstance(draft, dict):
        for k, v in draft.items():
            if v is not None:
                sections.append(f"- {k}: {v}")

    sections.append("\n---\n## User Message")
    sections.append(user_message)

    return "\n".join(sections)


def assemble_expert_prompt(
    prompt: str,
    draft: Any,
    user_message: str,
    escalation_reason: str,
    escalation_context: Optional[str] = None,
    project_summary: Optional[str] = None,
) -> str:
    """Assemble expert system prompt for escalated requests.

    Per TECH_ARCH L1609-1630: Minimal context — draft + user message +
    escalation info. Does NOT include full project docs.

    Args:
        prompt: Base drafter prompt template (shared with Drafter)
        draft: Current draft object
        user_message: Original Telegram message
        escalation_reason: Why the Gatekeeper escalated
        escalation_context: Additional context from Gatekeeper
        project_summary: Pre-injected project summary

    Returns:
        Complete system prompt string
    """
    sections = [prompt]

    if project_summary:
        sections.append("\n---\n## Project Summary")
        sections.append(project_summary)

    sections.append("\n---\n## Current Draft")
    if hasattr(draft, "content"):
        sections.append(f"- Platform: {draft.platform}")
        sections.append(f"- Content: {draft.content}")
    elif isinstance(draft, dict):
        for k, v in draft.items():
            if v is not None:
                sections.append(f"- {k}: {v}")

    sections.append("\n---\n## User Message")
    sections.append(user_message)

    sections.append("\n---\n## Escalation")
    sections.append(f"Reason: {escalation_reason}")
    if escalation_context:
        sections.append(f"Context: {escalation_context}")

    return "\n".join(sections)


# =============================================================================
# Context Assembly (data-fetching orchestrator)
# =============================================================================


def assemble_evaluator_context(
    db: Any,
    project_id: str,
    project_config: ProjectConfig,
    config: Optional[ContextConfig] = None,
) -> ProjectContext:
    """Gather all DB data into a ProjectContext for agent use.

    Per TECH_ARCH L1785-1810: orchestrates reading from DB + config files.

    Args:
        db: DryRunContext (wraps db.operations; auto-prepends conn)
        project_id: Project ID to assemble context for
        project_config: Loaded project configuration (social_context, memories, etc.)
        config: Context config for limits (defaults to ContextConfig())

    Returns:
        Assembled ProjectContext with all data populated
    """
    if config is None:
        config = ContextConfig()

    project = db.get_project(project_id)
    lifecycle = db.get_lifecycle(project_id)
    active_arcs = db.get_active_arcs(project_id)

    debt = db.get_narrative_debt(project_id)
    narrative_debt = debt.debt_counter if debt else 0

    audience_introduced = db.get_audience_introduced(project_id)
    pending_drafts = db.get_pending_drafts(project_id)
    recent_decisions = db.get_recent_decisions(project_id, limit=config.recent_decisions)
    recent_posts = db.get_recent_posts_for_context(project_id, limit=config.recent_posts)
    project_summary = db.get_project_summary(project_id)
    milestone_summaries = db.get_milestone_summaries(project_id)

    # Parse memories from project config
    memories = []
    if project_config.memories:
        memories = _parse_memories(project_config.memories)

    # Parse context notes from project config
    context_notes = []
    if project_config.context_notes:
        context_notes = _parse_context_notes(project_config.context_notes)

    return ProjectContext(
        project=project,
        social_context=project_config.social_context,
        lifecycle=lifecycle,
        active_arcs=active_arcs,
        narrative_debt=narrative_debt,
        audience_introduced=audience_introduced,
        pending_drafts=pending_drafts,
        recent_decisions=recent_decisions,
        recent_posts=recent_posts,
        project_summary=project_summary,
        memories=memories,
        milestone_summaries=milestone_summaries,
        context_notes=context_notes,
    )


def compact_by_truncation(context: str, max_tokens: int) -> str:
    """Compact context by truncating oldest content first.

    Truncation priority: oldest decisions/posts first, keep summaries.
    This is a simple approach — most projects never trigger it.

    Args:
        context: Full context string
        max_tokens: Target token budget

    Returns:
        Truncated context string
    """
    if count_tokens(context) <= max_tokens:
        return context

    # Simple strategy: truncate from the middle (history section)
    # while preserving the beginning (prompt + current state) and end (commit)
    lines = context.split("\n")

    # Find section boundaries
    history_start = None
    commit_start = None
    for i, line in enumerate(lines):
        if "## Recent History" in line and history_start is None:
            history_start = i
        if "## Current Commit" in line:
            commit_start = i

    if history_start is None or commit_start is None:
        # Can't find sections, just truncate from end
        target_chars = max_tokens * 4
        return context[:target_chars] + "\n[...context truncated]"

    # Keep everything before history, truncate history, keep commit
    pre_history = lines[:history_start]
    post_history = lines[commit_start:]
    history_lines = lines[history_start:commit_start]

    # Progressively remove history lines from oldest (end of list)
    while (
        count_tokens("\n".join(pre_history + history_lines + post_history))
        > max_tokens
        and len(history_lines) > 2  # Keep section header
    ):
        history_lines.pop(-1)

    if len(history_lines) <= 2:
        history_lines.append("[...history truncated for context budget]")

    return "\n".join(pre_history + history_lines + post_history)
