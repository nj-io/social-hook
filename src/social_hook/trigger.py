"""One-shot trigger: commit evaluation and draft creation pipeline."""

import logging
import subprocess
import sys

from social_hook.config.yaml import load_full_config
from social_hook.db import operations as ops
from social_hook.db.connection import init_database
from social_hook.error_feed import ErrorSeverity, error_feed
from social_hook.errors import ConfigError, DatabaseError
from social_hook.filesystem import generate_id, get_db_path
from social_hook.llm.dry_run import DryRunContext
from social_hook.llm.prompts import assemble_evaluator_context
from social_hook.models import CommitInfo, Decision, Draft, is_draftable
from social_hook.parsing import safe_int
from social_hook.rate_limits import check_rate_limit

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
                            insertions = safe_int(part.split()[0], 0, "git stat insertions")
                        elif "deletion" in part:
                            deletions = safe_int(part.split()[0], 0, "git stat deletions")

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
    trigger_source: str = "commit",
    existing_decision_id: str | None = None,
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
        existing_decision_id: If provided, reuse this ID instead of generating
            a new one. Used by retrigger to update in-place (upsert).

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
        error_feed.emit(
            ErrorSeverity.ERROR,
            f"Config error in trigger: {e}",
            context={"commit_hash": commit_hash, "repo_path": repo_path},
            source="config",
        )
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        return 1

    # 2. Initialize DB
    try:
        db_path = get_db_path()
        conn = init_database(db_path)
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        error_feed.emit(
            ErrorSeverity.ERROR,
            f"Database error in trigger: {e}",
            context={"commit_hash": commit_hash},
            source="database",
        )
        if verbose:
            print(f"Database error: {e}", file=sys.stderr)
        return 2

    # Wire error feed once per process (needs both config and db_path)
    from social_hook.scheduler import _ensure_error_feed

    _ensure_error_feed(config, str(db_path))

    db = DryRunContext(conn, dry_run=dry_run)
    db.trigger_source = trigger_source

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

    current_branch = _get_current_branch(repo_path)

    if project.trigger_branch and current_branch != project.trigger_branch:
        branch_desc = current_branch or "(detached HEAD)"
        if verbose:
            print(
                f"Branch '{branch_desc}' doesn't match trigger branch "
                f"'{project.trigger_branch}'. Skipping."
            )
        conn.close()
        return 0

    # 4. Rate limit gate (skip for manual triggers and drain)
    if trigger_source not in ("manual", "drain"):
        gate_result = check_rate_limit(conn, config.rate_limits)
        if gate_result.blocked:
            decision = Decision(
                id=existing_decision_id or generate_id("decision"),
                project_id=project.id,
                commit_hash=commit_hash,
                decision="deferred_eval",
                reasoning=gate_result.reason,
                commit_message=None,
                trigger_source=trigger_source,
                branch=current_branch,
            )
            if existing_decision_id:
                from social_hook.db import operations as _ops

                _ops.upsert_decision(conn, decision)
            else:
                db.insert_decision(decision)
            db.emit_data_event("decision", "created", decision.id, project.id)
            if verbose:
                print(f"Evaluation deferred: {gate_result.reason}")
            conn.close()
            return 0

    # 5. Load project config
    from social_hook.config.project import load_project_config

    project_config = load_project_config(repo_path)

    # 6. Parse commit (needed for timestamp-filtered context)
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
            summary, selected_files, file_summaries, prompt_docs = discover_project(
                client=discovery_client,
                repo_path=repo_path,
                project_docs=project_config.context.project_docs if project_config else [],
                max_discovery_tokens=project_config.context.max_discovery_tokens
                if project_config
                else 60000,
                max_file_size=project_config.context.max_file_size if project_config else 256000,
                db=db,
                project_id=project.id,
                on_progress=lambda stage: db.emit_data_event(
                    "pipeline", stage, commit_hash[:8], project.id
                ),
            )
            if summary:
                db.update_project_summary(project.id, summary)
                db.update_discovery_files(project.id, selected_files)
                if file_summaries:
                    db.upsert_file_summaries(project.id, file_summaries)
                if prompt_docs:
                    db.update_prompt_docs(project.id, prompt_docs)
                db.emit_data_event("project", "updated", project.id, project.id)
                context.project_summary = summary
                context.file_summaries = file_summaries if file_summaries else []
                if verbose:
                    print(f"Project discovery complete: {len(selected_files)} files analyzed")
        except Exception as e:
            logger.warning(f"Project discovery failed (non-fatal): {e}")
            if verbose:
                print(f"Project discovery skipped: {e}", file=sys.stderr)
    elif project_config and project_config.summary:
        try:
            freshness = db.get_summary_freshness(project.id)
            cfg = project_config.summary
            needs_refresh = freshness["commits_since_summary"] >= cfg.refresh_after_commits or (
                freshness["days_since_summary"] is not None
                and freshness["days_since_summary"] >= cfg.refresh_after_days
            )
        except Exception:
            logger.warning("Summary freshness check failed, skipping refresh", exc_info=True)
            needs_refresh = False
        if needs_refresh:
            try:
                from social_hook.llm.discovery import discover_project
                from social_hook.llm.factory import create_client as _create_client

                discovery_client = _create_client(config.models.evaluator, config, verbose=verbose)
                summary, selected_files, file_summaries, prompt_docs = discover_project(
                    client=discovery_client,
                    repo_path=repo_path,
                    project_docs=project_config.context.project_docs if project_config else [],
                    max_discovery_tokens=project_config.context.max_discovery_tokens
                    if project_config
                    else 60000,
                    max_file_size=project_config.context.max_file_size
                    if project_config
                    else 256000,
                    db=db,
                    project_id=project.id,
                    on_progress=lambda stage: db.emit_data_event(
                        "pipeline", stage, commit_hash[:8], project.id
                    ),
                )
                if summary:
                    db.update_project_summary(project.id, summary)
                    db.update_discovery_files(project.id, selected_files)
                    if file_summaries:
                        db.upsert_file_summaries(project.id, file_summaries)
                    if prompt_docs:
                        db.update_prompt_docs(project.id, prompt_docs)
                    db.emit_data_event("project", "updated", project.id, project.id)
                    context.project_summary = summary
                    context.file_summaries = file_summaries if file_summaries else []
                    if verbose:
                        print(f"Project summary refreshed: {len(selected_files)} files analyzed")
            except Exception as e:
                logger.warning(f"Project summary refresh failed (non-fatal): {e}")
                if verbose:
                    print(f"Summary refresh skipped: {e}", file=sys.stderr)

    if verbose and context.project_summary:
        print(f"Using project summary ({len(context.project_summary)} chars)")

    if verbose:
        print(f"Evaluating commit {commit.hash[:8]}: {commit.message}")

    db.emit_data_event("pipeline", "evaluating", commit_hash[:8], project.id)

    # 7. Evaluate
    from social_hook.llm.evaluator import Evaluator
    from social_hook.llm.factory import create_client

    try:
        evaluator_client = create_client(config.models.evaluator, config, verbose=verbose)
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        error_feed.emit(
            ErrorSeverity.ERROR,
            f"Evaluator client config error: {e}",
            context={"commit_hash": commit_hash, "project_id": project.id},
            source="config",
        )
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

    # Gather scheduling state for evaluator awareness
    from social_hook.scheduling import get_scheduling_state

    try:
        scheduling_state = get_scheduling_state(conn, project.id, config)
    except Exception as e:
        logger.warning(f"Failed to get scheduling state (non-fatal): {e}")
        scheduling_state = None

    # Fetch topics and arcs for evaluator context
    all_topics = ops.get_topics_by_project(conn, project.id)
    held_topics = [t for t in all_topics if t.status == "holding"]
    active_arcs_all = ops.get_arcs_by_project(conn, project.id, status="active")

    # Stage 1: Commit Analyzer (targets path only, with interval gating)
    analyzer_result = None
    has_targets = (
        getattr(config, "targets", None) and isinstance(config.targets, dict) and config.targets
    )
    if has_targets:
        analyzer_result = _run_commit_analyzer(
            conn=conn,
            db=db,
            project=project,
            commit=commit,
            context=context,
            evaluator_client=evaluator_client,
            project_config=project_config,
            show_prompt=show_prompt,
            dry_run=dry_run,
            verbose=verbose,
        )

        # Stage 1 trivial skip: if analyzer classified as trivial, skip stage 2
        if analyzer_result is not None and _is_trivial_classification(analyzer_result):
            logger.info("Trivial commit %s, skipping strategy evaluation", commit_hash[:8])
            result = _run_trivial_skip(
                analyzer_result=analyzer_result,
                config=config,
                conn=conn,
                db=db,
                project=project,
                commit=commit,
                commit_hash=commit_hash,
                context=context,
                evaluator_client=evaluator_client,
                current_branch=current_branch,
                dry_run=dry_run,
                verbose=verbose,
                existing_decision_id=existing_decision_id,
            )
            conn.close()
            return result

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
            scheduling_state=scheduling_state,
            strategies=config.content_strategies or None,
            held_topics=held_topics or None,
            active_arcs_all=active_arcs_all or None,
            targets=config.targets or None,
            all_topics=all_topics or None,
            analysis=analyzer_result,
        )
    except Exception as e:
        logger.error(f"LLM API error during evaluation: {e}")
        if verbose:
            print(f"LLM API error: {e}", file=sys.stderr)
        conn.close()
        return 3

    # 8. Map evaluation output to Decision
    analysis = evaluation.commit_analysis

    # --- New targets path: when config.targets has real target entries ---
    if has_targets:
        result = _run_targets_path(
            evaluation=evaluation,
            analysis=analysis,
            config=config,
            conn=conn,
            db=db,
            project=project,
            commit=commit,
            commit_hash=commit_hash,
            context=context,
            project_config=project_config,
            current_branch=current_branch,
            evaluator_client=evaluator_client,
            dry_run=dry_run,
            verbose=verbose,
            existing_decision_id=existing_decision_id,
            analyzer_result=analyzer_result,
        )
        conn.close()
        return result

    # --- Legacy path: single "default" target ---
    logger.warning("No targets configured. Using legacy platform-based drafting.")
    target = evaluation.strategies.get("default")
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
        id=existing_decision_id or generate_id("decision"),
        project_id=project.id,
        commit_hash=commit_hash,
        decision=decision_type,
        reasoning=target.reason,
        commit_message=commit.message,
        angle=target.angle,
        episode_type=None,
        episode_tags=analysis.episode_tags,
        post_category=_val(target.post_category),
        arc_id=target.arc_id,
        media_tool=_val(target.media_tool),
        targets={"default": target.model_dump()},
        commit_summary=analysis.summary,
        consolidate_with=target.consolidate_with,
        reference_posts=target.reference_posts,
        branch=current_branch,
    )

    # Hold count enforcement
    if decision_type == "hold":
        max_hold = project_config.context.max_hold_count if project_config else 5
        current_held = ops.get_held_decisions(conn, project.id)
        if len(current_held) >= max_hold:
            logger.warning(f"Hold limit reached ({max_hold}), forcing skip for {commit_hash[:8]}")
            decision.decision = "skip"
            decision_type = "skip"

    if existing_decision_id:
        ops.upsert_decision(conn, decision)
    else:
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

    # 8d. Queue actions (supersede/drop + merge groups) — runs on ANY decision type
    if evaluation.queue_actions:
        for _target_name, actions in evaluation.queue_actions.items():
            for qa in actions:
                action_type = qa.action
                if action_type == "merge":
                    continue  # handled by _execute_merge_groups below
                if not dry_run:
                    draft_ref = ops.get_draft(conn, qa.draft_id)
                    # Intentionally excludes deferred — queue actions target active drafts only
                    if not draft_ref or draft_ref.status not in ("draft", "approved", "scheduled"):
                        if verbose:
                            print(f"Queue action skipped: draft {qa.draft_id} not actionable")
                        continue
                    ops.execute_queue_action(conn, action_type, qa.draft_id, qa.reason)
                if verbose:
                    print(f"Queue action: {action_type} draft {qa.draft_id}")

        # Execute merge groups (creates replacement drafts via drafter)
        if not dry_run:
            _execute_merge_groups(
                evaluation.queue_actions,
                config,
                conn,
                db,
                project,
                context,
                project_config,
                dry_run,
                verbose,
            )

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

        db.emit_data_event("pipeline", "drafting", commit_hash[:8], project.id)
        eval_compat = make_eval_compat(evaluation, decision.decision)

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
                from social_hook.notifications import notify_draft_review

                notify_draft_review(
                    config,
                    project_name=project.name,
                    project_id=project.id,
                    commit_hash=commit.hash,
                    commit_message=commit.message,
                    draft_results=draft_results,
                )
            elif config.notification_level != "drafts_only":
                _send_decision_notification(config, project, commit, decision)

    conn.close()
    return 0


def _determine_overall_decision(
    strategies: dict,
) -> str:
    """Derive a single DecisionType from per-strategy decisions.

    Rules:
    - Empty strategies dict -> log warning, return "skip".
    - If any strategy has action "draft" -> "draft"
    - If all strategies have action "hold" -> "hold"
    - If all strategies have action "skip" -> "skip"
    - Mixed hold+skip (no draft) -> "skip"
    """
    if not strategies:
        logger.warning("Empty strategies dict in _determine_overall_decision")
        return "skip"

    actions = set()
    for decision in strategies.values():
        action = decision.action
        if hasattr(action, "value"):
            action = action.value
        actions.add(action)

    if "draft" in actions:
        return "draft"
    if actions == {"hold"}:
        return "hold"
    return "skip"


def _combine_strategy_reasoning(
    strategies: dict,
) -> str:
    """Combine per-strategy reasoning into a single string for the Decision record.

    Format: "strategy-name: reason; strategy-name: reason"
    Truncate to 500 chars if needed.
    """
    parts = []
    for name, decision in strategies.items():
        parts.append(f"{name}: {decision.reason}")
    combined = "; ".join(parts)
    if len(combined) > 500:
        combined = combined[:497] + "..."
    return combined


def _is_trivial_classification(analyzer_result) -> bool:
    """Check if the analyzer classified the commit as trivial."""
    if analyzer_result is None:
        return False
    ca = analyzer_result.commit_analysis
    if ca and ca.classification:
        return (
            ca.classification.value == "trivial"
            if hasattr(ca.classification, "value")
            else ca.classification == "trivial"
        )
    else:
        logger.warning("Analyzer result has no classification, treating as non-trivial")
        return False


def _run_trivial_skip(
    analyzer_result,
    config,
    conn,
    db,
    project,
    commit,
    commit_hash: str,
    context,
    evaluator_client,
    current_branch: str | None,
    dry_run: bool,
    verbose: bool,
    existing_decision_id: str | None = None,
) -> int:
    """Handle trivial commits: create cycle, do tag matching, skip stage 2."""
    import json

    from social_hook.models import EvaluationCycle

    analysis = analyzer_result.commit_analysis

    # Create evaluation cycle record
    cycle = EvaluationCycle(
        id=generate_id("cycle"),
        project_id=project.id,
        trigger_type="commit",
        trigger_ref=commit_hash,
    )
    db.insert_evaluation_cycle(cycle)

    # Store analysis JSON on the cycle for caching
    try:
        analysis_json = json.dumps(analyzer_result.model_dump(), default=str)
        ops.update_cycle_analysis_json(conn, cycle.id, analysis_json)
    except Exception as e:
        logger.warning(f"Failed to cache analysis JSON (non-fatal): {e}")

    # Tag-to-topic matching (even trivial commits may match topics)
    for tag in analysis.episode_tags:
        matching_topics = ops.get_topics_matching_tag(conn, project.id, tag)
        for topic in matching_topics:
            ops.increment_topic_commit_count(conn, topic.id)
            ops.insert_topic_commit(conn, topic.id, commit_hash, matched_tag=tag)

    # Create skip decision
    decision = Decision(
        id=existing_decision_id or generate_id("decision"),
        project_id=project.id,
        commit_hash=commit_hash,
        decision="skip",
        reasoning="Trivial commit — skipped strategy evaluation",
        commit_message=commit.message,
        episode_tags=analysis.episode_tags,
        commit_summary=analysis.summary,
        branch=current_branch,
    )

    if existing_decision_id:
        ops.upsert_decision(conn, decision)
    else:
        db.insert_decision(decision)
    db.emit_data_event("decision", "created", decision.id, project.id)

    if verbose:
        print("Decision: skip (trivial commit)")
        print(f"Summary: {analysis.summary}")

    return 0


def _run_commit_analyzer(
    conn,
    db,
    project,
    commit,
    context,
    evaluator_client,
    project_config,
    show_prompt: bool,
    dry_run: bool,
    verbose: bool,
):
    """Run stage 1 commit analyzer with interval gating.

    Returns CommitAnalysisResult if analysis was run or cached, None on error.
    """
    import json

    from social_hook.llm.schemas import CommitAnalysisResult

    # 1. Increment commit count
    new_count = ops.increment_analysis_commit_count(conn, project.id)

    # 2. Check interval threshold
    interval = 1
    if project_config and hasattr(project_config, "context") and project_config.context:
        interval = getattr(project_config.context, "commit_analysis_interval", 1)
    if interval < 1:
        interval = 1

    if new_count < interval:
        # Interval not met — use cached analysis from most recent cycle
        cached_cycle = ops.get_latest_cycle_with_analysis(conn, project.id)
        if cached_cycle and cached_cycle.commit_analysis_json:
            try:
                cached_data = json.loads(cached_cycle.commit_analysis_json)
                result = CommitAnalysisResult.model_validate(cached_data)
                if verbose:
                    print(f"Using cached analysis (count {new_count}/{interval})")
                return result
            except Exception as e:
                logger.warning(f"Failed to load cached analysis, running fresh: {e}")
                # Fall through to run fresh analysis
        else:
            # No cache (first commit case) — run fresh analysis
            if verbose:
                print(f"No cached analysis available, running fresh (count {new_count}/{interval})")

    # 3. Run fresh analysis
    try:
        from social_hook.llm.analyzer import CommitAnalyzer

        analyzer = CommitAnalyzer(evaluator_client)
        result = analyzer.analyze(
            commit=commit,
            context=context,
            db=db,
            show_prompt=show_prompt,
        )

        # Reset counter after successful analysis
        ops.reset_analysis_commit_count(conn, project.id)

        if verbose:
            print(
                f"Commit analysis complete (classification: "
                f"{result.commit_analysis.classification.value if result.commit_analysis.classification else 'unknown'})"
            )

        return result
    except Exception as e:
        logger.warning(f"Commit analyzer failed (non-fatal, evaluator will proceed): {e}")
        if verbose:
            print(f"Commit analyzer skipped: {e}", file=sys.stderr)
        return None


def _run_targets_path(
    evaluation,
    analysis,
    config,
    conn,
    db,
    project,
    commit,
    commit_hash: str,
    context,
    project_config,
    current_branch: str | None,
    evaluator_client,
    dry_run: bool,
    verbose: bool,
    existing_decision_id: str | None = None,
    analyzer_result=None,
) -> int:
    """New targets pipeline path: multi-strategy -> multi-target routing."""
    from social_hook.models import EvaluationCycle

    def _val(x):
        return x.value if hasattr(x, "value") else x

    # Create evaluation cycle record
    cycle = EvaluationCycle(
        id=generate_id("cycle"),
        project_id=project.id,
        trigger_type="commit",
        trigger_ref=commit_hash,
    )
    db.insert_evaluation_cycle(cycle)

    # If stage 1 analyzer produced a result, use it for enrichment
    if analyzer_result is not None:
        import json

        # Store analysis JSON on the cycle for caching
        try:
            analysis_json = json.dumps(analyzer_result.model_dump(), default=str)
            ops.update_cycle_analysis_json(conn, cycle.id, analysis_json)
        except Exception as e:
            logger.warning(f"Failed to cache analysis JSON (non-fatal): {e}")

        # Enrich the evaluator's analysis with stage 1 classification
        if analyzer_result.commit_analysis.classification:
            analysis.classification = analyzer_result.commit_analysis.classification

        # Use stage 1 tags if evaluator produced none
        if not analysis.episode_tags and analyzer_result.commit_analysis.episode_tags:
            analysis.episode_tags = analyzer_result.commit_analysis.episode_tags

        if verbose:
            classification = (
                analyzer_result.commit_analysis.classification.value
                if analyzer_result.commit_analysis.classification
                else "unknown"
            )
            print(f"Stage 1 classification: {classification}")

    # Brief update: if commit is non-trivial, update the brief
    _trigger_brief_update(
        evaluation=evaluation,
        analysis=analysis,
        conn=conn,
        db=db,
        project=project,
        evaluator_client=evaluator_client,
        dry_run=dry_run,
        verbose=verbose,
    )

    # Tag-to-topic matching: increment commit counts and record junction
    for tag in analysis.episode_tags:
        matching_topics = ops.get_topics_matching_tag(conn, project.id, tag)
        for topic in matching_topics:
            ops.increment_topic_commit_count(conn, topic.id)
            ops.insert_topic_commit(conn, topic.id, commit_hash, matched_tag=tag)

    # Update content topic statuses for held topics
    for _strategy_name, strat_decision in evaluation.strategies.items():
        action = _val(strat_decision.action)
        if action == "hold" and strat_decision.topic_id:
            ops.update_topic_status(conn, strat_decision.topic_id, "holding")

    # Derive overall decision from per-strategy decisions
    decision_type = _determine_overall_decision(evaluation.strategies)

    # Get the first "draft" strategy for arc/angle/category or fall back to first strategy
    first_draft_strategy = None
    for _sn, sd in evaluation.strategies.items():
        if _val(sd.action) == "draft":
            first_draft_strategy = sd
            break
    representative = first_draft_strategy or next(iter(evaluation.strategies.values()))

    decision = Decision(
        id=existing_decision_id or generate_id("decision"),
        project_id=project.id,
        commit_hash=commit_hash,
        decision=decision_type,
        reasoning=_combine_strategy_reasoning(evaluation.strategies),
        commit_message=commit.message,
        angle=representative.angle,
        episode_type=None,
        episode_tags=analysis.episode_tags,
        post_category=_val(representative.post_category),
        arc_id=representative.arc_id,
        media_tool=_val(representative.media_tool),
        targets={k: v.model_dump() for k, v in evaluation.strategies.items()},
        commit_summary=analysis.summary,
        consolidate_with=representative.consolidate_with,
        reference_posts=representative.reference_posts,
        branch=current_branch,
    )

    # Hold count enforcement
    if decision_type == "hold":
        max_hold = project_config.context.max_hold_count if project_config else 5
        current_held = ops.get_held_decisions(conn, project.id)
        if len(current_held) >= max_hold:
            logger.warning(f"Hold limit reached ({max_hold}), forcing skip for {commit_hash[:8]}")
            decision.decision = "skip"
            decision_type = "skip"

    if existing_decision_id:
        ops.upsert_decision(conn, decision)
    else:
        db.insert_decision(decision)
    db.emit_data_event("decision", "created", decision.id, project.id)

    # Arc activation for draftable strategies
    if is_draftable(decision.decision):
        for _sn, sd in evaluation.strategies.items():
            if _val(sd.action) != "draft":
                continue
            if sd.new_arc_theme and not sd.arc_id:
                try:
                    from social_hook.narrative.arcs import create_arc as _create_arc

                    new_arc_id = _create_arc(db.conn, project.id, sd.new_arc_theme)
                    db.update_decision(decision.id, arc_id=new_arc_id)
                    decision.arc_id = new_arc_id
                    if verbose:
                        print(f"Created new arc: {new_arc_id} ({sd.new_arc_theme})")
                except Exception as e:
                    logger.warning(f"Arc creation failed (non-fatal): {e}")
                break  # Only one arc per decision

    # Held decision absorption
    if is_draftable(decision.decision) and representative.consolidate_with:
        valid_ids = [d.id for d in context.held_decisions]
        absorbed = [cid for cid in representative.consolidate_with if cid in valid_ids]
        if absorbed and not dry_run:
            batch_id = generate_id("batch")
            ops.mark_decisions_processed(conn, absorbed, batch_id)

    # Queue actions (same as legacy path)
    executed_queue_actions: list[dict[str, str]] = []
    if evaluation.queue_actions:
        for _target_name, actions in evaluation.queue_actions.items():
            for qa in actions:
                action_type = qa.action
                if action_type == "merge":
                    continue
                if not dry_run:
                    draft_ref = ops.get_draft(conn, qa.draft_id)
                    if not draft_ref or draft_ref.status not in ("draft", "approved", "scheduled"):
                        if verbose:
                            print(f"Queue action skipped: draft {qa.draft_id} not actionable")
                        continue
                    ops.execute_queue_action(conn, action_type, qa.draft_id, qa.reason)
                    executed_queue_actions.append(
                        {
                            "type": action_type,
                            "draft_id": qa.draft_id,
                            "reason": qa.reason or "",
                        }
                    )
                if verbose:
                    print(f"Queue action: {action_type} draft {qa.draft_id}")

        if not dry_run:
            _execute_merge_groups(
                evaluation.queue_actions,
                config,
                conn,
                db,
                project,
                context,
                project_config,
                dry_run,
                verbose,
            )

    # Send decision notification for non-draftable decisions
    if (
        not dry_run
        and config.notification_level == "all_decisions"
        and not is_draftable(decision.decision)
    ):
        _send_decision_notification(config, project, commit, decision)

    if verbose:
        print(f"Decision: {decision_type}")
        print(f"Reasoning: {decision.reasoning}")

    # Route per-strategy decisions to per-target actions and draft
    if is_draftable(decision.decision):
        from social_hook.content_sources import content_sources
        from social_hook.drafting import draft_for_targets
        from social_hook.routing import route_to_targets

        db.emit_data_event("pipeline", "drafting", commit_hash[:8], project.id)

        target_actions = route_to_targets(evaluation.strategies, config, conn)
        draftable_actions = [a for a in target_actions if a.action == "draft"]

        if draftable_actions:
            draft_results = draft_for_targets(
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
                dry_run=dry_run,
                verbose=verbose,
            )

            # Increment arc post count if drafts were created for an arc
            if draft_results and decision.arc_id:
                try:
                    from social_hook.narrative.arcs import increment_arc_post_count

                    increment_arc_post_count(db.conn, decision.arc_id)
                    if verbose:
                        print(f"Incremented post count for arc: {decision.arc_id}")
                except Exception as e:
                    logger.warning(f"Arc post count increment failed (non-fatal): {e}")

            # Update topic status for strategies that drafted with a topic_id
            if draft_results and not dry_run:
                for _sn, sd in evaluation.strategies.items():
                    if _val(sd.action) == "draft" and sd.topic_id:
                        new_status = "partial" if sd.arc_id else "covered"
                        ops.update_topic_status(conn, sd.topic_id, new_status)
                        if verbose:
                            print(f"Topic {sd.topic_id} status -> {new_status}")

            draft_results_for_notification = draft_results
        else:
            draft_results_for_notification = None

        # Cycle notification (both draftable and non-draftable paths)
        cycle_drafts = (
            [r.draft for r in draft_results_for_notification]
            if draft_results_for_notification
            else []
        )
        should_notify = not dry_run and (cycle_drafts or config.notification_level != "drafts_only")
        if should_notify:
            from social_hook.notifications import notify_evaluation_cycle

            strategy_outcomes = {
                sn: {
                    "action": _val(sd.action),
                    "reason": sd.reason,
                    "arc_id": sd.arc_id,
                    "topic_id": sd.topic_id,
                }
                for sn, sd in evaluation.strategies.items()
            }
            notify_evaluation_cycle(
                config,
                project_name=project.name,
                project_id=project.id,
                cycle_id=cycle.id,
                trigger_description=f"Commit {commit.hash[:8]} — {commit.message}",
                strategy_outcomes=strategy_outcomes,
                drafts=cycle_drafts,
                queue_actions=executed_queue_actions or None,
                dry_run=dry_run,
            )

    return 0


def _trigger_brief_update(
    evaluation,
    analysis,
    conn,
    db,
    project,
    evaluator_client,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Update the project brief after commit analysis if the commit is non-trivial."""
    # Only update for non-trivial commits (has episode tags beyond trivial markers)
    if not analysis.episode_tags:
        return

    try:
        from social_hook.llm.brief import update_brief_from_commit

        current_brief = ops.get_project_summary(conn, project.id)
        if not current_brief:
            return

        # Get section metadata from the project
        proj = ops.get_project(conn, project.id)
        section_metadata = proj.brief_section_metadata if proj else None

        updated_brief, updated_metadata, changed_keys = update_brief_from_commit(
            current_brief=current_brief,
            commit_analysis_summary=analysis.summary,
            commit_analysis_tags=analysis.episode_tags,
            client=evaluator_client,
            section_metadata=section_metadata,
            db=db,
            project_id=project.id,
        )
        if updated_brief != current_brief and not dry_run:
            db.update_project_summary(project.id, updated_brief)
            if verbose:
                print(f"Brief updated: sections changed: {changed_keys}")
    except ImportError:
        logger.debug("brief.py not available, skipping brief update")
    except Exception as e:
        logger.warning(f"Brief update failed (non-fatal): {e}")
        if verbose:
            print(f"Brief update skipped: {e}", file=sys.stderr)


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


def _build_merge_evaluation(
    drafts: list[Draft],
    decisions: list[Decision],
    merge_instruction: str | None,
):
    """Build a synthetic evaluation for a merge group.

    Returns a SimpleNamespace matching the shape produced by make_eval_compat()
    in compat.py — the same interface the drafter pipeline expects.
    """
    from types import SimpleNamespace

    latest = decisions[-1]

    if merge_instruction:
        angle = merge_instruction
    else:
        combined = " + ".join(d.angle for d in decisions if d.angle)
        angle = combined or "Consolidate these drafts"

    combined_summary = "\n".join(
        f"- {d.commit_summary or d.commit_message or d.commit_hash[:8]}" for d in decisions
    )

    return SimpleNamespace(
        decision="draft",
        reasoning=f"Merged from {len(drafts)} drafts",
        angle=angle,
        episode_type=None,
        post_category=latest.post_category,
        arc_id=latest.arc_id,
        new_arc_theme=None,
        media_tool=latest.media_tool,
        reference_posts=None,
        commit_summary=combined_summary,
        include_project_docs=None,
    )


def _build_merge_commit(
    decisions: list[Decision],
    drafts: list[Draft],
) -> CommitInfo:
    """Build a synthetic CommitInfo for a merge group.

    Injects original draft contents into the diff field so the drafter
    sees them in the "### Diff" section of the system prompt.
    """
    summaries = "\n".join(
        f"- {d.commit_summary or d.commit_message or d.commit_hash[:8]}" for d in decisions
    )
    diff_section = "Original drafts to consolidate:\n" + "\n---\n".join(
        f"Draft {i + 1}:\n{d.content}" for i, d in enumerate(drafts)
    )
    return CommitInfo(
        hash=f"merge-{decisions[-1].commit_hash[:8]}",
        message=f"Merge of {len(drafts)} drafts:\n{summaries}",
        diff=diff_section,
        files_changed=[],
    )


def _execute_merge_groups(
    queue_actions: dict[str, list],
    config,
    conn,
    db,
    project,
    context,
    project_config,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Execute merge queue actions grouped by merge_group.

    For each merge group: load drafts, sub-group by platform, call drafter
    to create a replacement draft, supersede originals.
    """
    from collections import defaultdict

    from social_hook.drafting import draft_for_platforms

    for _target_name, actions in queue_actions.items():
        merge_actions = [a for a in actions if a.action == "merge"]
        if not merge_actions:
            continue

        # Group by merge_group label
        groups: dict[str, list] = defaultdict(list)
        for ma in merge_actions:
            group_key = ma.merge_group or "default"
            groups[group_key].append(ma)

        for group_key, group_actions in groups.items():
            # Extract merge_instruction (first non-null in the group)
            merge_instruction = next(
                (a.merge_instruction for a in group_actions if a.merge_instruction),
                None,
            )

            # Load and validate drafts + their parent decisions
            valid_drafts: list[Draft] = []
            valid_decisions: list[Decision] = []
            for ga in group_actions:
                draft = ops.get_draft(conn, ga.draft_id)
                # Intentionally excludes deferred — queue actions target active drafts only
                if (
                    not draft
                    or draft.status not in ("draft", "approved", "scheduled")
                    or draft.project_id != project.id
                ):
                    if verbose:
                        print(f"Merge skipped: draft {ga.draft_id} not actionable")
                    continue
                valid_drafts.append(draft)
                if draft.decision_id:
                    dec = ops.get_decision(conn, draft.decision_id)
                    if dec:
                        valid_decisions.append(dec)

            if len(valid_drafts) < 2 or not valid_decisions:
                if verbose:
                    print(
                        f"Merge group {group_key}: {len(valid_drafts)} valid draft(s), "
                        f"{len(valid_decisions)} decision(s) — skipping"
                    )
                continue

            # Sub-group by platform
            by_platform: dict[str, list[Draft]] = defaultdict(list)
            for d in valid_drafts:
                by_platform[d.platform].append(d)

            for platform, platform_drafts in by_platform.items():
                if len(platform_drafts) < 2:
                    if verbose:
                        logger.info(
                            "Merge group %s: only 1 draft on %s, skipping",
                            group_key,
                            platform,
                        )
                    continue

                pcfg = config.platforms.get(platform)
                if not pcfg or not pcfg.enabled:
                    continue

                try:
                    # Collect decisions for this platform's drafts
                    platform_decision_ids = {d.decision_id for d in platform_drafts}
                    platform_decisions = [
                        dec for dec in valid_decisions if dec.id in platform_decision_ids
                    ] or valid_decisions[-1:]  # fallback to latest

                    merged_eval = _build_merge_evaluation(
                        platform_drafts, platform_decisions, merge_instruction
                    )
                    merged_commit = _build_merge_commit(platform_decisions, platform_drafts)

                    draft_results = draft_for_platforms(
                        config,
                        conn,
                        db,
                        project,
                        decision_id=platform_decisions[-1].id,
                        evaluation=merged_eval,
                        context=context,
                        commit=merged_commit,
                        project_config=project_config,
                        target_platform_names=[platform],
                        dry_run=dry_run,
                        verbose=verbose,
                    )

                    if draft_results and not dry_run:
                        replacement_id = draft_results[0].draft.id
                        for d in platform_drafts:
                            ops.supersede_draft(conn, d.id, replacement_id)
                            db.emit_data_event("draft", "updated", d.id, project.id)

                    if verbose and draft_results:
                        print(
                            f"Merged {len(platform_drafts)} {platform} drafts "
                            f"→ {len(draft_results)} replacement(s)"
                        )

                except Exception as e:
                    logger.error("Merge group %s/%s failed: %s", group_key, platform, e)
                    if verbose:
                        print(f"Merge group {group_key}/{platform} failed: {e}")


def run_summary_trigger(
    config,
    conn,
    db,
    project,
    summary: str,
    repo_path: str,
    verbose: bool = False,
) -> dict | None:
    """Generate an introductory first draft from project summary.

    Creates a Decision with trigger_source="manual" and decision="draft",
    then calls the drafter directly. No evaluator call needed.

    Returns draft info dict or None on failure.
    """
    from social_hook.compat import make_eval_compat
    from social_hook.config.project import load_project_config
    from social_hook.drafting import draft_for_platforms

    project_config = load_project_config(repo_path)

    # Create a manual decision (no commit)
    decision = Decision(
        id=generate_id("decision"),
        project_id=project.id,
        commit_hash="summary",
        decision="draft",
        reasoning="Summary-based introductory draft",
        commit_message="Project introduction",
        angle="Introduce the project and what it does",
        trigger_source="manual",
    )
    db.insert_decision(decision)
    db.emit_data_event("decision", "created", decision.id, project.id)

    # Assemble context (no commit timestamps)
    context = assemble_evaluator_context(db, project.id, project_config)

    # Build a minimal evaluation-compatible object for the drafter
    from social_hook.llm.schemas import (
        CommitAnalysis,
        LogEvaluationInput,
        PostCategorySchema,
        StrategyDecisionInput,
        TargetAction,
    )

    evaluation = LogEvaluationInput(
        commit_analysis=CommitAnalysis(
            summary=summary[:500],
            episode_tags=["introduction"],
        ),
        strategies={
            "default": StrategyDecisionInput(
                action=TargetAction.draft,
                reason="Summary-based introduction",
                angle="Introduce the project and what it does",
                post_category=PostCategorySchema.opportunistic,
            ),
        },
    )
    eval_compat = make_eval_compat(evaluation, "draft")

    # Draft
    db.emit_data_event("pipeline", "drafting", "summary", project.id)

    commit = CommitInfo(
        hash="summary",
        message="Project introduction",
        diff=summary[:1000],
        files_changed=[],
    )

    try:
        draft_results = draft_for_platforms(
            config=config,
            conn=conn,
            db=db,
            project=project,
            decision_id=decision.id,
            evaluation=eval_compat,
            context=context,
            commit=commit,
            project_config=project_config,
            verbose=verbose,
        )
    except Exception as e:
        logger.error("Summary draft failed: %s", e)
        if verbose:
            print(f"Summary draft failed: {e}", file=sys.stderr)
        return None

    if not draft_results:
        return None

    # Return first draft info
    first = draft_results[0]
    return {
        "decision_id": decision.id,
        "draft_id": first.draft.id,
        "platform": first.draft.platform,
        "content": first.draft.content,
    }


def run_suggestion_trigger(
    suggestion_id: str,
    project_id: str,
    config_path: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Trigger evaluation from an operator content suggestion.

    Similar to run_trigger() but:
    - No commit analysis stage (no commit)
    - Trigger content is the suggestion idea
    - trigger_type = 'operator_suggestion'

    Returns:
        Exit code: 0 = success, 1 = error
    """
    # 1. Load config
    try:
        config = load_full_config(
            yaml_path=config_path if config_path else None,
        )
    except ConfigError as e:
        logger.error("Config error: %s", e)
        if verbose:
            print(f"Config error: {e}", file=sys.stderr)
        return 1

    # 2. Initialize DB
    try:
        db_path = get_db_path()
        conn = init_database(db_path)
    except DatabaseError as e:
        logger.error("Database error: %s", e)
        if verbose:
            print(f"Database error: {e}", file=sys.stderr)
        return 1

    # 3. Validate project exists
    project = ops.get_project(conn, project_id)
    if project is None:
        logger.error("Project '%s' not found", project_id)
        if verbose:
            print(f"Project '{project_id}' not found", file=sys.stderr)
        conn.close()
        return 1

    # 4. Validate suggestion exists and is pending
    suggestions = ops.get_suggestions_by_project(conn, project_id)
    suggestion = None
    for s in suggestions:
        if s.id == suggestion_id:
            suggestion = s
            break

    if suggestion is None:
        raise ConfigError(f"Suggestion '{suggestion_id}' not found in project '{project_id}'")

    if suggestion.status != "pending":
        raise ConfigError(
            f"Suggestion '{suggestion_id}' has status '{suggestion.status}', expected 'pending'"
        )

    # 5. Evaluate suggestion
    from social_hook.suggestions import evaluate_suggestion

    try:
        cycle_id = evaluate_suggestion(
            conn,
            config,
            project_id,
            suggestion_id,
            dry_run=dry_run,
        )
    except Exception as e:
        logger.error("Suggestion evaluation failed: %s", e)
        if verbose:
            print(f"Suggestion evaluation failed: {e}", file=sys.stderr)
        conn.close()
        return 1

    if cycle_id is None:
        logger.error("Suggestion evaluation returned no cycle for %s", suggestion_id)
        conn.close()
        return 1

    if verbose:
        print(f"Suggestion {suggestion_id} evaluated, cycle: {cycle_id}")

    conn.close()
    return 0


# Backward-compatible re-exports — tests import these from trigger.py
from social_hook.drafting import (  # noqa: E402, F401
    _generate_media,
    _needs_thread,
    _parse_thread_tweets,
)
