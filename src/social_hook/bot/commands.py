"""Telegram /command handlers."""

import logging
import time
from typing import Any

from social_hook.bot.notifications import format_draft_review, get_review_buttons_normalized
from social_hook.constants import PROJECT_NAME, PROJECT_SLUG
from social_hook.messaging.base import (
    Button,
    ButtonRow,
    InboundMessage,
    MessagingAdapter,
    OutboundMessage,
)
from social_hook.models import TERMINAL_STATUSES
from social_hook.parsing import safe_int

logger = logging.getLogger(__name__)

# Chat draft context: chat_id → (draft_id, project_id, timestamp)
_chat_draft_context: dict[str, tuple[str, str, float]] = {}
_CONTEXT_TTL_SECONDS = 3600  # 1 hour


def set_chat_draft_context(chat_id: str, draft_id: str, project_id: str) -> None:
    """Record that this chat is interacting with a specific draft."""
    _chat_draft_context[chat_id] = (draft_id, project_id, time.time())


def get_chat_draft_context(chat_id: str) -> tuple[str, str] | None:
    """Get the (draft_id, project_id) for this chat, or None if expired/missing."""
    entry = _chat_draft_context.get(chat_id)
    if entry is None:
        return None
    draft_id, project_id, ts = entry
    if time.time() - ts > _CONTEXT_TTL_SECONDS:
        del _chat_draft_context[chat_id]
        return None
    return (draft_id, project_id)


def _send(adapter: MessagingAdapter, chat_id: str, text: str, buttons=None) -> bool:
    """Send a plain message via adapter."""
    result = adapter.send_message(chat_id, OutboundMessage(text=text, buttons=buttons or []))
    return result.success


def _get_conn():
    """Get a fresh DB connection (per-request pattern for long-lived daemon)."""
    from social_hook.db import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


def _resync_thread_tweets(conn, draft_id: str, new_content: str) -> None:
    """Re-split content into draft_tweets if the draft has an existing thread.

    Called after content edits to keep draft_tweets in sync. If the draft
    has no existing tweets, this is a no-op. Uses _parse_thread_tweets()
    which is platform-agnostic (string parsing only, no LLM call).
    """
    from social_hook.db import operations as ops
    from social_hook.drafting import _parse_thread_tweets
    from social_hook.filesystem import generate_id
    from social_hook.models import DraftTweet

    existing = ops.get_draft_tweets(conn, draft_id)
    if not existing:
        return

    # Re-parse with thread_min=1 so any split result replaces the old tweets,
    # even if the new content has fewer parts than the original thread.
    parts = _parse_thread_tweets(new_content, thread_min=1)
    new_tweets = [
        DraftTweet(
            id=generate_id("tweet"),
            draft_id=draft_id,
            position=i,
            content=part,
        )
        for i, part in enumerate(parts)
    ]
    ops.replace_draft_tweets(conn, draft_id, new_tweets)


def _build_system_snapshot(conn, project_id: str | None, config, arcs=None) -> str:
    """Build a compact system status block for Gatekeeper context.

    Args:
        conn: DB connection
        project_id: Active project ID (optional)
        config: App config
        arcs: Pre-fetched active arcs (optional, avoids duplicate DB call)
    """
    from social_hook.db import operations as ops

    lines = ["## System Status"]

    # Projects
    projects = ops.get_all_projects(conn)
    if projects:
        proj_parts = []
        for p in projects:
            status = "paused" if p.paused else "active"
            lifecycle = ops.get_lifecycle(conn, p.id)
            phase = lifecycle.phase if lifecycle else "unknown"
            proj_parts.append(f"{p.name} ({status}, {phase} phase)")
        lines.append(f"- Projects: {', '.join(proj_parts)}")

    # Pending drafts (for the active project, or all)
    if project_id:
        drafts = ops.get_pending_drafts(conn, project_id)
    else:
        drafts = ops.get_all_pending_drafts(conn)
    if drafts:
        by_status: dict[str, int] = {}
        for d in drafts:
            by_status.setdefault(d.status, 0)
            by_status[d.status] += 1
        parts = [f"{c} {s}" for s, c in by_status.items()]
        lines.append(f"- Pending drafts: {len(drafts)} ({', '.join(parts)})")
    else:
        lines.append("- Pending drafts: 0")

    # Active arcs (for the active project)
    if project_id:
        if arcs is None:
            arcs = ops.get_active_arcs(conn, project_id)
        if arcs:
            arc_parts = [f'"{a.theme}" ({a.post_count} posts)' for a in arcs]
            lines.append(f"- Active arcs: {', '.join(arc_parts)}")

    # Recent posts
    if project_id:
        recent = ops.get_recent_posts(conn, project_id, days=7)
        if recent:
            last = recent[0]
            if last.posted_at:
                from datetime import datetime, timezone

                now = datetime.now(timezone.utc)
                posted_at = last.posted_at
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                delta = now - posted_at
                if delta.days > 0:
                    ago = f"{delta.days}d ago"
                else:
                    hours = delta.seconds // 3600
                    ago = f"{hours}h ago" if hours > 0 else "just now"
                lines.append(f"- Last post: {ago} on {last.platform}")
            else:
                lines.append(f"- Last post: recent, on {last.platform}")
        else:
            lines.append("- Last post: none in past 7 days")

    # Platforms
    if config and hasattr(config, "platforms"):
        plat_parts = []
        for name, pcfg in config.platforms.items():
            status = "enabled" if pcfg.enabled else "disabled"
            tier = f", {pcfg.account_tier} tier" if getattr(pcfg, "account_tier", None) else ""
            plat_parts.append(f"{name} ({status}{tier})")
        if plat_parts:
            lines.append(f"- Platforms: {', '.join(plat_parts)}")

    # Scheduling
    if config and hasattr(config, "scheduling"):
        s = config.scheduling
        days = "/".join(s.optimal_days) if s.optimal_days else "any"
        hours_str = "/".join(str(h) for h in s.optimal_hours) if s.optimal_hours else "any"
        lines.append(
            f"- Schedule: {s.timezone}, {days} at {hours_str}, max {s.max_posts_per_day}/day"
        )

    # Media tools
    if config and hasattr(config, "media_generation") and config.media_generation.enabled:
        tools = [t for t, enabled in config.media_generation.tools.items() if enabled]
        if tools:
            lines.append(f"- Media tools: {', '.join(tools)}")

    # Available commands
    lines.append("- Commands: /help, /review, /status, /list, /approve, /reject, /schedule")

    return "\n".join(lines)


def _build_chat_history(
    conn,
    chat_id: str,
    token_budget: int = 400,
    time_window_minutes: int = 15,
) -> str | None:
    """Build recent chat history for conversational context.

    Fills backwards from most recent messages until the token budget is
    exhausted or the time window is exceeded. Adapts naturally: short
    messages → more history, long messages → fewer entries.

    Platform-agnostic: queries the chat_messages table in the main DB.
    """
    from social_hook.db.operations import get_recent_chat_messages
    from social_hook.llm.prompts import count_tokens

    try:
        rows = get_recent_chat_messages(conn, chat_id, time_window_minutes)
    except Exception:
        return None

    if not rows:
        return None

    # Build history backwards (rows are newest-first), respecting token budget
    lines: list[str] = []
    tokens_used = 0
    for row in rows:
        text = row.get("content", "")
        if not text:
            continue

        role = "User" if row["role"] == "user" else "Assistant"
        line = f"- {role}: {text}"
        line_tokens = count_tokens(line)

        if tokens_used + line_tokens > token_budget:
            break
        lines.append(line)
        tokens_used += line_tokens

    if not lines:
        return None

    # Reverse to chronological order
    lines.reverse()
    return "## Recent Chat\n" + "\n".join(lines)


_chat_msg_count = 0  # Amortized cleanup counter


def _parse_command(text: str) -> tuple[str, str]:
    """Parse a command string into (command, args).

    Examples:
        '/status' -> ('status', '')
        '/approve draft_abc' -> ('approve', 'draft_abc')
        '/schedule draft_abc 2026-02-10 14:00' -> ('schedule', 'draft_abc 2026-02-10 14:00')
    """
    text = text.strip()
    if " " in text:
        cmd, args = text.split(" ", 1)
    else:
        cmd, args = text, ""
    # Strip leading / and @bot_name suffix
    cmd = cmd.lstrip("/").split("@")[0].lower()
    return cmd, args.strip()


def handle_command(
    msg: InboundMessage, adapter: MessagingAdapter, config: Any | None = None
) -> None:
    """Route a /command message to its handler.

    Args:
        msg: Normalized inbound message
        adapter: Messaging adapter for sending responses
        config: Full Config object
    """
    chat_id = msg.chat_id
    text = msg.text
    cmd, args = _parse_command(text)

    handlers = {
        "start": cmd_help,
        "help": cmd_help,
        "status": cmd_status,
        "pending": cmd_pending,
        "scheduled": cmd_scheduled,
        "projects": cmd_projects,
        "usage": cmd_usage,
        "review": cmd_review,
        "register": cmd_register,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "schedule": cmd_schedule,
        "cancel": cmd_cancel,
        "retry": cmd_retry,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "errors": cmd_errors,
        "health": cmd_health,
    }

    handler = handlers.get(cmd)
    if handler:
        handler(adapter, chat_id, args, config)
    else:
        _send(adapter, chat_id, f"Unknown command: /{cmd}\nUse /help for available commands.")


def handle_message(
    msg: InboundMessage,
    adapter: MessagingAdapter,
    config: Any | None = None,
    task_id: str | None = None,
) -> None:
    """Handle a free-text message by routing through Gatekeeper.

    Checks for pending edits first (Fix 1), then threads draft/project
    context through to Gatekeeper and Expert (Fix 2).

    Args:
        msg: Normalized inbound message
        adapter: Messaging adapter for sending responses
        config: Full Config object
    """
    chat_id = msg.chat_id
    text = msg.text

    if not text:
        return

    # Check for pending reply FIRST (Fix 1)
    from social_hook.bot.buttons import clear_pending_reply, get_pending_reply

    pending = get_pending_reply(chat_id)
    if pending:
        clear_pending_reply(chat_id)
        _handle_pending_reply(adapter, chat_id, pending, text, config, task_id=task_id)
        return

    try:
        from social_hook.errors import ConfigError
        from social_hook.llm.factory import create_client
        from social_hook.llm.gatekeeper import Gatekeeper

        if not config:
            _send(adapter, chat_id, f"Not configured. Run {PROJECT_SLUG} setup first.")
            return

        try:
            client = create_client(config.models.gatekeeper, config)
        except ConfigError:
            _send(adapter, chat_id, "Model provider not configured. Use /help for commands.")
            return

        # Look up draft/project context for this chat (Fix 2)
        draft_obj = None
        project_id = None
        db = None
        snapshot = None
        summary = None
        ctx = get_chat_draft_context(chat_id)

        _context_conn = None
        try:
            # Always open DB — needed for snapshot even without draft context
            _context_conn = _get_conn()
            from social_hook.llm.dry_run import DryRunContext

            db = DryRunContext(_context_conn, dry_run=False)

            if ctx:
                draft_id_ctx, project_id = ctx
                try:
                    from social_hook.db import get_draft

                    draft_obj = get_draft(_context_conn, draft_id_ctx)
                except Exception:
                    pass  # Graceful fallback — context is optional

            # If no project from draft context, use first active project
            if not project_id:
                from social_hook.db import operations as ops

                all_projects = ops.get_all_projects(_context_conn)
                active = [p for p in all_projects if not p.paused]
                if active:
                    project_id = active[0].id

            # Fetch enriched context for Gatekeeper
            gk_recent_decisions = None
            gk_recent_posts = None
            gk_lifecycle_phase = None
            gk_active_arcs = None
            gk_narrative_debt = None
            gk_audience_introduced = None
            gk_linked_decision = None
            gk_social_context = None
            gk_platform_introduced = None

            if project_id:
                from social_hook.db import operations as ops
                from social_hook.db.operations import get_project_summary

                summary = get_project_summary(_context_conn, project_id)

                try:
                    gk_recent_decisions = ops.get_recent_decisions_for_llm(
                        _context_conn, project_id, limit=10
                    )
                    gk_recent_posts = ops.get_recent_posts_for_context(
                        _context_conn, project_id, limit=5
                    )
                    lifecycle = ops.get_lifecycle(_context_conn, project_id)
                    gk_lifecycle_phase = lifecycle.phase if lifecycle else None
                    gk_active_arcs = ops.get_active_arcs(_context_conn, project_id)
                    debt = ops.get_narrative_debt(_context_conn, project_id)
                    gk_narrative_debt = debt.debt_counter if debt else 0
                    gk_audience_introduced = ops.get_audience_introduced(_context_conn, project_id)
                    gk_platform_introduced = ops.get_all_platform_introduced(
                        _context_conn, project_id
                    )

                    # Load social context for voice awareness
                    try:
                        project = ops.get_project(_context_conn, project_id)
                        if project and project.repo_path:
                            from social_hook.config.project import load_project_config

                            pc = load_project_config(project.repo_path)
                            gk_social_context = pc.social_context
                    except Exception:
                        logger.debug("Failed to load social context", exc_info=True)

                    if draft_obj and hasattr(draft_obj, "decision_id") and draft_obj.decision_id:
                        gk_linked_decision = ops.get_decision(_context_conn, draft_obj.decision_id)
                except Exception:
                    logger.debug("Failed to fetch gatekeeper context", exc_info=True)

            # Build system snapshot, reusing already-fetched arcs
            try:
                snapshot = _build_system_snapshot(
                    _context_conn, project_id, config, arcs=gk_active_arcs
                )
            except Exception:
                logger.debug("Failed to build system snapshot", exc_info=True)

            # Build chat history BEFORE storing inbound to avoid duplication
            history = None
            try:
                history = _build_chat_history(_context_conn, chat_id)
            except Exception:
                logger.debug("Failed to build chat history", exc_info=True)

            # Store inbound message
            from social_hook.db.operations import insert_chat_message

            try:
                insert_chat_message(_context_conn, chat_id, "user", text)
            except Exception:
                logger.debug("Failed to store inbound chat message", exc_info=True)

            if task_id:
                from social_hook.db import operations as ops

                ops.emit_task_stage(
                    _context_conn, task_id, "routing", "Understanding message", project_id or ""
                )

            gatekeeper = Gatekeeper(client)
            route = gatekeeper.route(
                user_message=text,
                draft_context=draft_obj,
                project_summary=summary,
                project_id=project_id,
                db=db,
                system_snapshot=snapshot,
                chat_history=history,
                recent_decisions=gk_recent_decisions,
                recent_posts=gk_recent_posts,
                lifecycle_phase=gk_lifecycle_phase,
                active_arcs=gk_active_arcs,
                narrative_debt=gk_narrative_debt,
                audience_introduced=gk_audience_introduced,
                linked_decision=gk_linked_decision,
                social_context=gk_social_context,
                platform_introduced=gk_platform_introduced,
            )

            response_text = None
            if route.action.value == "handle_directly":
                response_text = _handle_gatekeeper_direct(adapter, chat_id, route, config)
            elif route.action.value == "escalate_to_expert":
                response_text = _handle_expert_escalation(
                    adapter,
                    chat_id,
                    text,
                    route,
                    config,
                    draft=draft_obj,
                    project_id=project_id,
                    db=db,
                    task_id=task_id,
                )

            # Store outbound response
            if response_text:
                try:
                    insert_chat_message(_context_conn, chat_id, "assistant", response_text)
                except Exception:
                    logger.debug("Failed to store outbound chat message", exc_info=True)

            # Amortized cleanup
            global _chat_msg_count
            _chat_msg_count += 1
            if _chat_msg_count % 50 == 0:
                try:
                    from social_hook.db.operations import cleanup_old_chat_messages

                    cleanup_old_chat_messages(_context_conn)
                except Exception:
                    logger.debug("Chat message cleanup failed", exc_info=True)
        finally:
            if _context_conn:
                _context_conn.close()
    except Exception as e:
        logger.exception("Error routing message through Gatekeeper")
        _send(adapter, chat_id, f"Error processing message: {e}")


def _handle_pending_reply(adapter, chat_id, pending, text, config, task_id=None):
    """Dispatch a pending reply to the appropriate handler."""
    if pending.type == "edit_text":
        _save_edit(adapter, chat_id, pending.draft_id, text)
    elif pending.type == "schedule_custom":
        _save_custom_schedule(adapter, chat_id, pending.draft_id, text, config)
    elif pending.type == "edit_angle":
        _save_angle(adapter, chat_id, pending.draft_id, text, task_id=task_id)
    elif pending.type == "reject_note":
        _save_rejection_note(adapter, chat_id, pending.draft_id, text, config)
    elif pending.type == "edit_media_spec":
        _save_media_spec(adapter, chat_id, pending.draft_id, text, config)
    elif pending.type == "media_upload":
        _save_media_upload(adapter, chat_id, pending.draft_id, text)
    else:
        logger.warning("Unknown pending reply type: %s (draft %s)", pending.type, pending.draft_id)


def _save_custom_schedule(adapter, chat_id, draft_id, text, config):
    """Parse ISO datetime and schedule the draft."""
    from datetime import datetime

    from social_hook.db import get_draft, update_draft
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        if draft.preview_mode:
            _send(
                adapter,
                chat_id,
                "No account connected. Run 'social-hook account add' to connect and enable posting.",
            )
            return

        try:
            datetime.fromisoformat(text.strip())
        except ValueError:
            _send(
                adapter,
                chat_id,
                "Invalid format. Send an ISO 8601 datetime, e.g. 2025-03-15T14:30:00",
            )
            # Re-set pending reply so user can try again
            from social_hook.bot.buttons import PendingReply, _pending_replies

            _pending_replies[chat_id] = PendingReply(
                type="schedule_custom", draft_id=draft_id, timestamp=time.time()
            )
            return

        update_draft(conn, draft_id, status="scheduled", scheduled_time=text.strip())
        ops.emit_data_event(conn, "draft", "scheduled", draft_id, draft.project_id)
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` scheduled for {text.strip()}")
        if config:
            from social_hook.messaging.base import OutboundMessage
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(
                    text=f"Draft `{draft_id[:12]}` scheduled for {text.strip()} ({draft.platform})"
                ),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def _save_rejection_note(adapter, chat_id, draft_id, text, config=None):
    """Reject a draft with a user-provided note and save as voice memory."""
    from social_hook.db import get_draft, update_draft
    from social_hook.db import operations as ops
    from social_hook.intro_lifecycle import on_intro_rejected

    conn = _get_conn()
    try:
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        update_draft(conn, draft_id, status="rejected", last_error=f"Rejected: {text}")
        ops.emit_data_event(conn, "draft", "rejected", draft_id, draft.project_id)

        # Save rejection feedback as voice memory for future content generation
        memory_saved = False
        try:
            project = ops.get_project(conn, draft.project_id)
            if project:
                from social_hook.config.project import save_memory

                save_memory(
                    project.repo_path,
                    context=f"Rejected {draft.platform} draft",
                    feedback=text,
                    draft_id=draft_id,
                )
                memory_saved = True
        except Exception:
            logger.debug("Failed to save rejection memory", exc_info=True)

        cascade_msg = on_intro_rejected(conn, draft, draft.project_id, verbose=False)

        reject_msg = f"Draft `{draft_id[:12]}` rejected with note."
        if memory_saved:
            reject_msg += " Feedback saved for future drafts."
        if cascade_msg:
            reject_msg += f"\n{cascade_msg}"
        _send(adapter, chat_id, reject_msg)
        if config:
            from social_hook.messaging.base import OutboundMessage
            from social_hook.notifications import broadcast_notification

            broadcast_notification(
                config,
                OutboundMessage(
                    text=f"Draft `{draft_id[:12]}` rejected: {text} ({draft.platform})"
                ),
                exclude_chat=chat_id,
            )
    finally:
        conn.close()


def _save_media_spec(adapter, chat_id, draft_id, text, config):
    """Parse user-provided JSON spec, update draft, and trigger generation."""
    import json as json_mod

    from social_hook.db import get_draft, update_draft

    conn = _get_conn()
    try:
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        # Parse JSON from the reply (strip markdown code blocks)
        raw = text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            spec = json_mod.loads(raw)
        except json_mod.JSONDecodeError as e:
            _send(adapter, chat_id, f"Invalid JSON: {e}\nPlease send valid JSON.")
            # Re-register pending reply so user can try again
            import time as _time

            from social_hook.bot.buttons import PendingReply, _pending_replies

            _pending_replies[chat_id] = PendingReply(
                type="edit_media_spec", draft_id=draft_id, timestamp=_time.time()
            )
            return

        update_draft(conn, draft_id, media_spec=spec)

        # Auto-generate via btn_media_confirm_gen flow
        from social_hook.bot.buttons import btn_media_confirm_gen

        # Close conn before calling the button handler (it opens its own)
        conn.close()
        conn = None

        btn_media_confirm_gen(adapter, chat_id, "", draft_id, config)
    finally:
        if conn:
            conn.close()


def _save_media_upload(adapter, chat_id, draft_id, text):
    """Handle media upload reply — text contains the file path from the adapter."""
    import json as json_mod

    from social_hook.db import get_draft, update_draft
    from social_hook.db import operations as ops
    from social_hook.db.operations import insert_draft_change
    from social_hook.filesystem import generate_id
    from social_hook.models import DraftChange

    conn = _get_conn()
    try:
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        # The text should be a file path from the adapter's file download
        file_path = text.strip()
        if not file_path:
            _send(adapter, chat_id, "No file received. Send a photo or file.")
            return

        old_paths = draft.media_paths
        update_draft(
            conn,
            draft_id,
            media_paths=[file_path],
            media_type="upload",
        )

        insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft_id,
                field="media_paths",
                old_value=json_mod.dumps(old_paths),
                new_value=json_mod.dumps([file_path]),
                changed_by="human",
            ),
        )

        ops.emit_data_event(conn, "draft", "edited", draft_id, draft.project_id)
        _send(adapter, chat_id, f"Media attached to `{draft_id[:12]}`.")
    finally:
        conn.close()


def _apply_expert_result(
    conn,
    draft,
    result,
    config=None,
) -> bool:
    """Apply Expert refinement result to a draft in the database.

    Handles content updates, media spec updates, draft change audit trail,
    and optional auto-media-regeneration. Returns True if any changes were applied.
    """
    from social_hook.db import insert_draft_change, update_draft
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models import DraftChange

    if not result.refined_content and not result.refined_media_spec:
        return False

    if result.refined_content:
        old_content = draft.content
        update_draft(conn, draft.id, content=result.refined_content)
        _resync_thread_tweets(conn, draft.id, result.refined_content)
        insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft.id,
                field="content",
                old_value=old_content[:200],
                new_value=result.refined_content[:200],
                changed_by="expert",
            ),
        )

    if result.refined_media_spec:
        import json as json_mod

        update_draft(conn, draft.id, media_spec=result.refined_media_spec)
        insert_draft_change(
            conn,
            DraftChange(
                id=generate_id("change"),
                draft_id=draft.id,
                field="media_spec",
                old_value=json_mod.dumps(draft.media_spec)[:200] if draft.media_spec else "null",
                new_value=json_mod.dumps(result.refined_media_spec)[:200],
                changed_by="expert",
            ),
        )

        # Auto-regenerate media with new spec if config available
        if config and draft.media_type:
            try:
                from social_hook.drafting import _generate_media

                media_paths, _, _, _ = _generate_media(
                    config,
                    draft.media_type,
                    result.refined_media_spec,
                    project_config=None,
                )
                if media_paths:
                    update_draft(
                        conn,
                        draft.id,
                        media_paths=media_paths,
                        media_spec_used=result.refined_media_spec,
                    )
            except Exception as e:
                logger.warning(f"Auto-regeneration after expert refine failed: {e}")

    ops.emit_data_event(conn, "draft", "edited", draft.id, draft.project_id)
    return True


def _save_angle(adapter, chat_id, draft_id, text, task_id=None):
    """Use Expert agent to redraft content with a new angle."""
    from social_hook.config.yaml import load_full_config
    from social_hook.db import get_draft
    from social_hook.db import operations as ops
    from social_hook.llm.expert import Expert
    from social_hook.llm.factory import create_client

    conn = _get_conn()
    try:
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        if draft.status in TERMINAL_STATUSES:
            _send(adapter, chat_id, f"Cannot redraft: draft is '{draft.status}'")
            return

        try:
            config = load_full_config()
            client = create_client(config.models.drafter, config)
        except Exception as e:
            _send(adapter, chat_id, f"Cannot redraft: {e}")
            return

        summary = ops.get_project_summary(conn, draft.project_id)

        if task_id:
            ops.emit_task_stage(
                conn, task_id, "redrafting", "Redrafting with new angle", draft.project_id
            )

        expert = Expert(client)
        result = expert.handle(
            draft=draft,
            user_message=text,
            escalation_reason="angle_change",
            project_summary=summary,
            project_id=draft.project_id,
            db=conn,
        )

        if _apply_expert_result(conn, draft, result, config=config):
            set_chat_draft_context(chat_id, draft_id, draft.project_id)

            parts = []
            if result.refined_content:
                parts.append(
                    f"Draft `{draft_id[:12]}` redrafted with new angle."
                    f"\n\n```\n{result.refined_content}\n```"
                )
            else:
                parts.append(f"Draft `{draft_id[:12]}` media spec updated.")
            if result.refined_media_spec:
                parts.append("Media spec updated. Run `media-regen` to regenerate media.")
            msg = "\n".join(parts)
            buttons = get_review_buttons_normalized(
                draft.id, platform=draft.platform, preview_mode=draft.preview_mode
            )
            adapter.send_message(chat_id, OutboundMessage(text=msg, buttons=buttons))
        else:
            _send(
                adapter,
                chat_id,
                f"Expert could not refine draft: {result.reasoning}",
                buttons=get_review_buttons_normalized(draft_id),
            )
    except Exception as e:
        logger.exception("Error in angle redraft")
        _send(
            adapter,
            chat_id,
            f"Error redrafting: {e}",
            buttons=get_review_buttons_normalized(draft_id),
        )
    finally:
        conn.close()


def _save_edit(
    adapter: MessagingAdapter,
    chat_id: str,
    draft_id: str,
    new_content: str,
    changed_by: str = "human",
) -> None:
    """Save edited content to draft and create audit trail.

    Args:
        adapter: Messaging adapter for sending responses
        chat_id: Chat to reply in
        draft_id: Draft to update
        new_content: New draft content
        changed_by: Who made the change (human, gatekeeper, expert)
    """
    from social_hook.db import get_draft, insert_draft_change, update_draft
    from social_hook.db import operations as ops
    from social_hook.filesystem import generate_id
    from social_hook.models import DraftChange

    conn = _get_conn()
    try:
        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        old_content = draft.content
        update_draft(conn, draft_id, content=new_content)
        _resync_thread_tweets(conn, draft_id, new_content)

        change = DraftChange(
            id=generate_id("change"),
            draft_id=draft_id,
            field="content",
            old_value=old_content[:200],
            new_value=new_content[:200],
            changed_by=changed_by,
        )
        insert_draft_change(conn, change)
        ops.emit_data_event(conn, "draft", "edited", draft_id, draft.project_id)

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        _send(
            adapter,
            chat_id,
            f"Draft `{draft_id[:12]}` updated.\n\n```\n{new_content}\n```",
            buttons=get_review_buttons_normalized(draft_id, preview_mode=draft.preview_mode),
        )
    finally:
        conn.close()


def _handle_gatekeeper_direct(
    adapter: MessagingAdapter, chat_id: str, route: Any, config: Any
) -> str | None:
    """Handle a Gatekeeper direct action. Returns response text for chat history."""
    op = route.operation
    if op is None:
        _send(adapter, chat_id, "Understood.")
        return "Understood."

    op_value = op.value if hasattr(op, "value") else str(op)
    params = route.params or {}

    if op_value == "approve":
        draft_id = params.get("draft_id", "")
        if draft_id:
            cmd_approve(adapter, chat_id, draft_id, config)
        else:
            _send(adapter, chat_id, "Please specify a draft ID to approve.")
        return None  # Operational — response sent inside cmd_*
    elif op_value == "reject":
        draft_id = params.get("draft_id", "")
        if draft_id:
            cmd_reject(adapter, chat_id, draft_id, config)
        else:
            _send(adapter, chat_id, "Please specify a draft ID to reject.")
        return None
    elif op_value == "schedule":
        draft_id = params.get("draft_id", "")
        time_str = params.get("time", "")
        cmd_schedule(adapter, chat_id, f"{draft_id} {time_str}".strip(), config)
        return None
    elif op_value == "cancel":
        draft_id = params.get("draft_id", "")
        cmd_cancel(adapter, chat_id, draft_id, config)
        return None
    elif op_value == "substitute":
        new_content = params.get("content", "")
        if not new_content:
            logger.warning("Substitute routed but content empty")
            msg = "Please specify the new content."
            _send(adapter, chat_id, msg)
            return msg
        draft_id = params.get("draft_id", "")
        if not draft_id:
            ctx = get_chat_draft_context(chat_id)
            if ctx:
                draft_id = ctx[0]
        if not draft_id:
            msg = "No active draft to substitute. Use /review first."
            _send(adapter, chat_id, msg)
            return msg
        _save_edit(adapter, chat_id, draft_id, new_content, changed_by="gatekeeper")
        return None
    elif op_value == "query":
        answer: str = params.get("answer", "I'll look into that.")
        _send(adapter, chat_id, answer)
        return answer
    else:
        _send(adapter, chat_id, "Understood.")
        return "Understood."


def _handle_expert_escalation(
    adapter: MessagingAdapter,
    chat_id: str,
    user_message: str,
    route: Any,
    config: Any,
    draft: Any = None,
    project_id: str | None = None,
    db: Any = None,
    task_id: str | None = None,
) -> str | None:
    """Handle an Expert escalation. Returns response text for chat history.

    Args:
        adapter: Messaging adapter for sending responses
        chat_id: Chat to reply in
        user_message: Original user message
        route: Gatekeeper route result
        config: Full Config object
        draft: Current draft object (from chat context)
        project_id: Current project ID (from chat context)
        db: Database context for usage logging
    """
    try:
        from social_hook.errors import ConfigError
        from social_hook.llm.expert import Expert
        from social_hook.llm.factory import create_client

        try:
            client = create_client(config.models.drafter, config)
        except ConfigError:
            msg = "Model provider not configured. Use /help for commands."
            _send(adapter, chat_id, msg)
            return msg

        expert = Expert(client)

        # Resolve social context and identity for expert (non-fatal)
        expert_social_context = None
        expert_identity = None
        expert_summary = None
        if project_id:
            try:
                from social_hook.db import operations as _expert_ops

                _expert_conn = _get_conn()
                expert_summary = _expert_ops.get_project_summary(_expert_conn, project_id)
                _expert_project = _expert_ops.get_project(_expert_conn, project_id)
                if _expert_project and _expert_project.repo_path:
                    from social_hook.config.project import load_project_config

                    pc = load_project_config(_expert_project.repo_path)
                    expert_social_context = pc.social_context
                if draft and hasattr(draft, "platform"):
                    from social_hook.config.yaml import load_full_config, resolve_identity

                    full_config = load_full_config()
                    expert_identity = resolve_identity(full_config, draft.platform)
            except Exception:
                logger.debug("Failed to resolve expert context", exc_info=True)

        if task_id and db:
            from social_hook.db import operations as _stage_ops

            _stage_ops.emit_task_stage(
                db.conn, task_id, "thinking", "Drafting response", project_id or ""
            )

        result = expert.handle(
            draft=draft,
            user_message=user_message,
            escalation_reason=route.escalation_reason or "user request",
            escalation_context=route.escalation_context,
            project_summary=expert_summary,
            project_id=project_id,
            db=db,
            social_context=expert_social_context,
            identity=expert_identity,
        )

        action = result.action.value if hasattr(result.action, "value") else str(result.action)

        if action == "save_context_note" and result.context_note:
            from social_hook.config import save_context_note

            # Find a project to save the note to
            conn = _get_conn()
            try:
                from social_hook.db import get_all_projects

                projects = get_all_projects(conn)
                if projects:
                    project = projects[0]
                    save_context_note(project.repo_path, result.context_note, source="telegram")
                    msg = f"Context note saved for {project.name}."
                    _send(adapter, chat_id, msg)
                    return msg
                else:
                    msg = "No projects registered to save note to."
                    _send(adapter, chat_id, msg)
                    return msg
            finally:
                conn.close()
        elif action == "refine_draft" and (result.refined_content or result.refined_media_spec):
            if not draft:
                display_text = (
                    result.refined_content if result.refined_content else result.reasoning
                )
                msg = f"*Refined draft (no active draft to update):*\n\n```\n{display_text}\n```"
                _send(adapter, chat_id, msg)
                return msg

            conn = _get_conn()
            try:
                _apply_expert_result(conn, draft, result, config=config)

                parts = []
                if result.refined_content:
                    parts.append(f"```\n{result.refined_content}\n```")
                if result.refined_media_spec:
                    import json as json_mod

                    parts.append(
                        f"Media spec updated: {json_mod.dumps(result.refined_media_spec)[:200]}"
                    )
                msg = f"Draft `{draft.id[:12]}` updated by Expert.\n\n" + "\n".join(parts)
                buttons = get_review_buttons_normalized(
                    draft.id, platform=draft.platform, preview_mode=draft.preview_mode
                )
                adapter.send_message(chat_id, OutboundMessage(text=msg, buttons=buttons))
                return msg
            finally:
                conn.close()
        elif action == "answer_question" and result.answer:
            _send(adapter, chat_id, result.answer)
            return result.answer
        else:
            msg = result.reasoning or "Understood."
            _send(adapter, chat_id, msg)
            return msg
    except Exception as e:
        logger.exception("Error in expert escalation")
        msg = f"Error: {e}"
        _send(
            adapter,
            chat_id,
            msg,
            buttons=get_review_buttons_normalized(draft.id, preview_mode=draft.preview_mode)
            if draft
            else None,
        )
        return msg


# =============================================================================
# Command Handlers
# =============================================================================


HELP_DETAILS = {
    "status": "Show system overview: active/paused projects, pending drafts, scheduled posts.",
    "pending": "List all pending drafts (draft/approved/scheduled) with platform and preview.",
    "scheduled": "List scheduled drafts with their posting times. Includes [Cancel] button per draft.",
    "projects": "List all registered projects with active/paused status.",
    "usage": "Show token usage summary. Optional: /usage <days> (default 30).",
    "review": "Show full draft details with action buttons. Usage: /review <draft\\_id>",
    "register": f"Register a new project. Must be done from terminal: `{PROJECT_SLUG} register /path/to/repo`",
    "approve": "Approve a draft for posting. Usage: /approve <draft\\_id>",
    "reject": "Reject a draft. Optional reason: /reject <draft\\_id> [reason]",
    "schedule": "Schedule a draft. Without time: optimal scheduling. /schedule <draft\\_id> [datetime]",
    "cancel": "Cancel a scheduled draft. Usage: /cancel <draft\\_id>",
    "retry": "Retry a failed draft. Usage: /retry <draft\\_id>",
    "pause": "Pause a project (stops evaluating commits). Usage: /pause <project\\_id>",
    "resume": "Resume a paused project. Usage: /resume <project\\_id>",
    "errors": "Show recent system errors (ERROR/CRITICAL, last 24h). Usage: /errors [limit|severity]",
    "health": "Show system health status with error counts from last 24h.",
    "help": "Show help. For details on a command: /help <command>",
}


def cmd_help(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Show available commands. If args provided, show detailed help."""
    if args.strip():
        cmd_name = args.strip().lstrip("/")
        detail = HELP_DETAILS.get(cmd_name)
        if detail:
            _send(adapter, chat_id, f"*/{cmd_name}*\n\n{detail}")
        else:
            _send(adapter, chat_id, f"Unknown command: /{cmd_name}")
        return

    text = (
        f"*{PROJECT_NAME} Bot*\n\n"
        "Commands:\n"
        "/status - System status\n"
        "/pending - View pending drafts\n"
        "/scheduled - View scheduled drafts\n"
        "/projects - List registered projects\n"
        "/usage [days] - Token usage summary\n"
        "/review <draft\\_id> - Review a draft\n"
        "/approve <draft\\_id> - Approve a draft\n"
        "/reject <draft\\_id> [reason] - Reject a draft\n"
        "/schedule <draft\\_id> [time] - Schedule a draft\n"
        "/cancel <draft\\_id> - Cancel a draft\n"
        "/retry <draft\\_id> - Retry a failed draft\n"
        "/pause <project\\_id> - Pause a project\n"
        "/resume <project\\_id> - Resume a project\n"
        "/errors [limit|severity] - Recent system errors\n"
        "/health - System health status\n"
        "/help [command] - Show this message"
    )
    _send(adapter, chat_id, text)


def cmd_status(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Show system status."""
    conn = _get_conn()
    try:
        from social_hook.db import get_all_pending_drafts, get_all_projects

        projects = get_all_projects(conn)
        pending = get_all_pending_drafts(conn)

        active = [p for p in projects if not p.paused]
        paused = [p for p in projects if p.paused]

        scheduled = [d for d in pending if d.status == "scheduled"]
        drafts = [d for d in pending if d.status == "draft"]
        approved = [d for d in pending if d.status == "approved"]
        deferred = [d for d in pending if d.status == "deferred"]

        lines = [
            "*System Status*",
            "",
            f"Projects: {len(active)} active, {len(paused)} paused",
            f"Pending drafts: {len(drafts)}",
            f"Approved: {len(approved)}",
            f"Scheduled: {len(scheduled)}",
            f"Deferred: {len(deferred)}",
        ]
        _send(adapter, chat_id, "\n".join(lines))
    finally:
        conn.close()


def cmd_pending(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Show pending drafts with action buttons."""
    conn = _get_conn()
    try:
        from social_hook.db import get_all_pending_drafts

        drafts = get_all_pending_drafts(conn)
        if not drafts:
            _send(adapter, chat_id, "No pending drafts.")
            return

        for d in drafts[:10]:
            status_icon = {"draft": "📝", "approved": "✅", "scheduled": "⏰", "deferred": "⏸"}.get(
                d.status, "❓"
            )
            text = f"{status_icon} `{d.id[:12]}` [{d.platform}]\n{d.content[:80]}..."
            buttons = [
                ButtonRow(
                    buttons=[
                        Button(label="Review", action="review", payload=d.id),
                        Button(label="Quick Approve", action="quick_approve", payload=d.id),
                    ]
                ),
            ]
            adapter.send_message(chat_id, OutboundMessage(text=text, buttons=buttons))

        if len(drafts) > 10:
            _send(adapter, chat_id, f"...and {len(drafts) - 10} more")
    finally:
        conn.close()


def cmd_scheduled(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Show scheduled drafts with cancel buttons."""
    conn = _get_conn()
    try:
        from social_hook.db import get_all_pending_drafts

        all_pending = get_all_pending_drafts(conn)
        scheduled = [d for d in all_pending if d.status == "scheduled"]
        if not scheduled:
            _send(adapter, chat_id, "No scheduled drafts.")
            return

        for d in scheduled[:10]:
            time_str = d.scheduled_time or "no time"
            text = f"⏰ `{d.id[:12]}` [{d.platform}] {time_str}"
            buttons = [
                ButtonRow(
                    buttons=[
                        Button(label="Cancel", action="cancel", payload=d.id),
                    ]
                ),
            ]
            adapter.send_message(chat_id, OutboundMessage(text=text, buttons=buttons))
    finally:
        conn.close()


def cmd_projects(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """List registered projects."""
    conn = _get_conn()
    try:
        from social_hook.db import get_all_projects

        projects = get_all_projects(conn)
        if not projects:
            _send(adapter, chat_id, "No registered projects.")
            return

        lines = ["*Registered Projects*", ""]
        for p in projects:
            status = "⏸️ paused" if p.paused else "▶️ active"
            lines.append(f"{status} `{p.id[:12]}` {p.name}")
        _send(adapter, chat_id, "\n".join(lines))
    finally:
        conn.close()


def cmd_usage(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Show token usage summary. Use '/usage recent [N]' for individual operations."""
    arg = args.strip()

    conn = _get_conn()
    try:
        # Handle '/usage recent [N]'
        if arg.startswith("recent"):
            from social_hook.db import get_recent_usage

            parts = arg.split()
            limit = safe_int(parts[1], 10, "usage limit argument") if len(parts) > 1 else 10
            entries = get_recent_usage(conn, limit=limit)
            if not entries:
                _send(adapter, chat_id, "No usage data found.")
                return

            lines = [f"*Recent operations (last {limit})*", ""]
            for e in entries:
                project = e.get("project_name") or "—"
                op = e.get("operation_type", "?")
                inp = e.get("input_tokens", 0) or 0
                out = e.get("output_tokens", 0) or 0
                cost = (e.get("cost_cents", 0) or 0) / 100.0
                commit = e.get("commit_hash") or ""
                commit_str = commit[:8] if commit else "—"
                lines.append(f"`{commit_str}` {op} ({project}) — {inp:,}+{out:,} tok, ${cost:.3f}")
            _send(adapter, chat_id, "\n".join(lines))
            return

        try:
            days = int(arg) if arg else 30
        except ValueError:
            days = 30

        from social_hook.db import get_usage_summary

        rows = get_usage_summary(conn, days=days)
        total_input = sum(r.get("total_input", 0) or 0 for r in rows)
        total_output = sum(r.get("total_output", 0) or 0 for r in rows)
        total_cost = sum(r.get("total_cost_cents", 0) or 0 for r in rows) / 100.0
        lines = [
            f"*Usage (last {days} days)*",
            "",
            f"Models: {len(rows)}",
            f"Input tokens: {total_input:,}",
            f"Output tokens: {total_output:,}",
            f"Estimated cost: ${total_cost:.2f}",
        ]
        _send(adapter, chat_id, "\n".join(lines))
    finally:
        conn.close()


def cmd_review(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Review a draft with full details and action buttons."""
    draft_id = args.strip()
    if not draft_id:
        _send(adapter, chat_id, "Usage: /review <draft\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_decision, get_draft, get_draft_tweets, get_project

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        project = get_project(conn, draft.project_id)
        project_name = project.name if project else "unknown"

        decision = get_decision(conn, draft.decision_id)
        commit_hash = decision.commit_hash[:8] if decision else "unknown"
        commit_message = f"[{decision.commit_hash[:8]}]" if decision else ""

        tweets = get_draft_tweets(conn, draft.id)
        is_thread = bool(tweets)
        tweet_count = len(tweets) if is_thread else None

        suggested_time_str = None
        if draft.suggested_time:
            suggested_time_str = draft.suggested_time.strftime("%Y-%m-%d %H:%M UTC")

        msg = format_draft_review(
            project_name=project_name,
            commit_hash=commit_hash,
            commit_message=commit_message,
            platform=draft.platform,
            content=draft.content,
            suggested_time=suggested_time_str,
            draft_id=draft.id,
            char_count=len(draft.content),
            is_thread=is_thread,
            tweet_count=tweet_count,
            post_category=decision.post_category if decision else None,
            angle=decision.angle if decision else None,
            evaluator_reasoning=decision.reasoning if decision else None,
        )
        buttons = get_review_buttons_normalized(
            draft.id, platform=draft.platform, preview_mode=draft.preview_mode
        )
        adapter.send_message(chat_id, OutboundMessage(text=msg, buttons=buttons))
    finally:
        conn.close()


def cmd_register(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Send instructions for registering a project (requires terminal)."""
    _send(
        adapter,
        chat_id,
        "Registration requires filesystem access.\n\n"
        "Use from terminal:\n"
        f"`{PROJECT_SLUG} register /path/to/repo`",
    )


def cmd_approve(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Approve a draft for posting."""
    draft_id = args.strip()
    if not draft_id:
        _send(adapter, chat_id, "Usage: /approve <draft\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        # Scheduled drafts go through the scheduler; use unschedule first
        if draft.status not in ("draft", "approved", "deferred"):
            _send(adapter, chat_id, f"Cannot approve draft with status: {draft.status}")
            return

        update_draft(conn, draft_id, status="approved")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` approved.")
    finally:
        conn.close()


def cmd_reject(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Reject a draft with optional reason."""
    parts = args.strip().split(None, 1)
    if not parts:
        _send(adapter, chat_id, "Usage: /reject <draft\\_id> [reason]")
        return

    draft_id = parts[0]
    reason = parts[1] if len(parts) > 1 else None

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_kwargs = {"status": "rejected"}
        if reason:
            update_kwargs["last_error"] = f"Rejected: {reason}"
        update_draft(conn, draft_id, **update_kwargs)  # type: ignore[arg-type]

        msg = f"Draft `{draft_id[:12]}` rejected."
        if reason:
            msg += f"\nReason: {reason}"
        _send(adapter, chat_id, msg)
    finally:
        conn.close()


def cmd_schedule(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Schedule a draft for posting."""
    parts = args.strip().split(None, 1)
    if not parts:
        _send(adapter, chat_id, "Usage: /schedule <draft\\_id> [datetime]")
        return

    draft_id = parts[0]
    time_str = parts[1] if len(parts) > 1 else None

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        if time_str:
            update_draft(conn, draft_id, status="scheduled", scheduled_time=time_str)
            _send(
                adapter,
                chat_id,
                f"Draft `{draft_id[:12]}` scheduled for {time_str}.",
            )
        else:
            # Calculate optimal time
            from social_hook.scheduling import calculate_optimal_time

            result = calculate_optimal_time(
                conn,
                draft.project_id,
                platform=draft.platform,
                tz=config.scheduling.timezone if config else "UTC",
                max_posts_per_day=config.scheduling.max_posts_per_day if config else 3,
                min_gap_minutes=config.scheduling.min_gap_minutes if config else 30,
                optimal_days=config.scheduling.optimal_days if config else None,
                optimal_hours=config.scheduling.optimal_hours if config else None,
            )
            scheduled_str = result.datetime.isoformat()
            update_draft(conn, draft_id, status="scheduled", scheduled_time=scheduled_str)
            _send(
                adapter,
                chat_id,
                f"Draft `{draft_id[:12]}` scheduled for {scheduled_str}\n{result.time_reason}",
            )
    finally:
        conn.close()


def cmd_cancel(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Cancel a draft."""
    draft_id = args.strip()
    if not draft_id:
        _send(adapter, chat_id, "Usage: /cancel <draft\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        set_chat_draft_context(chat_id, draft_id, draft.project_id)

        update_draft(conn, draft_id, status="cancelled")
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` cancelled.")
    finally:
        conn.close()


def cmd_retry(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Retry a failed draft."""
    draft_id = args.strip()
    if not draft_id:
        _send(adapter, chat_id, "Usage: /retry <draft\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(adapter, chat_id, f"Draft `{draft_id}` not found.")
            return

        if draft.status != "failed":
            _send(
                adapter,
                chat_id,
                f"Can only retry failed drafts (current status: {draft.status}).",
            )
            return

        update_draft(conn, draft_id, status="scheduled", retry_count=0, last_error=None)
        _send(adapter, chat_id, f"Draft `{draft_id[:12]}` queued for retry.")
    finally:
        conn.close()


def cmd_pause(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Pause a project."""
    project_id = args.strip()
    if not project_id:
        _send(adapter, chat_id, "Usage: /pause <project\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_project

        project = get_project(conn, project_id)
        if not project:
            _send(adapter, chat_id, f"Project `{project_id}` not found.")
            return

        if project.paused:
            _send(adapter, chat_id, f"Project `{project.name}` is already paused.")
            return

        conn.execute("UPDATE projects SET paused = 1 WHERE id = ?", (project_id,))
        conn.commit()
        _send(adapter, chat_id, f"Project `{project.name}` paused.")
    finally:
        conn.close()


def cmd_resume(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Resume a paused project."""
    project_id = args.strip()
    if not project_id:
        _send(adapter, chat_id, "Usage: /resume <project\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_project

        project = get_project(conn, project_id)
        if not project:
            _send(adapter, chat_id, f"Project `{project_id}` not found.")
            return

        if not project.paused:
            _send(adapter, chat_id, f"Project `{project.name}` is not paused.")
            return

        conn.execute("UPDATE projects SET paused = 0 WHERE id = ?", (project_id,))
        conn.commit()
        _send(adapter, chat_id, f"Project `{project.name}` resumed.")
    finally:
        conn.close()


def cmd_errors(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Show recent system errors. Optional: /errors <limit> or /errors <severity>."""
    from social_hook.db import operations as ops

    # Parse args: could be a number (limit) or a severity string
    limit = 10
    severity = None
    arg = args.strip().lower()
    if arg:
        if arg.isdigit():
            limit = min(int(arg), 50)
        elif arg in ("info", "warning", "error", "critical"):
            severity = arg
        else:
            _send(
                adapter,
                chat_id,
                "Usage: /errors [limit|severity]\nSeverity: info, warning, error, critical",
            )
            return

    # Default to ERROR/CRITICAL when no severity specified
    conn = _get_conn()
    try:
        errors = ops.get_recent_system_errors(
            conn, limit=limit, severity=severity or ["error", "critical"]
        )

        if not errors:
            _send(adapter, chat_id, "No recent errors found.")
            return

        lines = [f"*Recent Errors* ({len(errors)})"]
        for e in errors:
            ts = ""
            if e.created_at:
                ts = e.created_at.replace("T", " ")[:16]
            source = f" [{e.source}]" if e.source else ""
            msg = e.message[:80] + ("..." if len(e.message) > 80 else "")
            lines.append(f"- {e.severity.upper()}{source} {ts}\n  {msg}")

        _send(adapter, chat_id, "\n".join(lines))
    finally:
        conn.close()


def cmd_health(adapter: MessagingAdapter, chat_id: str, args: str, config: Any) -> None:
    """Show system health status and error counts."""
    from social_hook.db import operations as ops

    conn = _get_conn()
    try:
        error_counts = ops.get_error_health_status(conn)
        total = sum(error_counts.values())
        status = ops.compute_health_status(error_counts).upper()

        lines = [
            f"*System Health: {status}*",
            "",
            f"Errors in last 24h: {total}",
        ]
        if total > 0:
            for sev in ("critical", "error", "warning", "info"):
                count = error_counts.get(sev, 0)
                if count > 0:
                    lines.append(f"  {sev}: {count}")

        _send(adapter, chat_id, "\n".join(lines))
    finally:
        conn.close()
