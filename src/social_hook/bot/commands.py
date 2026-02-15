"""Telegram /command handlers."""

import logging
from typing import Any, Optional

import requests

from social_hook.bot.notifications import (
    format_draft_review,
    format_error_notification,
    get_review_buttons,
    send_notification,
    send_notification_with_buttons,
)

logger = logging.getLogger(__name__)


def _send(token: str, chat_id: str, text: str) -> bool:
    """Shortcut to send a plain message."""
    return send_notification(token, chat_id, text)


def _get_conn():
    """Get a fresh DB connection (per-request pattern for long-lived daemon)."""
    from social_hook.db import init_database
    from social_hook.filesystem import get_db_path

    return init_database(get_db_path())


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


def handle_command(message: dict, token: str, config: Optional[Any] = None) -> None:
    """Route a /command message to its handler.

    Args:
        message: Telegram message dict
        token: Bot API token
        config: Full Config object
    """
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "")
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
    }

    handler = handlers.get(cmd)
    if handler:
        handler(token, chat_id, args, config)
    else:
        _send(token, chat_id, f"Unknown command: /{cmd}\nUse /help for available commands.")


def handle_message(message: dict, token: str, config: Optional[Any] = None) -> None:
    """Handle a free-text message by routing through Gatekeeper.

    Args:
        message: Telegram message dict
        token: Bot API token
        config: Full Config object
    """
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "")

    if not text:
        return

    try:
        from social_hook.llm.factory import create_client
        from social_hook.llm.gatekeeper import Gatekeeper
        from social_hook.errors import ConfigError

        if not config:
            _send(token, chat_id, "Not configured. Run social-hook setup first.")
            return

        try:
            client = create_client(config.models.gatekeeper, config)
        except ConfigError:
            _send(token, chat_id, "Model provider not configured. Use /help for commands.")
            return

        gatekeeper = Gatekeeper(client)
        route = gatekeeper.route(user_message=text)

        if route.action.value == "handle_directly":
            _handle_gatekeeper_direct(token, chat_id, route, config)
        elif route.action.value == "escalate_to_expert":
            _handle_expert_escalation(token, chat_id, text, route, config)
    except Exception as e:
        logger.exception("Error routing message through Gatekeeper")
        _send(token, chat_id, f"Error processing message: {e}")


def _handle_gatekeeper_direct(
    token: str, chat_id: str, route: Any, config: Any
) -> None:
    """Handle a Gatekeeper direct action."""
    op = route.operation
    if op is None:
        _send(token, chat_id, "Understood.")
        return

    op_value = op.value if hasattr(op, "value") else str(op)
    params = route.params or {}

    if op_value == "approve":
        draft_id = params.get("draft_id", "")
        if draft_id:
            cmd_approve(token, chat_id, draft_id, config)
        else:
            _send(token, chat_id, "Please specify a draft ID to approve.")
    elif op_value == "reject":
        draft_id = params.get("draft_id", "")
        if draft_id:
            cmd_reject(token, chat_id, draft_id, config)
        else:
            _send(token, chat_id, "Please specify a draft ID to reject.")
    elif op_value == "schedule":
        draft_id = params.get("draft_id", "")
        time_str = params.get("time", "")
        cmd_schedule(token, chat_id, f"{draft_id} {time_str}".strip(), config)
    elif op_value == "cancel":
        draft_id = params.get("draft_id", "")
        cmd_cancel(token, chat_id, draft_id, config)
    elif op_value == "query":
        answer = params.get("answer", "I'll look into that.")
        _send(token, chat_id, answer)
    else:
        _send(token, chat_id, "Understood.")


def _handle_expert_escalation(
    token: str, chat_id: str, user_message: str, route: Any, config: Any
) -> None:
    """Handle an Expert escalation."""
    try:
        from social_hook.llm.factory import create_client
        from social_hook.llm.expert import Expert
        from social_hook.errors import ConfigError

        try:
            client = create_client(config.models.drafter, config)
        except ConfigError:
            _send(token, chat_id, "Model provider not configured. Use /help for commands.")
            return

        expert = Expert(client)

        result = expert.handle(
            draft=None,
            user_message=user_message,
            escalation_reason=route.escalation_reason or "user request",
            escalation_context=route.escalation_context,
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
                    save_context_note(
                        project.repo_path, result.context_note, source="telegram"
                    )
                    _send(token, chat_id, f"Context note saved for {project.name}.")
                else:
                    _send(token, chat_id, "No projects registered to save note to.")
            finally:
                conn.close()
        elif action == "refine_draft" and result.refined_content:
            _send(
                token,
                chat_id,
                f"*Refined draft:*\n\n```\n{result.refined_content[:500]}\n```",
            )
        elif action == "answer_question" and result.answer:
            _send(token, chat_id, result.answer)
        else:
            _send(token, chat_id, result.reasoning or "Understood.")
    except Exception as e:
        logger.exception("Error in expert escalation")
        _send(token, chat_id, f"Error: {e}")


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
    "register": "Register a new project. Must be done from terminal: `social-hook register /path/to/repo`",
    "approve": "Approve a draft for posting. Usage: /approve <draft\\_id>",
    "reject": "Reject a draft. Optional reason: /reject <draft\\_id> [reason]",
    "schedule": "Schedule a draft. Without time: optimal scheduling. /schedule <draft\\_id> [datetime]",
    "cancel": "Cancel a scheduled draft. Usage: /cancel <draft\\_id>",
    "retry": "Retry a failed draft. Usage: /retry <draft\\_id>",
    "pause": "Pause a project (stops evaluating commits). Usage: /pause <project\\_id>",
    "resume": "Resume a paused project. Usage: /resume <project\\_id>",
    "help": "Show help. For details on a command: /help <command>",
}


def cmd_help(token: str, chat_id: str, args: str, config: Any) -> None:
    """Show available commands. If args provided, show detailed help."""
    if args.strip():
        cmd_name = args.strip().lstrip("/")
        detail = HELP_DETAILS.get(cmd_name)
        if detail:
            _send(token, chat_id, f"*/{cmd_name}*\n\n{detail}")
        else:
            _send(token, chat_id, f"Unknown command: /{cmd_name}")
        return

    text = (
        "*Social Hook Bot*\n\n"
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
        "/help [command] - Show this message"
    )
    _send(token, chat_id, text)


def cmd_status(token: str, chat_id: str, args: str, config: Any) -> None:
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

        lines = [
            "*System Status*",
            "",
            f"Projects: {len(active)} active, {len(paused)} paused",
            f"Pending drafts: {len(drafts)}",
            f"Approved: {len(approved)}",
            f"Scheduled: {len(scheduled)}",
        ]
        _send(token, chat_id, "\n".join(lines))
    finally:
        conn.close()


def cmd_pending(token: str, chat_id: str, args: str, config: Any) -> None:
    """Show pending drafts with action buttons."""
    conn = _get_conn()
    try:
        from social_hook.db import get_all_pending_drafts

        drafts = get_all_pending_drafts(conn)
        if not drafts:
            _send(token, chat_id, "No pending drafts.")
            return

        for d in drafts[:10]:
            status_icon = {"draft": "📝", "approved": "✅", "scheduled": "⏰"}.get(
                d.status, "❓"
            )
            text = (
                f"{status_icon} `{d.id[:12]}` [{d.platform}]\n"
                f"{d.content[:80]}..."
            )
            buttons = [
                [
                    {"text": "Review", "callback_data": f"review:{d.id}"},
                    {"text": "Quick Approve", "callback_data": f"quick_approve:{d.id}"},
                ],
            ]
            send_notification_with_buttons(token, chat_id, text, buttons)

        if len(drafts) > 10:
            _send(token, chat_id, f"...and {len(drafts) - 10} more")
    finally:
        conn.close()


def cmd_scheduled(token: str, chat_id: str, args: str, config: Any) -> None:
    """Show scheduled drafts with cancel buttons."""
    conn = _get_conn()
    try:
        from social_hook.db import get_all_pending_drafts

        all_pending = get_all_pending_drafts(conn)
        scheduled = [d for d in all_pending if d.status == "scheduled"]
        if not scheduled:
            _send(token, chat_id, "No scheduled drafts.")
            return

        for d in scheduled[:10]:
            time_str = d.scheduled_time or "no time"
            text = f"⏰ `{d.id[:12]}` [{d.platform}] {time_str}"
            buttons = [
                [{"text": "Cancel", "callback_data": f"cancel:{d.id}"}],
            ]
            send_notification_with_buttons(token, chat_id, text, buttons)
    finally:
        conn.close()


def cmd_projects(token: str, chat_id: str, args: str, config: Any) -> None:
    """List registered projects."""
    conn = _get_conn()
    try:
        from social_hook.db import get_all_projects

        projects = get_all_projects(conn)
        if not projects:
            _send(token, chat_id, "No registered projects.")
            return

        lines = ["*Registered Projects*", ""]
        for p in projects:
            status = "⏸️ paused" if p.paused else "▶️ active"
            lines.append(f"{status} `{p.id[:12]}` {p.name}")
        _send(token, chat_id, "\n".join(lines))
    finally:
        conn.close()


def cmd_usage(token: str, chat_id: str, args: str, config: Any) -> None:
    """Show token usage summary. Use '/usage recent [N]' for individual operations."""
    arg = args.strip()

    conn = _get_conn()
    try:
        # Handle '/usage recent [N]'
        if arg.startswith("recent"):
            from social_hook.db import get_recent_usage

            parts = arg.split()
            limit = int(parts[1]) if len(parts) > 1 else 10
            entries = get_recent_usage(conn, limit=limit)
            if not entries:
                _send(token, chat_id, "No usage data found.")
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
            _send(token, chat_id, "\n".join(lines))
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
        _send(token, chat_id, "\n".join(lines))
    finally:
        conn.close()


def cmd_review(token: str, chat_id: str, args: str, config: Any) -> None:
    """Review a draft with full details and action buttons."""
    draft_id = args.strip()
    if not draft_id:
        _send(token, chat_id, "Usage: /review <draft\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_decision, get_draft, get_draft_tweets, get_project

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        project = get_project(conn, draft.project_id)
        project_name = project.name if project else "unknown"

        decision = get_decision(conn, draft.decision_id)
        commit_hash = decision.commit_hash[:8] if decision else "unknown"
        commit_message = decision.reasoning[:50] if decision else ""

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
        )
        buttons = get_review_buttons(draft.id)
        send_notification_with_buttons(token, chat_id, msg, buttons)
    finally:
        conn.close()


def cmd_register(token: str, chat_id: str, args: str, config: Any) -> None:
    """Send instructions for registering a project (requires terminal)."""
    _send(
        token,
        chat_id,
        "Registration requires filesystem access.\n\n"
        "Use from terminal:\n"
        "`social-hook register /path/to/repo`",
    )


def cmd_approve(token: str, chat_id: str, args: str, config: Any) -> None:
    """Approve a draft for posting."""
    draft_id = args.strip()
    if not draft_id:
        _send(token, chat_id, "Usage: /approve <draft\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        if draft.status not in ("draft", "approved"):
            _send(
                token, chat_id, f"Cannot approve draft with status: {draft.status}"
            )
            return

        update_draft(conn, draft_id, status="approved")
        _send(token, chat_id, f"Draft `{draft_id[:12]}` approved.")
    finally:
        conn.close()


def cmd_reject(token: str, chat_id: str, args: str, config: Any) -> None:
    """Reject a draft with optional reason."""
    parts = args.strip().split(None, 1)
    if not parts:
        _send(token, chat_id, "Usage: /reject <draft\\_id> [reason]")
        return

    draft_id = parts[0]
    reason = parts[1] if len(parts) > 1 else None

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        update_kwargs = {"status": "rejected"}
        if reason:
            update_kwargs["last_error"] = f"Rejected: {reason}"
        update_draft(conn, draft_id, **update_kwargs)

        msg = f"Draft `{draft_id[:12]}` rejected."
        if reason:
            msg += f"\nReason: {reason}"
        _send(token, chat_id, msg)
    finally:
        conn.close()


def cmd_schedule(token: str, chat_id: str, args: str, config: Any) -> None:
    """Schedule a draft for posting."""
    parts = args.strip().split(None, 1)
    if not parts:
        _send(token, chat_id, "Usage: /schedule <draft\\_id> [datetime]")
        return

    draft_id = parts[0]
    time_str = parts[1] if len(parts) > 1 else None

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        if time_str:
            update_draft(conn, draft_id, status="scheduled", scheduled_time=time_str)
            _send(
                token,
                chat_id,
                f"Draft `{draft_id[:12]}` scheduled for {time_str}.",
            )
        else:
            # Calculate optimal time
            from social_hook.scheduling import calculate_optimal_time

            result = calculate_optimal_time(
                conn,
                draft.project_id,
                tz=config.scheduling.timezone if config else "UTC",
                max_posts_per_day=config.scheduling.max_posts_per_day if config else 3,
                min_gap_minutes=config.scheduling.min_gap_minutes if config else 30,
                optimal_days=config.scheduling.optimal_days if config else None,
                optimal_hours=config.scheduling.optimal_hours if config else None,
            )
            scheduled_str = result.datetime.isoformat()
            update_draft(
                conn, draft_id, status="scheduled", scheduled_time=scheduled_str
            )
            _send(
                token,
                chat_id,
                f"Draft `{draft_id[:12]}` scheduled for {scheduled_str}\n{result.time_reason}",
            )
    finally:
        conn.close()


def cmd_cancel(token: str, chat_id: str, args: str, config: Any) -> None:
    """Cancel a draft."""
    draft_id = args.strip()
    if not draft_id:
        _send(token, chat_id, "Usage: /cancel <draft\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        update_draft(conn, draft_id, status="cancelled")
        _send(token, chat_id, f"Draft `{draft_id[:12]}` cancelled.")
    finally:
        conn.close()


def cmd_retry(token: str, chat_id: str, args: str, config: Any) -> None:
    """Retry a failed draft."""
    draft_id = args.strip()
    if not draft_id:
        _send(token, chat_id, "Usage: /retry <draft\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_draft, update_draft

        draft = get_draft(conn, draft_id)
        if not draft:
            _send(token, chat_id, f"Draft `{draft_id}` not found.")
            return

        if draft.status != "failed":
            _send(
                token,
                chat_id,
                f"Can only retry failed drafts (current status: {draft.status}).",
            )
            return

        update_draft(conn, draft_id, status="scheduled", retry_count=0, last_error=None)
        _send(token, chat_id, f"Draft `{draft_id[:12]}` queued for retry.")
    finally:
        conn.close()


def cmd_pause(token: str, chat_id: str, args: str, config: Any) -> None:
    """Pause a project."""
    project_id = args.strip()
    if not project_id:
        _send(token, chat_id, "Usage: /pause <project\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_project

        project = get_project(conn, project_id)
        if not project:
            _send(token, chat_id, f"Project `{project_id}` not found.")
            return

        if project.paused:
            _send(token, chat_id, f"Project `{project.name}` is already paused.")
            return

        conn.execute(
            "UPDATE projects SET paused = 1 WHERE id = ?", (project_id,)
        )
        conn.commit()
        _send(token, chat_id, f"Project `{project.name}` paused.")
    finally:
        conn.close()


def cmd_resume(token: str, chat_id: str, args: str, config: Any) -> None:
    """Resume a paused project."""
    project_id = args.strip()
    if not project_id:
        _send(token, chat_id, "Usage: /resume <project\\_id>")
        return

    conn = _get_conn()
    try:
        from social_hook.db import get_project

        project = get_project(conn, project_id)
        if not project:
            _send(token, chat_id, f"Project `{project_id}` not found.")
            return

        if not project.paused:
            _send(token, chat_id, f"Project `{project.name}` is not paused.")
            return

        conn.execute(
            "UPDATE projects SET paused = 0 WHERE id = ?", (project_id,)
        )
        conn.commit()
        _send(token, chat_id, f"Project `{project.name}` resumed.")
    finally:
        conn.close()
