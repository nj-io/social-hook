"""Scheduler tick: posts due drafts and manages lock file."""

import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from social_hook.adapters.platform.factory import resolve_platform_creds
from social_hook.adapters.platform.registry import AdapterRegistry
from social_hook.config.yaml import load_full_config
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.error_feed import ErrorSeverity, ensure_error_feed, error_feed
from social_hook.errors import ConfigError
from social_hook.filesystem import generate_id, get_base_path, get_db_path
from social_hook.models import CommitInfo, Decision, Post
from social_hook.notifications import send_notification
from social_hook.rate_limits import check_rate_limit
from social_hook.scheduling import calculate_optimal_time
from social_hook.trigger import parse_commit_info, run_trigger

logger = logging.getLogger(__name__)

# Process-scoped adapter cache — persists rate limit state and token refreshers across ticks.
# Clears on process restart. Keyed by account name (targets) or platform name (legacy).
_registry = AdapterRegistry()

# Backwards-compat alias — callers should migrate to error_feed.ensure_error_feed
_ensure_error_feed = ensure_error_feed


def _check_per_account_gap(conn, config, draft) -> bool:
    """Check if posting this draft would violate the per-account posting gap.

    For targets-path drafts (draft.target_id set), finds all targets sharing the
    same account and computes the effective gap as the maximum min_gap_minutes
    across those targets. This prevents the loosest target from bypassing the
    tightest target's gap.

    Returns True if gap is satisfied (OK to post), False if too soon.
    """
    target_id = draft.target_id
    if not target_id:
        return True  # Legacy path, no per-account gap

    targets = getattr(config, "targets", None)
    if not targets or not isinstance(targets, dict):
        return True

    target = targets.get(target_id)
    if not target:
        logger.warning("Target '%s' not found in config for draft %s", target_id, draft.id)
        return True

    account_name = target.account
    if not account_name:
        return True  # No account (preview mode)

    # Find all targets sharing this account
    from social_hook.config.platforms import FREQUENCY_PARAMS

    sibling_target_ids = []
    max_gap = 0
    for tname, tcfg in targets.items():
        if tcfg.account == account_name:
            sibling_target_ids.append(tname)
            # Resolve min_gap_minutes for this target
            frequency = tcfg.frequency or "moderate"
            freq_params = FREQUENCY_PARAMS.get(frequency, FREQUENCY_PARAMS["moderate"])
            gap = freq_params["min_gap_minutes"]
            sched = tcfg.scheduling or {}
            gap = sched.get("min_gap_minutes", gap)
            if gap > max_gap:
                max_gap = gap

    if max_gap <= 0:
        return True

    last_post_time = ops.get_last_post_time_by_account(conn, sibling_target_ids)
    if last_post_time is None:
        return True

    elapsed = (datetime.now(timezone.utc) - last_post_time).total_seconds() / 60
    if elapsed >= max_gap:
        return True
    else:
        logger.info(
            "Per-account gap not met for account '%s': %.0f min elapsed, need %d min",
            account_name,
            elapsed,
            max_gap,
        )
        return False


def _check_cross_account_gap(conn, config, draft) -> bool:
    """Check if posting this draft would violate the cross-account platform gap.

    Reads platform_settings.cross_account_gap_minutes for the draft's platform.
    Checks last post time across ALL accounts on this platform (not just this account).
    Applies fixed jitter: ~33% of gap value, random per check.
    Returns True if gap is satisfied (OK to post), False if too soon.
    """
    platform = draft.platform
    platform_settings = getattr(config, "platform_settings", None)
    if not platform_settings or not isinstance(platform_settings, dict):
        return True  # no platform_settings configured
    gap_config = platform_settings.get(platform)
    if not gap_config or gap_config.cross_account_gap_minutes <= 0:
        return True  # disabled

    base_gap = gap_config.cross_account_gap_minutes
    jitter = random.randint(0, int(base_gap * 0.33))
    effective_gap = base_gap + jitter

    last_post_time = ops.get_last_post_time_by_platform(conn, platform)
    if last_post_time is None:
        return True

    elapsed = (datetime.now(timezone.utc) - last_post_time).total_seconds() / 60
    if elapsed >= effective_gap:
        return True
    else:
        logger.info(
            "Cross-account gap not met for %s: %.0f min elapsed, need %d min",
            platform,
            elapsed,
            effective_gap,
        )
        return False


def record_post_success(conn, draft, result, config, project_name: str, dry_run: bool = False):
    """Record a successful post: update draft, create Post record, emit events, notify."""
    ops.update_draft(conn, draft.id, status="posted")
    ops.emit_data_event(conn, "draft", "updated", draft.id, draft.project_id)

    # Populate post metadata from decision and draft structure
    topic_tags: list[str] = []
    feature_tags: list[str] = []
    is_thread_head = False

    if draft.decision_id:
        decision = ops.get_decision(conn, draft.decision_id)
        if decision:
            topic_tags = decision.episode_tags or []
            # feature_tags: same source — episode_tags covers both for now
            feature_tags = []
        else:
            logger.warning("Decision %s not found for draft %s", draft.decision_id, draft.id)

    # Thread head: draft has thread tweets
    draft_tweets = ops.get_draft_tweets(conn, draft.id)
    if draft_tweets:
        is_thread_head = True

    post = Post(
        id=generate_id("post"),
        draft_id=draft.id,
        project_id=draft.project_id,
        platform=draft.platform,
        external_id=result.external_id,
        external_url=result.external_url,
        content=draft.content,
        target_id=draft.target_id,
        topic_tags=topic_tags,
        feature_tags=feature_tags,
        is_thread_head=is_thread_head,
    )
    ops.insert_post(conn, post)
    ops.emit_data_event(conn, "post", "created", post.id, draft.project_id)

    # Update topic status when a draft with topic_id is posted
    if draft.topic_id and not dry_run:
        ops.update_topic_status(conn, draft.topic_id, "covered")
        logger.info("Topic %s status -> covered (draft %s posted)", draft.topic_id, draft.id)

    send_notification(
        config,
        f"*Posted successfully*\n\n"
        f"Project: {project_name}\n"
        f"Platform: {draft.platform}\n"
        f"URL: {result.external_url or 'N/A'}\n\n"
        f"```\n{draft.content[:300]}\n```",
        dry_run=dry_run,
    )
    return post


# =============================================================================
# Lock file management
# =============================================================================


def get_lock_path() -> Path:
    """Get the path to the scheduler lock file."""
    return get_base_path() / "scheduler.lock"


def get_lock_pid(lock_path: Path) -> int | None:
    """Read PID from lock file.

    Returns:
        PID as int, or None if file doesn't exist or is invalid
    """
    if not lock_path.exists():
        return None
    try:
        content = lock_path.read_text().strip()
        return int(content)
    except (ValueError, OSError):
        return None


def is_lock_stale(lock_path: Path) -> bool:
    """Check if a lock file is stale (process no longer running).

    Args:
        lock_path: Path to the lock file

    Returns:
        True if lock is stale (can be cleaned up)
    """
    pid = get_lock_pid(lock_path)
    if pid is None:
        return True

    try:
        os.kill(pid, 0)  # Signal 0 = check if process exists
        return False  # Process is alive
    except ProcessLookupError:
        return True  # Process is dead
    except PermissionError:
        return False  # Process exists but we can't signal it


def acquire_lock(lock_path: Path | None = None) -> bool:
    """Acquire the scheduler lock.

    Args:
        lock_path: Override lock file path (for testing)

    Returns:
        True if lock was acquired, False if held by another process
    """
    if lock_path is None:
        lock_path = get_lock_path()

    if lock_path.exists():
        if not is_lock_stale(lock_path):
            return False
        # Stale lock - clean up
        logger.info(f"Cleaning up stale lock file: {lock_path}")
        lock_path.unlink()

    # Create lock with our PID
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()))
    return True


def release_lock(lock_path: Path | None = None) -> None:
    """Release the scheduler lock.

    Args:
        lock_path: Override lock file path (for testing)
    """
    if lock_path is None:
        lock_path = get_lock_path()

    if lock_path.exists():
        # Only remove if it's our lock
        pid = get_lock_pid(lock_path)
        if pid == os.getpid():
            lock_path.unlink(missing_ok=True)


# =============================================================================
# Scheduler tick
# =============================================================================


def promote_deferred_drafts(conn, config, dry_run=False):
    """Try to promote deferred drafts to scheduled when slots open up.

    Iterates deferred drafts in FIFO order. For each:
    - If platform is gone/disabled, cancel the draft.
    - Otherwise, recalculate scheduling. If a slot is available, promote
      to scheduled with the computed time.

    Args:
        conn: Database connection.
        config: Full Config object.
        dry_run: If True, skip notifications.

    Returns:
        Number of drafts promoted.
    """
    from social_hook.config.platforms import resolve_platform

    deferred = ops.get_deferred_drafts(conn)
    promoted = 0

    for draft in deferred:
        # Guard: platform gone or disabled
        pcfg = config.platforms.get(draft.platform)
        if not pcfg or not pcfg.enabled:
            ops.update_draft(conn, draft.id, status="cancelled")
            ops.emit_data_event(conn, "draft", "updated", draft.id, draft.project_id)
            logger.info(
                f"Deferred draft {draft.id} cancelled: platform '{draft.platform}' disabled/removed"
            )
            continue

        resolved = resolve_platform(draft.platform, pcfg, config.scheduling)
        schedule = calculate_optimal_time(
            conn,
            draft.project_id,
            platform=draft.platform,
            tz=config.scheduling.timezone,
            max_posts_per_day=resolved.max_posts_per_day,
            min_gap_minutes=resolved.min_gap_minutes,
            optimal_days=resolved.optimal_days,
            optimal_hours=resolved.optimal_hours,
            max_per_week=config.scheduling.max_per_week,
        )

        if schedule.deferred:
            # Still no slot available, stays deferred
            continue

        # Promote to scheduled
        ops.update_draft(
            conn,
            draft.id,
            status="scheduled",
            scheduled_time=schedule.datetime.isoformat(),
        )
        ops.emit_data_event(conn, "draft", "updated", draft.id, draft.project_id)
        promoted += 1

        project = ops.get_project(conn, draft.project_id)
        project_name = project.name if project else "Unknown"
        send_notification(
            config,
            f"*Deferred draft promoted*\n\n"
            f"Project: {project_name}\n"
            f"Platform: {draft.platform}\n"
            f"Scheduled: {schedule.datetime.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"```\n{draft.content[:300]}\n```",
            dry_run=dry_run,
        )

    return promoted


def _drain_deferred_evaluations(conn, config, dry_run):
    """Process deferred evaluations when rate limit slots are available.

    Called during scheduler_tick after promote_deferred_drafts. For each project,
    drains deferred_eval decisions by re-triggering evaluation (individual mode)
    or combining them into a single evaluator call (batch mode).

    Skipped entirely in dry_run mode since drain deletes decisions before
    re-evaluating, which is destructive.
    """
    if dry_run:
        return

    projects = ops.get_all_projects(conn)

    for project in projects:
        if project.paused:
            continue

        deferred = ops.get_deferred_eval_decisions(conn, project.id)
        if not deferred:
            continue

        if config.rate_limits.batch_throttled:
            _drain_batch(conn, config, project, deferred)
        else:
            _drain_individual(conn, config, project, deferred)


def _drain_individual(conn, config, project, deferred):
    """Drain deferred_eval decisions one at a time, re-checking rate limits."""
    for d in deferred:
        gate = check_rate_limit(conn, config.rate_limits)
        if gate.blocked:
            break

        commit_hash = d.commit_hash
        ops.delete_decision(conn, d.id)

        try:
            run_trigger(
                commit_hash=commit_hash,
                repo_path=project.repo_path,
                dry_run=False,
                trigger_source="drain",
            )
        except Exception as e:
            logger.error(
                "Drain failed for commit %s (project %s): %s",
                commit_hash,
                project.id,
                e,
            )
            # Re-insert deferred_eval only if run_trigger didn't create a real decision
            existing = conn.execute(
                "SELECT id FROM decisions WHERE project_id = ? AND commit_hash = ?",
                (project.id, commit_hash),
            ).fetchone()
            if not existing:
                ops.insert_decision(
                    conn,
                    Decision(
                        id=generate_id("decision"),
                        project_id=project.id,
                        commit_hash=commit_hash,
                        decision="deferred_eval",
                        reasoning=f"Drain failed: {e}",
                        trigger_source="commit",
                    ),
                )


def _drain_batch(conn, config, project, deferred):
    """Combine all deferred evals into a single evaluator call."""
    gate = check_rate_limit(conn, config.rate_limits)
    if gate.blocked:
        return

    # Delete all deferred decisions first
    for d in deferred:
        ops.delete_decision(conn, d.id)

    # Parse real commit info for each hash
    parsed_summaries = []
    for d in deferred:
        try:
            ci = parse_commit_info(d.commit_hash, project.repo_path)
            parsed_summaries.append(f"- {ci.message.splitlines()[0]}")
        except Exception:
            parsed_summaries.append(f"- {d.commit_hash[:8]}")

    commit = CommitInfo(
        hash=f"batch-{deferred[-1].commit_hash[:8]}",
        message=f"Batch of {len(deferred)} deferred triggers:\n" + "\n".join(parsed_summaries),
        diff="",
        files_changed=[],
    )

    try:
        _run_batch_evaluation(conn, config, project, commit, deferred)
    except Exception as e:
        logger.error("Batch drain failed for project %s: %s", project.id, e)
        # Re-insert all deferred decisions to avoid permanent loss
        for d in deferred:
            existing = conn.execute(
                "SELECT id FROM decisions WHERE project_id = ? AND commit_hash = ?",
                (project.id, d.commit_hash),
            ).fetchone()
            if not existing:
                ops.insert_decision(
                    conn,
                    Decision(
                        id=generate_id("decision"),
                        project_id=project.id,
                        commit_hash=d.commit_hash,
                        decision="deferred_eval",
                        reasoning=f"Batch drain failed: {e}",
                        trigger_source="commit",
                    ),
                )


def _run_batch_evaluation(conn, config, project, commit, deferred):
    """Run evaluator on a batch of deferred decisions. Follows consolidation.py pattern."""
    from social_hook.config.project import load_project_config
    from social_hook.errors import ConfigError
    from social_hook.llm.dry_run import DryRunContext
    from social_hook.llm.factory import create_client

    project_config = load_project_config(project.repo_path)

    db = DryRunContext(conn, dry_run=False)
    db.trigger_source = "drain"

    from social_hook.llm.prompts import assemble_evaluator_context

    context = assemble_evaluator_context(db, project.id, project_config)

    try:
        evaluator_client = create_client(config.models.evaluator, config)
    except ConfigError as e:
        logger.error("Config error creating evaluator client for drain batch: %s", e)
        return

    from social_hook.llm.evaluator import Evaluator

    try:
        evaluator = Evaluator(evaluator_client)

        platform_summaries = []
        for pname, pcfg in config.platforms.items():
            if pcfg.enabled:
                summary = f"{pname} ({pcfg.priority})"
                if pcfg.type == "custom" and pcfg.description:
                    summary += f" -- {pcfg.description}"
                platform_summaries.append(summary)

        evaluation = evaluator.evaluate(
            commit,
            context,
            db,
            platform_summaries=platform_summaries or None,
            media_config=config.media_generation,
            media_guidance=project_config.media_guidance if project_config else None,
            strategy_config=project_config.strategy if project_config else None,
            summary_config=project_config.summary if project_config else None,
            strategies=config.content_strategies or None,
        )
    except Exception as e:
        logger.error("LLM API error during drain batch evaluation: %s", e)
        return

    def _val(x):
        return x.value if hasattr(x, "value") else x

    # --- New targets path ---
    if getattr(config, "targets", None) and isinstance(config.targets, dict) and config.targets:
        from social_hook.trigger import _combine_strategy_reasoning, _determine_overall_decision

        decision_type = _determine_overall_decision(evaluation.strategies)
        if decision_type != "draft":
            logger.info("Drain batch re-evaluation for %s: %s", project.name, decision_type)
            return

        representative = next(
            (sd for sd in evaluation.strategies.values() if _val(sd.action) == "draft"),
            next(iter(evaluation.strategies.values())),
        )

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash=commit.hash,
            decision="draft",
            reasoning=_combine_strategy_reasoning(evaluation.strategies),
            angle=representative.angle,
            episode_type=None,
            post_category=_val(representative.post_category),
            media_tool=_val(representative.media_tool),
            targets={k: v.model_dump() for k, v in evaluation.strategies.items()},
            trigger_source="drain",
        )
        ops.insert_decision(conn, decision)
        ops.emit_data_event(conn, "decision", "created", decision.id, project.id)

        from social_hook.content_sources import content_sources
        from social_hook.drafting import draft_for_targets
        from social_hook.routing import route_to_targets

        target_actions = route_to_targets(evaluation.strategies, config, conn)
        draftable_actions = [a for a in target_actions if a.action == "draft"]

        if draftable_actions:
            draft_for_targets(
                draftable_actions,
                config,
                conn,
                db,
                project,
                decision_id=decision.id,
                evaluation=evaluation,
                context=context,
                commit=commit,
                content_source_registry=content_sources,
                project_config=project_config,
                dry_run=False,
            )
    else:
        # --- Legacy path ---
        target = evaluation.strategies.get("default")
        if not target:
            logger.info("Drain batch re-evaluation for %s: no default target", project.name)
            return

        if _val(target.action) != "draft":
            logger.info("Drain batch re-evaluation for %s: %s", project.name, _val(target.action))
            return

        decision = Decision(
            id=generate_id("decision"),
            project_id=project.id,
            commit_hash=commit.hash,
            decision="draft",
            reasoning=target.reason,
            angle=target.angle,
            episode_type=None,
            post_category=_val(target.post_category),
            media_tool=_val(target.media_tool),
            trigger_source="drain",
        )
        ops.insert_decision(conn, decision)
        ops.emit_data_event(conn, "decision", "created", decision.id, project.id)

        from social_hook.compat import make_eval_compat
        from social_hook.drafting import draft_for_platforms

        eval_compat = make_eval_compat(evaluation, "draft")
        draft_for_platforms(
            config,
            conn,
            db,
            project,
            decision_id=decision.id,
            evaluation=eval_compat,
            context=context,
            commit=commit,
            project_config=project_config,
            dry_run=False,
        )


def scheduler_tick(
    dry_run: bool = False,
    config_path: str | None = None,
    lock_path: Path | None = None,
    draft_id: str | None = None,
) -> int:
    """Run one scheduler tick: post all due drafts.

    Args:
        dry_run: If True, simulate posting
        config_path: Optional config file override
        lock_path: Optional lock file path override (for testing)
        draft_id: If set, post only this draft (post-now mode).
            Uses a per-draft lock, skips promote/drain, and fetches the
            draft directly instead of querying due drafts.

    Returns:
        Number of drafts processed (posted or failed)
    """
    # Per-draft lock when draft_id is provided
    if draft_id and lock_path is None:
        lock_path = get_base_path() / f"post_now_{draft_id}.lock"

    # Acquire lock
    if not acquire_lock(lock_path):
        logger.info("Scheduler tick skipped: lock held by another process")
        return 0

    effective_lock = lock_path or get_lock_path()

    try:
        # Load config
        config = load_full_config(yaml_path=config_path)

        # Init DB
        db_path = get_db_path()
        conn = init_database(db_path)

        # Wire error feed once per process
        ensure_error_feed(config, str(db_path))

        try:
            # --- Post-now mode: single draft, no promote/drain ---
            if draft_id:
                return _tick_single_draft(conn, config, draft_id, dry_run, db_path=db_path)

            # --- Normal mode ---
            # Promote deferred drafts before checking for due drafts
            promote_deferred_drafts(conn, config, dry_run=dry_run)

            # Drain deferred evaluations when rate limit slots are available
            _drain_deferred_evaluations(conn, config, dry_run)

            # Get due drafts
            due_drafts = ops.get_due_drafts(conn)
            if not due_drafts:
                return 0

            processed = 0

            for draft in due_drafts:
                try:
                    # Apply pending changes if any
                    changes = ops.get_draft_changes(conn, draft.id)
                    for change in changes:
                        if change.field == "content" and change.new_value:
                            draft.content = change.new_value

                    # Get project for this draft
                    project = ops.get_project(conn, draft.project_id)
                    if not project:
                        logger.error(f"Project not found for draft {draft.id}")
                        continue

                    if project.paused:
                        logger.info(f"Skipping draft {draft.id}: project {project.name} is paused")
                        continue

                    # Per-account gap check: skip if too soon after last post for this account
                    if not _check_per_account_gap(conn, config, draft):
                        continue

                    # Cross-account gap check: skip if too soon after last post on this platform
                    if not _check_cross_account_gap(conn, config, draft):
                        continue

                    if dry_run:
                        # Simulate success
                        from social_hook.adapters.dry_run import dry_run_post_result

                        result = dry_run_post_result()
                    else:
                        # Post via adapter
                        result = _post_draft(conn, draft, config, db_path=db_path)

                    if result.success:
                        record_post_success(
                            conn, draft, result, config, project.name, dry_run=dry_run
                        )
                    else:
                        _handle_post_failure(
                            conn, draft, result.error or "Unknown error", config, dry_run
                        )

                    processed += 1

                except Exception as e:
                    logger.error(f"Error processing draft {draft.id}: {e}")
                    _handle_post_failure(conn, draft, str(e), config, dry_run)
                    processed += 1

            return processed

        finally:
            conn.close()

    finally:
        release_lock(effective_lock)


def _tick_single_draft(conn, config, draft_id, dry_run, db_path=None) -> int:
    """Post a single draft by ID (post-now mode).

    Skips promote_deferred_drafts and _drain_deferred_evaluations.
    Only processes the specified draft if its status is 'scheduled'.

    Returns:
        Number of drafts processed (0 or 1).
    """
    draft = ops.get_draft(conn, draft_id)
    if not draft:
        logger.error(f"Post-now: draft {draft_id} not found")
        return 0

    if draft.status != "scheduled":
        logger.info(f"Post-now: draft {draft_id} status is {draft.status}, expected scheduled")
        return 0

    project = ops.get_project(conn, draft.project_id)
    if not project:
        logger.error(f"Post-now: project not found for draft {draft_id}")
        return 0

    if project.paused:
        logger.info(f"Post-now: skipping draft {draft_id}, project {project.name} is paused")
        return 0

    # Per-account gap check
    if not _check_per_account_gap(conn, config, draft):
        logger.info(f"Post-now: draft {draft_id} deferred by per-account gap")
        return 0

    # Cross-account gap check: post-now still checks because automated cross-posting can trigger it
    if not _check_cross_account_gap(conn, config, draft):
        logger.info(f"Post-now: draft {draft_id} deferred by cross-account gap")
        return 0

    try:
        if dry_run:
            from social_hook.adapters.dry_run import dry_run_post_result

            result = dry_run_post_result()
        else:
            result = _post_draft(conn, draft, config, db_path=db_path)

        if result.success:
            record_post_success(conn, draft, result, config, project.name, dry_run=dry_run)
        else:
            _handle_post_failure(conn, draft, result.error or "Unknown error", config, dry_run)

        return 1

    except Exception as e:
        logger.error(f"Post-now: error processing draft {draft_id}: {e}")
        _handle_post_failure(conn, draft, str(e), config, dry_run)
        return 1


def _post_draft(conn, draft, config, db_path=None):
    """Post a draft using the appropriate platform adapter.

    Args:
        conn: Database connection (for thread tweet lookup)
        draft: Draft object to post
        config: Full config object
        db_path: Path to SQLite database (for OAuth 2.0 token refresh)

    Returns:
        PostResult or ThreadResult
    """
    from social_hook.adapters.models import PostResult

    if draft.preview_mode:
        return PostResult(
            success=False,
            error="No account connected. Run 'social-hook account add' to connect and enable posting.",
        )

    # Get adapter: targets path (draft.target_id set) or legacy path
    db_path_str = str(db_path) if db_path else None
    try:
        target_id = draft.target_id
        if target_id is not None and target_id in config.targets:
            target = config.targets[target_id]
            account_name = target.account
            account = config.accounts.get(account_name)
            if not account:
                return PostResult(
                    success=False,
                    error=f"Account '{account_name}' not found for target '{target_id}'",
                )
            platform_creds = resolve_platform_creds(account, config.platform_credentials)

            def on_error(msg, _acct=account_name):
                error_feed.emit(
                    ErrorSeverity.ERROR,
                    msg,
                    context={"account_name": _acct},
                    source="auth",
                )

            adapter = _registry.get_for_account(
                account_name,
                account,
                platform_creds,
                config.env,
                db_path_str or "",
                on_error=on_error,
            )
        else:
            # Legacy path: no target_id or target_id not in config
            adapter = _registry.get(draft.platform, config, db_path=db_path_str)
    except ConfigError as e:
        error_feed.emit(
            ErrorSeverity.ERROR,
            f"Adapter creation failed for draft {draft.id}: {e}",
            context={"draft_id": draft.id, "platform": draft.platform},
            source="auth",
        )
        return PostResult(success=False, error=str(e))

    # Post format assignment: determine quote/reply for arc continuations
    decision = None
    if draft.decision_id:
        decision = ops.get_decision(conn, draft.decision_id)

    if decision and decision.arc_id and not draft.post_format:
        all_arc_posts = ops.get_arc_posts(conn, decision.arc_id)
        platform_posts = [p for p in all_arc_posts if p.platform == draft.platform]
        prior = platform_posts[0] if platform_posts else None
        if prior:
            if len(platform_posts) <= 1:
                draft.post_format = "quote"
            else:
                draft.post_format = "reply"
            draft.reference_post_id = prior.id
            ops.update_draft(
                conn,
                draft.id,
                post_format=draft.post_format,
                reference_post_id=draft.reference_post_id,
            )

    # Handle reference posting via abstract adapter interface
    if draft.reference_post_id and draft.post_format in ("quote", "reply"):
        ref_post = ops.get_post(conn, draft.reference_post_id)
        if ref_post and ref_post.external_id:
            from social_hook.adapters.models import PostReference, ReferenceType

            ref_type = ReferenceType.QUOTE if draft.post_format == "quote" else ReferenceType.REPLY
            if not adapter.supports_reference_type(ref_type):
                ref_type = ReferenceType.LINK
            reference = PostReference(
                external_id=ref_post.external_id,
                external_url=ref_post.external_url or "",
                reference_type=ref_type,
            )
            return adapter.post_with_reference(draft.content, reference, draft.media_paths or None)

    # X-specific: check if this is a thread (has draft_tweets)
    if draft.platform == "x":
        tweets = ops.get_draft_tweets(conn, draft.id)
        if tweets:
            tweet_dicts = []
            for i, t in enumerate(tweets):
                td = {"content": t.content, "media_paths": t.media_paths}
                # Attach draft-level media to first tweet if tweet has no own media
                if i == 0 and not t.media_paths and draft.media_paths:
                    td["media_paths"] = draft.media_paths
                tweet_dicts.append(td)
            thread_result = adapter.post_thread(tweet_dicts)

            # Update each draft_tweet with external_id and posted_at
            if thread_result.success:
                from datetime import datetime, timezone

                now_iso = datetime.now(timezone.utc).isoformat()
                for tweet, tweet_result in zip(tweets, thread_result.tweet_results, strict=False):
                    if tweet_result.success:
                        ops.update_draft_tweet(
                            conn,
                            tweet.id,
                            external_id=tweet_result.external_id,
                            posted_at=now_iso,
                        )
                    else:
                        ops.update_draft_tweet(
                            conn,
                            tweet.id,
                            error=tweet_result.error,
                        )

            # Return first tweet's result as the PostResult for compatibility
            first = thread_result.tweet_results[0] if thread_result.tweet_results else None
            return PostResult(
                success=thread_result.success,
                external_id=first.external_id if first else None,
                external_url=first.external_url if first else None,
                error=thread_result.error,
            )

    # Standard single-post (X, LinkedIn, or other)
    return adapter.post(draft.content, media_paths=draft.media_paths or None)


def _handle_post_failure(conn, draft, error_msg, config, dry_run):
    """Handle a failed post attempt with retry logic."""
    new_retry_count = draft.retry_count + 1

    if new_retry_count >= 3:
        # Max retries exceeded — emit to error feed
        error_feed.emit(
            ErrorSeverity.ERROR,
            f"Draft {draft.id} failed after {new_retry_count} attempts: {error_msg}",
            context={
                "draft_id": draft.id,
                "project_id": draft.project_id,
                "platform": draft.platform,
            },
            source="posting",
        )
        ops.update_draft(
            conn,
            draft.id,
            status="failed",
            retry_count=new_retry_count,
            last_error=error_msg,
        )
        ops.emit_data_event(conn, "draft", "updated", draft.id, draft.project_id)
        logger.error(f"Draft {draft.id} failed after {new_retry_count} attempts: {error_msg}")

        project = ops.get_project(conn, draft.project_id)
        project_name = project.name if project else "Unknown"
        send_notification(
            config,
            f"*Post failed*\n\n"
            f"Project: {project_name}\n"
            f"Platform: {draft.platform}\n"
            f"Error: {error_msg}\n"
            f"Attempts: {new_retry_count}/3\n\n"
            f"Draft {draft.id} marked as failed.",
            dry_run=dry_run,
        )
    else:
        # Schedule retry with backoff
        from datetime import datetime, timedelta, timezone

        error_feed.emit(
            ErrorSeverity.WARNING,
            f"Draft {draft.id} posting failed (attempt {new_retry_count}/3): {error_msg}",
            context={
                "draft_id": draft.id,
                "project_id": draft.project_id,
                "platform": draft.platform,
            },
            source="posting",
        )

        backoff_minutes = 5 * (2**new_retry_count)  # 10, 20 minutes
        retry_time = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)

        ops.update_draft(
            conn,
            draft.id,
            status="scheduled",
            scheduled_time=retry_time.strftime("%Y-%m-%d %H:%M:%S"),
            retry_count=new_retry_count,
            last_error=error_msg,
        )
        ops.emit_data_event(conn, "draft", "updated", draft.id, draft.project_id)
        logger.info(
            f"Draft {draft.id} retry {new_retry_count}/3 scheduled for "
            f"{retry_time.strftime('%H:%M UTC')} (backoff: {backoff_minutes}m)"
        )
