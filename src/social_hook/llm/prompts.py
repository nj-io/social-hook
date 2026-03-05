"""Prompt loading and context assembly for LLM agents (T17)."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

logger = logging.getLogger(__name__)

from social_hook.constants import CONFIG_DIR_NAME, PROJECT_SLUG
from social_hook.config.project import (
    ContextConfig,
    ProjectConfig,
    _parse_context_notes,
    _parse_memories,
)
from social_hook.errors import PromptNotFoundError
from social_hook.models import CommitInfo, ProjectContext

if TYPE_CHECKING:
    from social_hook.config.project import MediaToolGuidance, StrategyConfig, SummaryConfig
    from social_hook.config.yaml import MediaGenerationConfig


def _relative_time(dt) -> str:
    """Format a datetime as a human-readable relative time string."""
    if not dt:
        return "unknown"
    from datetime import datetime, timezone
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - dt
    days = delta.days
    if days > 30:
        return f"{days // 30}mo ago"
    if days > 0:
        return f"{days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    return "just now"


def _render_narrative_sections(sections: list[str], narratives: list[dict]) -> None:
    """Append Development Narrative sections to the prompt if narratives exist."""
    if not narratives:
        return
    sections.append("\n---\n## Development Narrative")
    for n in narratives[:5]:  # Budget: ~2000 tokens
        in_window = n.get("_in_window", True)
        label = "" if in_window else " (earlier context)"
        sections.append(f"\n### Session: {n.get('summary', 'No summary')}{label}")
        if n.get('key_decisions'):
            sections.append("**Key decisions:** " + "; ".join(n['key_decisions'][:3]))
        if n.get('rejected_approaches'):
            sections.append("**Rejected approaches:** " + "; ".join(n['rejected_approaches'][:3]))
        if n.get('aha_moments'):
            sections.append("**Insights:** " + "; ".join(n['aha_moments'][:3]))
        if n.get('social_hooks'):
            sections.append("**Post angles:** " + "; ".join(n['social_hooks'][:3]))


def load_prompt(role: str) -> str:
    """Load a prompt template from ~/.social-hook/prompts/{role}.md.

    Args:
        role: Agent role name (evaluator, drafter, gatekeeper)

    Returns:
        Prompt template content

    Raises:
        PromptNotFoundError: If prompt file does not exist
    """
    prompt_path = Path.home() / CONFIG_DIR_NAME / "prompts" / f"{role}.md"
    if not prompt_path.exists():
        raise PromptNotFoundError(
            f"Prompt file not found: {prompt_path}. "
            f"Run '{PROJECT_SLUG} setup' to create default prompts."
        )
    return prompt_path.read_text(encoding="utf-8")


def count_tokens(text: str) -> int:
    """Approximate token count for text.

    Uses chars/4 heuristic. Sufficient for context budgeting.
    """
    return len(text) // 4


def _get_enabled_tools(
    media_config: Optional["MediaGenerationConfig"],
    media_guidance: Optional[dict[str, "MediaToolGuidance"]],
) -> list[tuple[str, Optional["MediaToolGuidance"]]]:
    """Return list of (tool_name, guidance_or_None) for enabled tools only.

    A tool is enabled if media_config.tools[name] is True.
    Disabled tools are omitted even if guidance exists.
    """
    if media_config is None:
        return []
    if not media_config.enabled:
        return []

    result = []
    for tool_name, enabled in media_config.tools.items():
        if not enabled:
            continue
        guidance = media_guidance.get(tool_name) if media_guidance else None
        result.append((tool_name, guidance))
    return result


def _append_media_tools_section(
    sections: list[str],
    media_config: Optional["MediaGenerationConfig"],
    media_guidance: Optional[dict[str, "MediaToolGuidance"]],
) -> None:
    """Append '## Available Media Tools' section to evaluator prompt."""
    tools = _get_enabled_tools(media_config, media_guidance)
    if not tools:
        return

    sections.append("\n---\n## Available Media Tools")
    for tool_name, guidance in tools:
        if guidance and (guidance.use_when or guidance.constraints):
            sections.append(f"\n### {tool_name}")
            if guidance.use_when:
                sections.append("**Use when:** " + "; ".join(guidance.use_when))
            if guidance.constraints:
                sections.append("**Constraints:** " + "; ".join(guidance.constraints))
        else:
            sections.append(f"- {tool_name}")


def _append_media_guide_section(
    sections: list[str],
    media_config: Optional["MediaGenerationConfig"],
    media_guidance: Optional[dict[str, "MediaToolGuidance"]],
) -> None:
    """Append '## Media Tool Guide' section to drafter prompt."""
    tools = _get_enabled_tools(media_config, media_guidance)
    if not tools:
        return

    sections.append("\n---\n## Media Tool Guide")
    for tool_name, guidance in tools:
        if guidance and (guidance.use_when or guidance.constraints or guidance.prompt_example):
            sections.append(f"\n### {tool_name}")
            if guidance.use_when:
                sections.append("**Use when:** " + "; ".join(guidance.use_when))
            if guidance.constraints:
                sections.append("**Constraints:** " + "; ".join(guidance.constraints))
            if guidance.prompt_example:
                sections.append(f"**Prompt example:** {guidance.prompt_example}")
        else:
            sections.append(f"- {tool_name}")


def assemble_evaluator_prompt(
    prompt: str,
    project_context: ProjectContext,
    commit: CommitInfo,
    config: Optional[ContextConfig] = None,
    platform_summaries: Optional[list[str]] = None,
    media_config: Optional["MediaGenerationConfig"] = None,
    media_guidance: Optional[dict[str, "MediaToolGuidance"]] = None,
    strategy_config: Optional["StrategyConfig"] = None,
    summary_config: Optional["SummaryConfig"] = None,
) -> str:
    """Assemble full evaluator system prompt with context.

    Per TECH_ARCH L1553-1580: Includes lifecycle, arcs, debt, pending drafts,
    recent history, and commit details.

    Args:
        prompt: Base evaluator prompt template
        project_context: Assembled project state
        commit: Current commit information
        config: Context config for limits
        platform_summaries: Platform summary strings for context
        media_config: Media generation config (enabled tools)
        media_guidance: Per-tool content guidance
        strategy_config: Strategy thresholds (portfolio window, episode prefs)
        summary_config: Summary refresh thresholds

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
        cap = getattr(config, 'pending_drafts_cap', 10)
        to_show = project_context.pending_drafts[:cap]
        overflow = len(project_context.pending_drafts) - cap
        detail = getattr(config, 'pending_draft_detail', 'full_content')
        if detail == "full_content":
            sections.append("### Pending Drafts")
            for d in to_show:
                intro = " [INTRO]" if getattr(d, 'is_intro', False) else ""
                sections.append(f"- [{d.platform}:{d.status}]{intro}: {d.content}")
            if overflow > 0:
                sections.append(f"  (+{overflow} older drafts)")
        else:
            summaries = ", ".join(f"{d.platform}:{d.status}" for d in to_show)
            sections.append(f"- Pending drafts: [{summaries}]")

    if project_context.held_decisions:
        max_hold = config.max_hold_count if hasattr(config, 'max_hold_count') else 5
        sections.append("\n---\n## Held Commits")
        sections.append(f"Commits held for consolidation ({len(project_context.held_decisions)}/{max_hold} slots).")
        sections.append("For each: consolidate into this draft via `consolidate_with`, keep holding, or let drop.")
        for d in project_context.held_decisions:
            summary = d.commit_summary or d.commit_message or d.commit_hash[:8]
            sections.append(f"- [id={d.id}] {d.commit_hash[:8]}: {summary} (held {_relative_time(d.created_at)})")

    # Target platforms
    if platform_summaries:
        sections.append("\n---\n## Target Platforms")
        for ps in platform_summaries:
            sections.append(f"- {ps}")
        sections.append(
            "\nNote: Your decision applies globally. Per-platform content filtering "
            "is handled downstream. Focus on whether this commit is worth sharing."
        )

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

    # Development Narrative (from journey capture)
    _render_narrative_sections(sections, project_context.session_narratives)

    # Recent history
    sections.append("\n---\n## Recent History")
    if project_context.recent_decisions:
        sections.append("### Recent Decisions")
        for d in project_context.recent_decisions[:config.recent_decisions]:
            sections.append(
                f"- [{d.decision}] {d.commit_hash[:8]} \"{d.commit_message or 'N/A'}\": {d.reasoning[:100]}"
            )
    if project_context.recent_posts:
        sections.append("### Post History")
        for p in project_context.recent_posts[:config.recent_posts]:
            url_part = f", {p.external_url}" if p.external_url else ""
            time_ago = _relative_time(p.posted_at)
            sections.append(f"- {p.platform} [id={p.id}]: {p.content[:80]}... ({time_ago}{url_part})")

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

    # Available media tools (dynamic, from config)
    _append_media_tools_section(sections, media_config, media_guidance)

    # Strategy config
    if strategy_config:
        strategy_lines = []
        if strategy_config.portfolio_window:
            strategy_lines.append(
                f"- Consider last {strategy_config.portfolio_window} posts for variety"
            )
        if strategy_config.episode_preferences:
            if strategy_config.episode_preferences.favor:
                strategy_lines.append(
                    f"- Favored episode types: {', '.join(strategy_config.episode_preferences.favor)}"
                )
            if strategy_config.episode_preferences.avoid:
                strategy_lines.append(
                    f"- Avoid episode types: {', '.join(strategy_config.episode_preferences.avoid)}"
                )
        if strategy_lines:
            sections.append("\n---\n## Strategy Preferences")
            sections.extend(strategy_lines)

    # Summary freshness thresholds
    if summary_config:
        sections.append("\n---\n## Summary Freshness Thresholds")
        sections.append(
            f"- Refresh after {summary_config.refresh_after_commits} commits"
        )
        sections.append(
            f"- Refresh after {summary_config.refresh_after_days} days"
        )

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
    config: Optional["ContextConfig"] = None,
    media_config: Optional["MediaGenerationConfig"] = None,
    media_guidance: Optional[dict[str, "MediaToolGuidance"]] = None,
) -> str:
    """Assemble full drafter system prompt with context.

    Per TECH_ARCH L1582-1607: Includes evaluation result, arc context (when
    post_category == 'arc'), recent posts, and commit details.

    When audience_introduced=false, also includes project documentation
    (README, CLAUDE.md) so the drafter can write a proper introduction.

    Args:
        prompt: Base drafter prompt template
        decision: Evaluation decision (evaluation result or dict)
        project_context: Assembled project state
        recent_posts: Recent posts for voice consistency
        commit: Current commit information
        arc_context: Arc metadata + posts (when post_category == 'arc')
        config: Context config for doc inclusion limits
        media_config: Media generation config (enabled tools)
        media_guidance: Per-tool content guidance

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

    # Current state — audience introduction status
    sections.append("\n---\n## Current State")
    sections.append(
        f"- Audience introduced: {project_context.audience_introduced}"
    )
    if not project_context.audience_introduced:
        sections.append(
            "- **THIS IS THE FIRST POST FOR THIS PROJECT.** "
            "The audience does not know what this project is yet. "
            "You must write an introductory post that explains what the "
            "project does, what problem it solves, and why it matters — "
            "not just what this commit changed."
        )

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

    # Development Narrative (from journey capture)
    _render_narrative_sections(sections, project_context.session_narratives)

    # Project documentation — included when the evaluator requests it
    # (include_project_docs=true) or when audience hasn't been introduced yet.
    include_docs = not project_context.audience_introduced
    if hasattr(decision, "include_project_docs") and decision.include_project_docs:
        include_docs = True
    elif isinstance(decision, dict) and decision.get("include_project_docs"):
        include_docs = True

    if include_docs and project_context.project.repo_path:
        repo = Path(project_context.project.repo_path)

        # When audience hasn't been introduced and discovery files exist,
        # load those files instead of just README+CLAUDE.md for deeper
        # project understanding in first posts.
        discovery_files_loaded = False
        if not project_context.audience_introduced and project_context.project.discovery_files:
            try:
                import json as _json
                disc_files = _json.loads(project_context.project.discovery_files)
                if disc_files:
                    sections.append("\n---\n## Project Documentation (Discovery)")
                    tokens_used = 0
                    for rel_path in disc_files:
                        fpath = repo / rel_path
                        if not fpath.exists() or not fpath.is_file():
                            continue
                        try:
                            content = fpath.read_text(encoding="utf-8", errors="replace")
                            file_tokens = count_tokens(content)
                            if tokens_used + file_tokens > config.max_doc_tokens:
                                remaining = config.max_doc_tokens - tokens_used
                                if remaining > 100:
                                    content = content[:remaining * 4] + "\n[...truncated]"
                                    sections.append(f"\n### {rel_path}")
                                    sections.append(content)
                                break
                            sections.append(f"\n### {rel_path}")
                            sections.append(content)
                            tokens_used += file_tokens
                        except (OSError, UnicodeDecodeError):
                            continue
                    discovery_files_loaded = True
            except (ValueError, TypeError):
                pass

        # Fallback to README + CLAUDE.md when no discovery files loaded
        if not discovery_files_loaded:
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

    # Project summary
    if project_context.project_summary:
        sections.append("\n---\n## Project Summary")
        sections.append(project_context.project_summary)

    # Evaluation result
    sections.append("\n---\n## Evaluation Result")
    if hasattr(decision, "decision"):
        sections.append(f"- Decision: {decision.decision}")
        sections.append(f"- Reasoning: {decision.reasoning}")
        if hasattr(decision, "angle") and decision.angle:
            sections.append(f"- Angle: {decision.angle}")
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
            arc_char_limit = getattr(config, 'arc_context_chars', 500) if config else 500
            for p in arc_context["posts"][:5]:
                url_part = f" | url: {p.external_url}" if p.external_url else ""
                sections.append(f"- [id={p.id}] [{p.platform}]{url_part}: {p.content[:arc_char_limit]}")

    # Recent posts
    if recent_posts:
        sections.append("\n---\n## Recent Posts")
        for p in recent_posts[:15]:
            sections.append(f"- [{p.platform}] {p.content[:100]}")

    # Media tool guide (dynamic, from config)
    _append_media_guide_section(sections, media_config, media_guidance)

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
    system_snapshot: Optional[str] = None,
    chat_history: Optional[str] = None,
    recent_decisions: Optional[list[Any]] = None,
    recent_posts: Optional[list[Any]] = None,
    lifecycle_phase: Optional[str] = None,
    active_arcs: Optional[list[Any]] = None,
    narrative_debt: Optional[int] = None,
    audience_introduced: Optional[bool] = None,
    linked_decision: Optional[Any] = None,
) -> str:
    """Assemble gatekeeper system prompt with enriched context.

    Per TECH_ARCH: Pre-injected project summary, current draft,
    and user message, plus enriched project state for better routing.

    Args:
        prompt: Base gatekeeper prompt template
        draft: Current draft object
        user_message: Telegram message to process
        project_summary: Pre-injected project summary (~500 tokens)
        system_snapshot: Compact system status block (live DB + config data)
        chat_history: Recent chat messages for conversational context
        recent_decisions: Recent evaluation decisions for context
        recent_posts: Recent published posts for context
        lifecycle_phase: Current project lifecycle phase
        active_arcs: Active narrative arcs
        narrative_debt: Current narrative debt counter
        audience_introduced: Whether audience has been introduced
        linked_decision: Decision linked to the current draft

    Returns:
        Complete system prompt string
    """
    sections = [prompt]

    if system_snapshot:
        sections.append("\n---\n" + system_snapshot)

    # Project State section (between snapshot and summary)
    state_lines = []
    if lifecycle_phase is not None:
        state_lines.append(f"- Lifecycle phase: {lifecycle_phase}")
    if audience_introduced is not None:
        state_lines.append(f"- Audience introduced: {audience_introduced}")
    if narrative_debt is not None:
        state_lines.append(f"- Narrative debt: {narrative_debt}")
    if state_lines:
        sections.append("\n---\n## Project State")
        sections.extend(state_lines)

    # Active Arcs
    if active_arcs:
        sections.append("\n---\n## Active Arcs")
        for arc in active_arcs:
            theme = arc.theme if hasattr(arc, "theme") else str(arc)
            post_count = arc.post_count if hasattr(arc, "post_count") else 0
            sections.append(f'- "{theme}" ({post_count} posts)')

    # Recent Decisions
    if recent_decisions:
        sections.append("\n---\n## Recent Decisions (last %d)" % len(recent_decisions))
        for d in recent_decisions:
            decision = d.decision if hasattr(d, "decision") else d.get("decision", "?")
            commit_hash = d.commit_hash[:8] if hasattr(d, "commit_hash") else "?"
            msg = d.commit_message or "N/A" if hasattr(d, "commit_message") else d.get("commit_message", "N/A")
            reasoning = d.reasoning[:80] if hasattr(d, "reasoning") else str(d.get("reasoning", ""))[:80]
            sections.append(f"- [{decision}] {commit_hash}: {msg} — {reasoning}")

    # Recent Posts
    if recent_posts:
        sections.append("\n---\n## Recent Posts (last %d)" % len(recent_posts))
        for p in recent_posts:
            platform = p.platform if hasattr(p, "platform") else p.get("platform", "?")
            content = p.content[:100] if hasattr(p, "content") else str(p.get("content", ""))[:100]
            sections.append(f"- [{platform}] {content}")

    if project_summary:
        sections.append("\n---\n## Project Summary")
        sections.append(project_summary)

    if chat_history:
        sections.append("\n---\n" + chat_history)

    # Linked Decision (for current draft)
    if linked_decision:
        sections.append("\n---\n## Linked Decision (for current draft)")
        reasoning = linked_decision.reasoning if hasattr(linked_decision, "reasoning") else linked_decision.get("reasoning", "")
        sections.append(f"- Reasoning: {reasoning[:200]}")
        angle = linked_decision.angle if hasattr(linked_decision, "angle") else linked_decision.get("angle")
        if angle:
            sections.append(f"- Angle: {angle}")
        episode_type = linked_decision.episode_type if hasattr(linked_decision, "episode_type") else linked_decision.get("episode_type")
        if episode_type:
            sections.append(f"- Episode type: {episode_type}")

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
    commit_timestamp: Optional[str] = None,
    parent_timestamp: Optional[str] = None,
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
    held_decisions = db.get_held_decisions(project_id, limit=20)
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

    # Load session narratives from journey capture storage
    try:
        from social_hook.narrative.storage import load_recent_narratives
        session_narratives = load_recent_narratives(
            project_id, limit=5,
            after=parent_timestamp,
            before=commit_timestamp,
        )
    except Exception:
        logger.debug("Failed to load narratives for %s", project_id, exc_info=True)
        session_narratives = []

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
        session_narratives=session_narratives,
        held_decisions=held_decisions,
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
