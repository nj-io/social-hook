"""One-shot trigger: commit evaluation and draft creation pipeline."""

import logging
import subprocess
import sys
from typing import Any

from social_hook.config.yaml import load_full_config
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.errors import ConfigError, DatabaseError
from social_hook.filesystem import generate_id, get_db_path
from social_hook.llm.dry_run import DryRunContext
from social_hook.llm.prompts import assemble_evaluator_context
from social_hook.models import CommitInfo, Decision, is_draftable

logger = logging.getLogger(__name__)


def parse_commit_info(commit_hash: str, repo_path: str) -> CommitInfo:
    """Parse commit info from git.

    Args:
        commit_hash: Git commit hash
        repo_path: Path to the git repository

    Returns:
        CommitInfo with parsed data
    """
    try:
        # Get full commit message (subject + body)
        message = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%B", commit_hash],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Get author date (ISO 8601 with timezone)
        timestamp = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%aI", commit_hash],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Get parent commit's author date (fails with exit 128 on first commit)
        parent_result = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%aI", f"{commit_hash}~1"],
            capture_output=True,
            text=True,
        )
        parent_timestamp = parent_result.stdout.strip() if parent_result.returncode == 0 else None

        # Get stat summary
        stat_output = subprocess.run(
            ["git", "-C", repo_path, "show", "--stat", "--format=", commit_hash],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Parse files changed from stat
        files_changed = []
        insertions = 0
        deletions = 0
        for line in stat_output.split("\n"):
            line = line.strip()
            if "|" in line and not line.startswith(" "):
                # "filename | N +++--"
                parts = line.split("|")
                if parts:
                    files_changed.append(parts[0].strip())
            elif "changed" in line:
                # Summary line: "N files changed, N insertions(+), N deletions(-)"
                if "insertion" in line:
                    for part in line.split(","):
                        part = part.strip()
                        if "insertion" in part:
                            insertions = int(part.split()[0])
                        elif "deletion" in part:
                            deletions = int(part.split()[0])

        # Get diff
        diff = subprocess.run(
            ["git", "-C", repo_path, "diff", f"{commit_hash}~1..{commit_hash}"],
            capture_output=True,
            text=True,
        ).stdout

        # Fallback for first commit (no parent)
        if not diff:
            diff = subprocess.run(
                ["git", "-C", repo_path, "show", "--format=", commit_hash],
                capture_output=True,
                text=True,
            ).stdout

        return CommitInfo(
            hash=commit_hash,
            message=message,
            diff=diff,
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
            timestamp=timestamp,
            parent_timestamp=parent_timestamp,
        )
    except subprocess.CalledProcessError:
        # Return minimal info if git commands fail
        return CommitInfo(
            hash=commit_hash,
            message="(unable to parse)",
            diff="",
        )


def git_remote_origin(repo_path: str) -> str | None:
    """Get the git remote origin URL for worktree detection.

    Args:
        repo_path: Path to the git repository

    Returns:
        Remote origin URL, or None if not available
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def _get_current_branch(repo_path: str) -> str | None:
    """Get the current git branch name. Returns None for detached HEAD."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        return None if branch == "HEAD" else branch
    except (subprocess.CalledProcessError, OSError):
        return None


def run_trigger(
    commit_hash: str,
    repo_path: str,
    dry_run: bool = False,
    config_path: str | None = None,
    verbose: bool = False,
    show_prompt: bool = False,
) -> int:
    """Run the commit-to-draft trigger pipeline.

    Exit codes:
        0 = success or unregistered (silent)
        1 = config error
        2 = DB error
        3 = LLM API error
        4 = Telegram error (non-fatal, draft still saved)

    Args:
        commit_hash: Git commit hash to evaluate
        repo_path: Path to the repository
        dry_run: If True, skip DB writes and real API calls
        config_path: Optional override for config location
        verbose: If True, print detailed output

    Returns:
        Exit code (0-4)
    """
    # 1. Load config
    try:
        config = load_full_config(
            yaml_path=config_path if config_path else None,
        )
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        return 1

    # 2. Initialize DB
    try:
        db_path = get_db_path()
        conn = init_database(db_path)
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        if verbose:
            print(f"Database error: {e}", file=sys.stderr)
        return 2

    db = DryRunContext(conn, dry_run=dry_run)

    # 3. Check registration
    project = ops.get_project_by_path(conn, repo_path)
    if project is None:
        # Try worktree detection via origin
        origin = git_remote_origin(repo_path)
        if origin:
            projects = ops.get_project_by_origin(conn, origin)
            if projects:
                project = projects[0]  # Use first match

    if project is None:
        # Not registered - exit silently
        if verbose:
            print(f"Repository {repo_path} is not registered. Exiting.")
        conn.close()
        return 0

    if project.paused:
        if verbose:
            print(f"Project {project.name} is paused. Skipping.")
        conn.close()
        return 0

    if project.trigger_branch:
        current_branch = _get_current_branch(repo_path)
        if current_branch != project.trigger_branch:
            branch_desc = current_branch or "(detached HEAD)"
            if verbose:
                print(
                    f"Branch '{branch_desc}' doesn't match trigger branch "
                    f"'{project.trigger_branch}'. Skipping."
                )
            conn.close()
            return 0

    # 4. Load project config
    from social_hook.config.project import load_project_config

    project_config = load_project_config(repo_path)

    # 5. Parse commit (needed for timestamp-filtered context)
    commit = parse_commit_info(commit_hash, repo_path)

    # 6. Assemble context (with commit timestamps for narrative filtering)
    context = assemble_evaluator_context(
        db,
        project.id,
        project_config,
        commit_timestamp=commit.timestamp,
        parent_timestamp=commit.parent_timestamp,
    )

    # 6b. Auto-discovery: seed project summary if missing
    if getattr(context, "project_summary", None) is None:
        try:
            from social_hook.llm.discovery import discover_project
            from social_hook.llm.factory import create_client as _create_client

            discovery_client = _create_client(config.models.evaluator, config, verbose=verbose)
            summary, selected_files = discover_project(
                client=discovery_client,
                repo_path=repo_path,
                project_docs=project_config.context.project_docs if project_config else [],
                max_doc_tokens=project_config.context.max_doc_tokens if project_config else 10000,
                db=db,
                project_id=project.id,
            )
            if summary:
                db.update_project_summary(project.id, summary)
                db.update_discovery_files(project.id, selected_files)
                context.project_summary = summary
                if verbose:
                    print(f"Project discovery complete: {len(selected_files)} files analyzed")
        except Exception as e:
            logger.warning(f"Project discovery failed (non-fatal): {e}")
            if verbose:
                print(f"Project discovery skipped: {e}", file=sys.stderr)

    if verbose:
        print(f"Evaluating commit {commit.hash[:8]}: {commit.message}")

    # 7. Evaluate
    from social_hook.llm.evaluator import Evaluator
    from social_hook.llm.factory import create_client

    try:
        evaluator_client = create_client(config.models.evaluator, config, verbose=verbose)
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        conn.close()
        return 1

    # Build platform summaries for evaluator context
    platform_summaries = []
    for pname, pcfg in config.platforms.items():
        if pcfg.enabled:
            summary = f"{pname} ({pcfg.priority})"
            if pcfg.type == "custom" and pcfg.description:
                summary += f" — {pcfg.description}"
            platform_summaries.append(summary)

    try:
        evaluator = Evaluator(evaluator_client)
        evaluation = evaluator.evaluate(
            commit,
            context,
            db,
            show_prompt=show_prompt,
            platform_summaries=platform_summaries or None,
            media_config=config.media_generation,
            media_guidance=project_config.media_guidance if project_config else None,
            strategy_config=project_config.strategy if project_config else None,
            summary_config=project_config.summary if project_config else None,
        )
    except Exception as e:
        logger.error(f"LLM API error during evaluation: {e}")
        if verbose:
            print(f"LLM API error: {e}", file=sys.stderr)
        conn.close()
        return 3

    # 8. Map evaluation output to Decision
    analysis = evaluation.commit_analysis
    target = evaluation.targets.get("default")
    if target is None:
        logger.error("Evaluation missing 'default' target")
        if verbose:
            print("Error: evaluation missing 'default' target", file=sys.stderr)
        conn.close()
        return 3

    def _val(x):
        return x.value if hasattr(x, "value") else x

    decision_type = _val(target.action)  # "draft", "hold", or "skip"

    decision = Decision(
        id=generate_id("decision"),
        project_id=project.id,
        commit_hash=commit_hash,
        decision=decision_type,
        reasoning=target.reason,
        commit_message=commit.message,
        angle=target.angle,
        episode_type=_val(target.episode_type),
        episode_tags=analysis.episode_tags,
        post_category=_val(target.post_category),
        arc_id=target.arc_id,
        media_tool=_val(target.media_tool),
        targets={"default": target.model_dump()},
        commit_summary=analysis.summary,
        consolidate_with=target.consolidate_with,
    )

    # Hold count enforcement
    if decision_type == "hold":
        max_hold = project_config.context.max_hold_count if project_config else 5
        current_held = ops.get_held_decisions(conn, project.id)
        if len(current_held) >= max_hold:
            logger.warning(f"Hold limit reached ({max_hold}), forcing skip for {commit_hash[:8]}")
            decision.decision = "skip"
            decision_type = "skip"

    db.insert_decision(decision)
    db.emit_data_event("decision", "created", decision.id, project.id)

    # 8b. Arc activation: create new arc or link to existing
    if is_draftable(decision.decision):
        _arc_id = target.arc_id
        _new_arc_theme = target.new_arc_theme

        if _new_arc_theme and not _arc_id:
            try:
                from social_hook.narrative.arcs import create_arc as _create_arc

                new_arc_id = _create_arc(db.conn, project.id, _new_arc_theme)
                db.update_decision(decision.id, arc_id=new_arc_id)
                decision.arc_id = new_arc_id
                if verbose:
                    print(f"Created new arc: {new_arc_id} ({_new_arc_theme})")
            except Exception as e:
                logger.warning(f"Arc creation failed (non-fatal): {e}")
                if verbose:
                    print(f"Arc creation skipped: {e}", file=sys.stderr)

    # 8c. Held decision absorption
    if is_draftable(decision.decision) and target.consolidate_with:
        valid_ids = [d.id for d in context.held_decisions]
        absorbed = [cid for cid in target.consolidate_with if cid in valid_ids]
        if absorbed and not dry_run:
            batch_id = generate_id("batch")
            ops.mark_decisions_processed(conn, absorbed, batch_id)

    # 8d. Queue actions
    if evaluation.queue_actions:
        for _target_name, actions in evaluation.queue_actions.items():
            for qa in actions:
                action_type = qa.action
                if action_type == "merge":
                    continue  # handled after draft creation
                if not dry_run:
                    draft_ref = ops.get_draft(conn, qa.draft_id)
                    if not draft_ref or draft_ref.status not in ("draft", "approved", "scheduled"):
                        if verbose:
                            print(f"Queue action skipped: draft {qa.draft_id} not actionable")
                        continue
                    ops.execute_queue_action(conn, action_type, qa.draft_id, qa.reason)
                if verbose:
                    print(f"Queue action: {action_type} draft {qa.draft_id}")

    # 8e. Send decision notification for non-draftable decisions
    if (
        not dry_run
        and config.notification_level == "all_decisions"
        and not is_draftable(decision.decision)
    ):
        _send_decision_notification(config, project, commit, decision)

    if verbose:
        print(f"Decision: {decision_type}")
        print(f"Reasoning: {target.reason}")

    # 9. If draftable, create drafts per platform
    if is_draftable(decision.decision):
        from social_hook.compat import make_eval_compat
        from social_hook.drafting import draft_for_platforms

        eval_compat = make_eval_compat(evaluation, decision.decision)

        # Duplicate intro check
        draft_results: list[Any] | None = None
        if not context.audience_introduced:
            existing_intro = ops.get_intro_draft(conn, project.id)
            if existing_intro:
                if verbose:
                    print("Intro draft already exists, skipping new draft creation")
                draft_results = []

        if draft_results is None:
            draft_results = draft_for_platforms(
                config,
                conn,
                db,
                project,
                decision_id=decision.id,
                evaluation=eval_compat,
                context=context,
                commit=commit,
                project_config=project_config,
                dry_run=dry_run,
                verbose=verbose,
            )

        # Audience introduced lifecycle
        if draft_results and not context.audience_introduced:
            for r in draft_results:
                if not dry_run:
                    ops.update_draft(conn, r.draft.id, is_intro=True)
                r.draft.is_intro = True
            if not dry_run:
                ops.set_audience_introduced(conn, project.id, True)

        # Merge queue actions — after draft creation
        merge_actions = [
            qa
            for actions in (evaluation.queue_actions or {}).values()
            for qa in actions
            if qa.action == "merge"
        ]
        if merge_actions and draft_results and not dry_run:
            for qa in merge_actions:
                ops.execute_queue_action(conn, "supersede", qa.draft_id, qa.reason)

        # Increment arc post count if drafts were created for an arc
        if draft_results and decision.arc_id:
            try:
                from social_hook.narrative.arcs import increment_arc_post_count

                increment_arc_post_count(db.conn, decision.arc_id)
                if verbose:
                    print(f"Incremented post count for arc: {decision.arc_id}")
            except Exception as e:
                logger.warning(f"Arc post count increment failed (non-fatal): {e}")

        # Notifications
        if not dry_run:
            if draft_results:
                from social_hook.bot.notifications import (
                    format_draft_review,
                    get_review_buttons_normalized,
                )
                from social_hook.messaging.base import OutboundMessage as _OutboundMessage
                from social_hook.notifications import broadcast_notification

                for result in draft_results:
                    draft = result.draft
                    schedule = result.schedule
                    thread_tweets = result.thread_tweets
                    is_thread = bool(thread_tweets)
                    tweet_count = len(thread_tweets) if is_thread else None
                    suggested_time_str = schedule.datetime.strftime("%Y-%m-%d %H:%M UTC")
                    media_info = (
                        f"{draft.media_type} ({len(draft.media_paths)} file)"
                        if draft.media_paths
                        else None
                    )

                    msg_text = format_draft_review(
                        project_name=project.name,
                        commit_hash=commit.hash[:8],
                        commit_message=commit.message,
                        platform=draft.platform,
                        content=draft.content,
                        suggested_time=suggested_time_str,
                        draft_id=draft.id,
                        is_thread=is_thread,
                        tweet_count=tweet_count,
                        media_info=media_info,
                    )
                    buttons = get_review_buttons_normalized(draft.id)
                    msg = _OutboundMessage(text=msg_text, buttons=buttons)
                    broadcast_notification(
                        config,
                        msg,
                        media=draft.media_paths or None,
                        chat_context=(draft.id, project.id),
                    )
            elif config.notification_level != "drafts_only":
                _send_decision_notification(config, project, commit, decision)

    conn.close()
    return 0


def _send_decision_notification(config, project, commit, decision):
    """Send a decision notification to all configured channels."""
    from social_hook.messaging.base import OutboundMessage
    from social_hook.notifications import broadcast_notification

    reasoning_preview = (
        (decision.reasoning[:200] + "...") if len(decision.reasoning) > 200 else decision.reasoning
    )
    msg_text = (
        f"Commit evaluated\n\n"
        f"Project: {project.name}\n"
        f"Commit: {commit.hash[:8]} - {commit.message}\n"
        f"Decision: {decision.decision}\n"
        f"Reasoning: {reasoning_preview}"
    )
    broadcast_notification(config, OutboundMessage(text=msg_text))


# Backward-compatible re-exports — tests import these from trigger.py
from social_hook.drafting import (  # noqa: E402, F401
    _generate_media,
    _needs_thread,
    _parse_thread_tweets,
)
