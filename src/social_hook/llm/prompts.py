"""Prompt loading and context assembly for LLM agents (T17)."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

logger = logging.getLogger(__name__)

from social_hook.config.project import (
    ContextConfig,
    ProjectConfig,
    _parse_context_notes,
    _parse_memories,
)
from social_hook.constants import CONFIG_DIR_NAME, PROJECT_SLUG
from social_hook.errors import PromptNotFoundError
from social_hook.models import CommitInfo, ProjectContext
from social_hook.scheduling import ProjectSchedulingState

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
        if n.get("key_decisions"):
            sections.append("**Key decisions:** " + "; ".join(n["key_decisions"][:3]))
        if n.get("rejected_approaches"):
            sections.append("**Rejected approaches:** " + "; ".join(n["rejected_approaches"][:3]))
        if n.get("aha_moments"):
            sections.append("**Insights:** " + "; ".join(n["aha_moments"][:3]))
        if n.get("social_hooks"):
            sections.append("**Post angles:** " + "; ".join(n["social_hooks"][:3]))


_BUNDLED_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _build_identity_instruction(
    identity: Any,
    target_post_count: int = 0,
    is_first_post: bool = False,
    first_post_date: str | None = None,
) -> str:
    """Build an Author Identity section for drafter/expert prompts.

    Passes raw data (post count, first post flag, date) — the LLM
    decides how to use intro hooks based on audience familiarity.

    Args:
        identity: IdentityConfig or None
        target_post_count: Posts published on this platform
        is_first_post: Whether this is the first post on this platform
        first_post_date: ISO date of earliest post on this platform

    Returns:
        Identity instruction string, or "" if no identity configured
    """
    if identity is None:
        return ""
    pronoun_map = {
        "myself": "first person singular (I, me, my)",
        "team": "first person plural (we, our, us)",
        "company": "first person plural as the company (we, our, us)",
        "project": "third person or project voice (it, the project)",
    }
    label = getattr(identity, "label", "") or ""
    id_type = getattr(identity, "type", "myself") or "myself"
    description = getattr(identity, "description", None)
    intro_hook = getattr(identity, "intro_hook", None)

    pronouns = pronoun_map.get(id_type, f"the voice of: {label}")

    sections = [
        "\n## Author Identity\n",
        f"**Identity**: {label}\n",
    ]
    if description:
        sections.append(f"**About**: {description}\n")
    sections.append(
        f"**Perspective**: Write using {pronouns}. "
        f"Maintain this perspective consistently throughout all content.\n"
    )

    if intro_hook:
        sections.append(
            f'\n**Intro hook**: "{intro_hook}"\n'
            f"Posts published on this platform/target: {target_post_count}. "
            f"First post: {'yes' if is_first_post else 'no'}. "
            f"Posting since: {first_post_date or 'N/A'}.\n"
            f"Use the intro hook naturally — prominently in early posts, "
            f"fading as the audience becomes familiar. Don't repeat it verbatim across posts.\n"
        )

    return "\n".join(sections)


def load_prompt(role: str) -> str:
    """Load a prompt template for an agent role.

    Search order: user prompts (~/.social-hook/prompts/{role}.md),
    then bundled prompts (src/social_hook/prompts/{role}.md).

    Args:
        role: Agent role name (evaluator, drafter, gatekeeper)

    Returns:
        Prompt template content

    Raises:
        PromptNotFoundError: If prompt file does not exist in either location
    """
    user_path = Path.home() / CONFIG_DIR_NAME / "prompts" / f"{role}.md"
    if user_path.exists():
        return user_path.read_text(encoding="utf-8")

    bundled_path = _BUNDLED_PROMPTS_DIR / f"{role}.md"
    if bundled_path.exists():
        return bundled_path.read_text(encoding="utf-8")

    raise PromptNotFoundError(
        f"Prompt file not found: {user_path}. Run '{PROJECT_SLUG} setup' to create default prompts."
    )


def count_tokens(text: str) -> int:
    """Approximate token count for text.

    Uses chars/4 heuristic. Sufficient for context budgeting.
    """
    return len(text) // 4


def _get_enabled_tools(
    media_config: Optional["MediaGenerationConfig"],
    media_guidance: dict[str, "MediaToolGuidance"] | None,
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
    media_guidance: dict[str, "MediaToolGuidance"] | None,
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


_MEDIA_SPEC_FIELDS = {
    "ray_so": "Required spec fields: code (string). Optional: language, title.",
    "mermaid": "Required spec fields: diagram (mermaid markup string).",
    "nano_banana_pro": "Required spec fields: prompt (image description string).",
    "playwright": "Required spec fields: url (string). Optional: selector.",
}


def _append_media_guide_section(
    sections: list[str],
    media_config: Optional["MediaGenerationConfig"],
    media_guidance: dict[str, "MediaToolGuidance"] | None,
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
            spec_info = _MEDIA_SPEC_FIELDS.get(tool_name)
            if spec_info:
                sections.append(f"**Spec fields:** {spec_info}")
        else:
            sections.append(f"- {tool_name}")
            spec_info = _MEDIA_SPEC_FIELDS.get(tool_name)
            if spec_info:
                sections.append(f"  **Spec fields:** {spec_info}")


def assemble_evaluator_prompt(
    prompt: str,
    project_context: ProjectContext,
    commit: CommitInfo,
    config: ContextConfig | None = None,
    platform_summaries: list[str] | None = None,
    media_config: Optional["MediaGenerationConfig"] = None,
    media_guidance: dict[str, "MediaToolGuidance"] | None = None,
    strategy_config: Optional["StrategyConfig"] = None,
    summary_config: Optional["SummaryConfig"] = None,
    scheduling_state: ProjectSchedulingState | None = None,
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
        scheduling_state: Per-platform scheduling capacity snapshot

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
        sections.append(f"- Lifecycle phase: {lc.phase} (confidence: {lc.confidence})")
    sections.append(f"- Narrative debt: {project_context.narrative_debt}")
    if project_context.platform_introduced:
        intro_items = ", ".join(
            f"{p}: {'yes' if v else 'no'}" for p, v in project_context.platform_introduced.items()
        )
        sections.append(f"- Platform introduced: {{{intro_items}}}")
    else:
        sections.append(f"- Platform introduced: {project_context.all_introduced}")

    if project_context.active_arcs:
        sections.append("### Active Arcs")
        for a in project_context.active_arcs:
            sections.append(
                f"- [id={a.id}] {a.theme} ({a.post_count} posts, "
                f"last post {_relative_time(a.last_post_at)})"
            )
            # Show recent posts in this arc so evaluator can reference them
            arc_post_list = project_context.arc_posts.get(a.id, [])
            for p in arc_post_list:
                url_part = f", {p.external_url}" if p.external_url else ""
                sections.append(
                    f"  - {p.platform} [id={p.id}]: {p.content[:500]}... "
                    f"({_relative_time(p.posted_at)}{url_part})"
                )

    if project_context.pending_drafts:
        cap = getattr(config, "pending_drafts_cap", 10)
        to_show = project_context.pending_drafts[:cap]
        overflow = len(project_context.pending_drafts) - cap
        detail = getattr(config, "pending_draft_detail", "full_content")
        if detail == "full_content":
            sections.append("### Pending Drafts")
            for d in to_show:
                intro = " [INTRO]" if getattr(d, "is_intro", False) else ""
                sections.append(f"- [id={d.id}][{d.platform}:{d.status}]{intro}: {d.content}")
            if overflow > 0:
                sections.append(f"  (+{overflow} older drafts)")
        else:
            summaries = ", ".join(f"{d.id}:{d.platform}:{d.status}" for d in to_show)
            sections.append(f"- Pending drafts: [{summaries}]")

    if project_context.held_decisions:
        max_hold = config.max_hold_count if hasattr(config, "max_hold_count") else 5
        sections.append("\n---\n## Held Commits")
        sections.append(
            f"Commits held for consolidation ({len(project_context.held_decisions)}/{max_hold} slots)."
        )
        sections.append(
            "For each: consolidate into this draft via `consolidate_with`, keep holding, or let drop."
        )
        for hd in project_context.held_decisions:
            summary = hd.commit_summary or hd.commit_message or hd.commit_hash[:8]
            sections.append(
                f"- [id={hd.id}] {hd.commit_hash[:8]}: {summary} (held {_relative_time(hd.created_at)})"
            )

    # Target platforms
    if platform_summaries:
        sections.append("\n---\n## Target Platforms")
        for ps in platform_summaries:
            sections.append(f"- {ps}")
        sections.append(
            "\nYour action (draft/hold/skip) applies to all platforms. The Scheduling State "
            "section shows per-platform capacity for awareness. Per-platform content "
            "filtering is handled downstream."
        )

    # Scheduling State
    if scheduling_state:
        sections.append("\n---\n## Scheduling State")
        if scheduling_state.max_per_week is not None:
            sections.append(
                f"Project weekly limit: {scheduling_state.weekly_posts}/{scheduling_state.max_per_week} "
                f"posts (this project, shared across all platforms)"
            )
        else:
            sections.append(f"Project weekly posts: {scheduling_state.weekly_posts} (no limit set)")
        for pss in scheduling_state.platform_states:
            sections.append(f"\n### {pss.platform}")
            sections.append(
                f"- Today (all projects): {pss.posts_today}/{pss.max_posts_per_day} posts, "
                f"Slots remaining: ~{pss.slots_remaining_today}"
            )
            deferred_part = f", Deferred: {pss.deferred_drafts}" if pss.deferred_drafts else ""
            sections.append(f"- Pending drafts: {pss.pending_drafts}{deferred_part}")
            if pss.pending_drafts > pss.slots_remaining_today:
                sections.append(
                    f"- NOTE: {pss.pending_drafts} pending drafts for ~{pss.slots_remaining_today} "
                    f"slot(s) today. Review pending drafts for overlap — merge redundant ones."
                )

    # Memories
    if project_context.memories:
        sections.append("\n---\n## Voice Memories")
        for m in project_context.memories[-10:]:  # Last 10 memories
            sections.append(
                f"- {m.get('date', 'N/A')}: {m.get('context', '')} → {m.get('feedback', '')}"
            )

    # Context Notes
    if project_context.context_notes:
        sections.append("\n---\n## Context Notes")
        for n in project_context.context_notes[-10:]:  # Last 10 notes
            sections.append(
                f"- [{n.get('date', 'N/A')}] ({n.get('source', 'unknown')}): {n.get('note', '')}"
            )

    # Development Narrative (from journey capture)
    _render_narrative_sections(sections, project_context.session_narratives)

    # Recent history
    sections.append("\n---\n## Recent History")
    if project_context.recent_decisions:
        sections.append("### Recent Decisions")
        for dec in project_context.recent_decisions[: config.recent_decisions]:
            sections.append(
                f'- [{dec.decision}] {dec.commit_hash[:8]} "{dec.commit_message or "N/A"}": {dec.reasoning[:100]}'
            )
    if project_context.recent_posts:
        sections.append("### Post History")
        for p in project_context.recent_posts[: config.recent_posts]:
            url_part = f", {p.external_url}" if p.external_url else ""
            time_ago = _relative_time(p.posted_at)
            sections.append(
                f"- {p.platform} [id={p.id}]: {p.content[:500]}... ({time_ago}{url_part})"
            )

    # Project summary
    if project_context.project_summary:
        sections.append("\n---\n## Project Summary")
        sections.append(project_context.project_summary)

    # Commit-relevant file context
    if project_context.file_summaries and commit.files_changed:
        changed_dirs = {fp.rsplit("/", 1)[0] + "/" for fp in commit.files_changed if "/" in fp}
        changed_exact = set(commit.files_changed)

        relevant = [
            fs
            for fs in project_context.file_summaries
            if fs["path"] in changed_exact or any(fs["path"].startswith(d) for d in changed_dirs)
        ]
        if relevant:
            sections.append("\n---\n## Relevant File Context")
            for fs in relevant[:20]:
                sections.append(f"- **{fs['path']}**: {fs['summary']}")

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

    # Project documentation — LLM-selected during discovery
    if project_context.project.repo_path and project_context.project.prompt_docs:
        import json as _json

        try:
            doc_paths = _json.loads(project_context.project.prompt_docs)
        except (ValueError, TypeError):
            doc_paths = []
        if doc_paths:
            repo = Path(project_context.project.repo_path)
            sections.append("\n---\n## Project Documentation")
            tokens_used = 0
            for rel_path in doc_paths:
                fpath = repo / rel_path
                if not fpath.exists() or not fpath.is_file():
                    continue
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    file_tokens = count_tokens(content)
                    if tokens_used + file_tokens > config.max_doc_tokens:
                        remaining = config.max_doc_tokens - tokens_used
                        if remaining > 100:
                            content = content[: remaining * 4] + "\n[...truncated]"
                            sections.append(f"\n### {rel_path}")
                            sections.append(content)
                        break
                    sections.append(f"\n### {rel_path}")
                    sections.append(content)
                    tokens_used += file_tokens
                except (OSError, UnicodeDecodeError):
                    continue

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
        sections.append(f"- Refresh after {summary_config.refresh_after_commits} commits")
        sections.append(f"- Refresh after {summary_config.refresh_after_days} days")

    # Current commit
    sections.append("\n---\n## Current Commit")
    sections.append(f"- Hash: {commit.hash}")
    sections.append(f"- Message: {commit.message}")
    sections.append(
        f"- Changes: {len(commit.files_changed)} files, +{commit.insertions}/-{commit.deletions}"
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
    arc_context: dict[str, Any] | None = None,
    config: Optional["ContextConfig"] = None,
    media_config: Optional["MediaGenerationConfig"] = None,
    media_guidance: dict[str, "MediaToolGuidance"] | None = None,
    referenced_posts: list | None = None,
    platform_name: str | None = None,
    identity: Any | None = None,
    target_post_count: int = 0,
    is_first_post: bool = False,
    first_post_date: str | None = None,
) -> str:
    """Assemble full drafter system prompt with context.

    Per TECH_ARCH L1582-1607: Includes evaluation result, arc context (when
    post_category == 'arc'), recent posts, and commit details.

    When platform not yet introduced, also includes project documentation
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
        referenced_posts: Evaluator-identified relevant posts
        platform_name: Current target platform name
        identity: Resolved IdentityConfig for this platform
        target_post_count: Posts published on this platform
        is_first_post: Whether this is the first post on this platform
        first_post_date: Earliest posted_at for this platform

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

    # Current state — per-platform introduction status
    platform_introduced = (
        project_context.platform_introduced.get(platform_name, False)
        if platform_name
        else project_context.all_introduced
    )
    sections.append("\n---\n## Current State")
    if project_context.platform_introduced:
        intro_items = ", ".join(
            f"{p}: {'yes' if v else 'no'}" for p, v in project_context.platform_introduced.items()
        )
        sections.append(f"- Platform introduced: {{{intro_items}}}")
    else:
        sections.append(f"- Platform introduced: {platform_introduced}")
    if not platform_introduced:
        sections.append(
            "- **THIS IS THE FIRST POST FOR THIS PROJECT ON THIS PLATFORM.** "
            "The audience does not know what this project is yet. "
            "You must write an introductory post that explains what the "
            "project does, what problem it solves, and why it matters — "
            "not just what this commit changed."
        )

    # Author Identity (after social context, before discovery-injected sections)
    identity_section = _build_identity_instruction(
        identity, target_post_count, is_first_post, first_post_date
    )
    if identity_section:
        sections.append(identity_section)

    # Memories
    if project_context.memories:
        sections.append("\n---\n## Voice Memories")
        for m in project_context.memories[-10:]:
            sections.append(
                f"- {m.get('date', 'N/A')}: {m.get('context', '')} → {m.get('feedback', '')}"
            )

    # Context Notes
    if project_context.context_notes:
        sections.append("\n---\n## Context Notes")
        for n in project_context.context_notes[-10:]:
            sections.append(
                f"- [{n.get('date', 'N/A')}] ({n.get('source', 'unknown')}): {n.get('note', '')}"
            )

    # Development Narrative (from journey capture)
    _render_narrative_sections(sections, project_context.session_narratives)

    # Project documentation — included when the evaluator requests it
    # (include_project_docs=true) or when platform hasn't been introduced yet.
    include_docs = not platform_introduced
    if (
        hasattr(decision, "include_project_docs")
        and decision.include_project_docs
        or isinstance(decision, dict)
        and decision.get("include_project_docs")
    ):
        include_docs = True

    if include_docs and project_context.project.repo_path:
        repo = Path(project_context.project.repo_path)

        # When audience hasn't been introduced and discovery files exist,
        # load those files instead of just README+CLAUDE.md for deeper
        # project understanding in first posts.
        discovery_files_loaded = False
        if not platform_introduced and project_context.project.discovery_files:
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
                                    content = content[: remaining * 4] + "\n[...truncated]"
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

        # Fallback to prompt_docs when no discovery files loaded
        if not discovery_files_loaded and project_context.project.prompt_docs:
            import json as _json

            try:
                doc_paths = _json.loads(project_context.project.prompt_docs)
            except (ValueError, TypeError):
                doc_paths = []
            if doc_paths:
                sections.append("\n---\n## Project Documentation")
                tokens_used = 0
                for rel_path in doc_paths:
                    fpath = repo / rel_path
                    if not fpath.exists() or not fpath.is_file():
                        continue
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="replace")
                        file_tokens = count_tokens(content)
                        if tokens_used + file_tokens > config.max_doc_tokens:
                            remaining = config.max_doc_tokens - tokens_used
                            if remaining > 100:
                                content = content[: remaining * 4] + "\n[...truncated]"
                                sections.append(f"\n### {rel_path}")
                                sections.append(content)
                            break
                        sections.append(f"\n### {rel_path}")
                        sections.append(content)
                        tokens_used += file_tokens
                    except (OSError, UnicodeDecodeError):
                        continue

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
            arc_char_limit = getattr(config, "arc_context_chars", 500) if config else 500
            for p in arc_context["posts"][:5]:
                url_part = f" | url: {p.external_url}" if p.external_url else ""
                sections.append(
                    f"- [id={p.id}] [{p.platform}]{url_part}: {p.content[:arc_char_limit]}"
                )

    # Referenced posts (evaluator-identified relevant previous posts)
    if referenced_posts:
        sections.append("\n---\n## Referenced Posts")
        sections.append(
            "The evaluator identified these previous posts as relevant. Reference them naturally."
        )
        ref_char_limit = getattr(config, "arc_context_chars", 500) if config else 500
        for p in referenced_posts:
            url_part = f" (url: {p.external_url})" if getattr(p, "external_url", None) else ""
            time_ago = _relative_time(getattr(p, "posted_at", None))
            content_preview = getattr(p, "content", "")[:ref_char_limit]
            sections.append(
                f'- [{getattr(p, "platform", "?")}]{url_part}: "{content_preview}" ({time_ago})'
            )

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
        f"- Changes: {len(commit.files_changed)} files, +{commit.insertions}/-{commit.deletions}"
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
    project_summary: str | None = None,
    system_snapshot: str | None = None,
    chat_history: str | None = None,
    recent_decisions: list[Any] | None = None,
    recent_posts: list[Any] | None = None,
    lifecycle_phase: str | None = None,
    active_arcs: list[Any] | None = None,
    narrative_debt: int | None = None,
    audience_introduced: bool | None = None,
    linked_decision: Any | None = None,
    social_context: str | None = None,
    platform_introduced: dict[str, bool] | None = None,
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
        audience_introduced: Whether audience has been introduced (deprecated, use platform_introduced)
        linked_decision: Decision linked to the current draft
        social_context: Project social context for voice awareness
        platform_introduced: Per-platform introduction state dict

    Returns:
        Complete system prompt string
    """
    sections = [prompt]

    if social_context:
        sections.append("\n---\n## Project Context")
        sections.append(social_context)

    if system_snapshot:
        sections.append("\n---\n" + system_snapshot)

    # Project State section (between snapshot and summary)
    state_lines = []
    if lifecycle_phase is not None:
        state_lines.append(f"- Lifecycle phase: {lifecycle_phase}")
    if platform_introduced is not None:
        intro_items = ", ".join(
            f"{p}: {'yes' if v else 'no'}" for p, v in platform_introduced.items()
        )
        state_lines.append(f"- Platform introduced: {{{intro_items}}}")
    elif audience_introduced is not None:
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
        sections.append(f"\n---\n## Recent Decisions (last {len(recent_decisions)})")
        for d in recent_decisions:
            decision = d.decision if hasattr(d, "decision") else d.get("decision", "?")
            commit_hash = d.commit_hash[:8] if hasattr(d, "commit_hash") else "?"
            msg = (
                d.commit_message or "N/A"
                if hasattr(d, "commit_message")
                else d.get("commit_message", "N/A")
            )
            reasoning = (
                d.reasoning[:80] if hasattr(d, "reasoning") else str(d.get("reasoning", ""))[:80]
            )
            sections.append(f"- [{decision}] {commit_hash}: {msg} — {reasoning}")

    # Recent Posts
    if recent_posts:
        sections.append(f"\n---\n## Recent Posts (last {len(recent_posts)})")
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
        reasoning = (
            linked_decision.reasoning
            if hasattr(linked_decision, "reasoning")
            else linked_decision.get("reasoning", "")
        )
        sections.append(f"- Reasoning: {reasoning[:200]}")
        angle = (
            linked_decision.angle
            if hasattr(linked_decision, "angle")
            else linked_decision.get("angle")
        )
        if angle:
            sections.append(f"- Angle: {angle}")
        episode_type = (
            linked_decision.episode_type
            if hasattr(linked_decision, "episode_type")
            else linked_decision.get("episode_type")
        )
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
    escalation_context: str | None = None,
    project_summary: str | None = None,
    social_context: str | None = None,
    identity: Any | None = None,
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
        social_context: Project social context for voice consistency
        identity: Resolved IdentityConfig for maintaining perspective

    Returns:
        Complete system prompt string
    """
    sections = [prompt]

    if social_context:
        sections.append("\n---\n## Project Context")
        sections.append(social_context)

    identity_section = _build_identity_instruction(identity)
    if identity_section:
        sections.append(identity_section)
        sections.append("When revising, maintain the author's identity and perspective.")

    if project_summary:
        sections.append("\n---\n## Project Summary")
        sections.append(project_summary)

    sections.append("\n---\n## Current Draft")
    if hasattr(draft, "content"):
        sections.append(f"- Platform: {draft.platform}")
        sections.append(f"- Content: {draft.content}")
        if hasattr(draft, "media_type") and draft.media_type:
            sections.append(f"- Media type: {draft.media_type}")
        if hasattr(draft, "media_spec") and draft.media_spec:
            import json as _json

            sections.append(f"- Media spec: {_json.dumps(draft.media_spec)}")
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
    config: ContextConfig | None = None,
    commit_timestamp: str | None = None,
    parent_timestamp: str | None = None,
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

    # Fetch recent posts per arc so evaluator can reference them
    arc_posts: dict[str, list] = {}
    for arc in active_arcs:
        posts = db.get_arc_posts(arc.id)
        if posts:
            arc_posts[arc.id] = posts[:3]  # Last 3 posts per arc

    debt = db.get_narrative_debt(project_id)
    narrative_debt = debt.debt_counter if debt else 0

    platform_introduced = db.get_all_platform_introduced(project_id)
    pending_drafts = db.get_pending_drafts(project_id)
    held_decisions = db.get_held_decisions(project_id, limit=20)
    recent_decisions = db.get_recent_decisions_for_llm(project_id, limit=config.recent_decisions)
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
            project_id,
            limit=5,
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
        platform_introduced=platform_introduced,
        pending_drafts=pending_drafts,
        recent_decisions=recent_decisions,
        recent_posts=recent_posts,
        project_summary=project_summary,
        memories=memories,
        milestone_summaries=milestone_summaries,
        context_notes=context_notes,
        session_narratives=session_narratives,
        held_decisions=held_decisions,
        arc_posts=arc_posts,
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
        count_tokens("\n".join(pre_history + history_lines + post_history)) > max_tokens
        and len(history_lines) > 2  # Keep section header
    ):
        history_lines.pop(-1)

    if len(history_lines) <= 2:
        history_lines.append("[...history truncated for context budget]")

    return "\n".join(pre_history + history_lines + post_history)


# =============================================================================
# Media Spec Generation
# =============================================================================


def assemble_spec_generation_prompt(
    tool_name: str,
    schema: dict,
    draft_content: str,
) -> str:
    """Build a prompt asking the LLM to generate a media spec for a given tool.

    Args:
        tool_name: Media tool name (e.g. "mermaid", "ray_so")
        schema: Tool spec schema from registry (has "required" and "optional" keys)
        draft_content: The draft's text content to inspire the spec

    Returns:
        Complete prompt string for the LLM
    """
    # Build a natural-language field list instead of dumping raw schema JSON.
    # The tool's input_schema already provides the structural schema, so the prompt
    # adds semantic context rather than duplicating the schema in a different format.
    fields = []
    for field, desc in schema.get("required", {}).items():
        fields.append(f"- {field} (required): {desc}")
    for field, desc in schema.get("optional", {}).items():
        fields.append(f"- {field} (optional): {desc}")
    fields_text = "\n".join(fields)

    return (
        f"You are a media spec generator. Given a social media post and a media tool, "
        f"produce a spec that would create a compelling visual for the post.\n\n"
        f"## Tool: {tool_name}\n\n"
        f"## Available Fields\n{fields_text}\n\n"
        f"## Post Content\n{draft_content}\n\n"
        f"## Instructions\n"
        f"- Fill in all required fields with values appropriate for the post content.\n"
        f"- Optionally include optional fields if they improve the result.\n"
        f"- Be creative — the spec should produce a compelling visual that complements the post.\n"
    )


def build_spec_generation_tool(tool_name: str, schema: dict) -> dict:
    """Convert a media spec_schema() dict to a tool definition for LLM calls.

    The spec_schema format is {"required": {"field": "desc"}, "optional": {"field": "desc"}}.
    This converts it to a standard tool definition with JSON Schema input_schema.
    """
    properties = {}
    required = []
    for field, desc in schema.get("required", {}).items():
        properties[field] = {"type": "string", "description": desc}
        required.append(field)
    for field, desc in schema.get("optional", {}).items():
        properties[field] = {"type": "string", "description": desc}
    return {
        "name": "generate_media_spec",
        "description": f"Generate a {tool_name} media spec for the given social media post",
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }
