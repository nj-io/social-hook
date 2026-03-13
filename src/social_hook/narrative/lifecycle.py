"""Lifecycle phase detection and strategy triggers (T18)."""

import sqlite3

from social_hook.config.project import StrategyConfig
from social_hook.db import operations as ops
from social_hook.models import Lifecycle


def detect_lifecycle_phase(signals: dict) -> Lifecycle:
    """Detect project lifecycle phase from git-derived signals.

    Signals are metrics like file churn, test coverage growth, deployment indicators.
    Each signal contributes evidence for a phase. Phase transitions occur when
    confidence > 0.7.

    Args:
        signals: Dict of signal names to values. Expected keys:
            - high_file_churn (bool): Many files changing
            - new_directories (bool): New directory structures
            - docs_heavy (bool): Documentation-focused commits
            - tests_growing (bool): Test files increasing
            - architecture_stabilizing (bool): Less structural change
            - demo_scripts (bool): Demo/example files
            - ux_polish (bool): UI refinements
            - readme_updates (bool): README changes
            - release_tags (bool): Version tags present
            - changelog (bool): CHANGELOG updates
            - deploy_automation (bool): CI/CD changes
            - bugfixes (bool): Fix-type commits dominating
            - optimization (bool): Performance improvements

    Returns:
        Lifecycle with detected phase, confidence, and evidence list
    """
    phase_scores: dict[str, float] = {
        "research": 0.0,
        "build": 0.0,
        "demo": 0.0,
        "launch": 0.0,
        "post_launch": 0.0,
    }
    evidence: list[str] = []

    # Research signals
    if signals.get("high_file_churn"):
        phase_scores["research"] += 0.3
        evidence.append("high_file_churn")
    if signals.get("new_directories"):
        phase_scores["research"] += 0.2
        evidence.append("new_directories")
    if signals.get("docs_heavy"):
        phase_scores["research"] += 0.3
        evidence.append("docs_heavy")

    # Build signals
    if signals.get("tests_growing"):
        phase_scores["build"] += 0.3
        evidence.append("tests_growing")
    if signals.get("architecture_stabilizing"):
        phase_scores["build"] += 0.3
        evidence.append("architecture_stabilizing")

    # Demo signals
    if signals.get("demo_scripts"):
        phase_scores["demo"] += 0.3
        evidence.append("demo_scripts")
    if signals.get("ux_polish"):
        phase_scores["demo"] += 0.2
        evidence.append("ux_polish")
    if signals.get("readme_updates"):
        phase_scores["demo"] += 0.2
        evidence.append("readme_updates")

    # Launch signals
    if signals.get("release_tags"):
        phase_scores["launch"] += 0.4
        evidence.append("release_tags")
    if signals.get("changelog"):
        phase_scores["launch"] += 0.2
        evidence.append("changelog")
    if signals.get("deploy_automation"):
        phase_scores["launch"] += 0.2
        evidence.append("deploy_automation")

    # Post-launch signals
    if signals.get("bugfixes"):
        phase_scores["post_launch"] += 0.3
        evidence.append("bugfixes")
    if signals.get("optimization"):
        phase_scores["post_launch"] += 0.3
        evidence.append("optimization")

    # Find highest-scoring phase
    best_phase = max(phase_scores, key=phase_scores.get)  # type: ignore[arg-type]
    confidence = min(phase_scores[best_phase], 1.0)

    # Default to research with low confidence if no signals
    if confidence == 0.0:
        best_phase = "research"
        confidence = 0.3

    return Lifecycle(
        project_id="",  # Caller sets this
        phase=best_phase,
        confidence=round(confidence, 2),
        evidence=evidence,
    )


def check_strategy_triggers(
    conn: sqlite3.Connection,
    project_id: str,
    config: StrategyConfig | None = None,
    new_lifecycle: Lifecycle | None = None,
) -> list[str]:
    """Check all strategy trigger conditions.

    Combines 5 checks per TECH_ARCH L809-847:
    1. phase_transition - Lifecycle phase changed with high confidence
    2. major_artifact - LLM-driven, flagged by Evaluator (not checked here)
    3. arc_stagnation - Active arc with no posts for N days
    4. narrative_debt_high - Debt counter exceeds threshold
    5. time_elapsed - Days since last strategy moment exceeds max gap

    Args:
        conn: Database connection
        project_id: Project to check
        config: Strategy config with thresholds (defaults used if None)
        new_lifecycle: Newly detected lifecycle phase (for transition check)

    Returns:
        List of triggered condition names
    """
    if config is None:
        config = StrategyConfig()

    triggers: list[str] = []

    # 1. Phase transition — new phase differs from stored with high confidence
    if new_lifecycle and new_lifecycle.confidence > 0.7:
        stored = ops.get_lifecycle(conn, project_id)
        if stored and stored.phase != new_lifecycle.phase:
            triggers.append("phase_transition")
        elif not stored:
            # First lifecycle detection counts as a transition
            triggers.append("phase_transition")

    # 3. Arc stagnation
    stagnation_days = config.arc_stagnation_days
    stagnant = conn.execute(
        """
        SELECT id, theme FROM arcs
        WHERE project_id = ?
          AND status = 'active'
          AND (last_post_at IS NULL OR last_post_at < datetime('now', '-' || ? || ' days'))
        """,
        (project_id, stagnation_days),
    ).fetchall()
    if stagnant:
        triggers.append("arc_stagnation")

    # 4. Narrative debt > threshold
    debt = ops.get_narrative_debt(conn, project_id)
    if debt and debt.debt_counter > config.narrative_debt_threshold:
        triggers.append("narrative_debt_high")

    # 5. Time since last strategy moment
    lifecycle = ops.get_lifecycle(conn, project_id)
    if lifecycle:
        max_gap = config.strategy_moment_max_gap_days
        row = conn.execute(
            """
            SELECT CASE
                WHEN last_strategy_moment IS NULL THEN ?  + 1
                ELSE julianday('now') - julianday(last_strategy_moment)
            END as days_elapsed
            FROM lifecycles WHERE project_id = ?
            """,
            (max_gap, project_id),
        ).fetchone()
        if row and row[0] > max_gap:
            triggers.append("time_elapsed")

    return triggers


def record_strategy_moment(conn: sqlite3.Connection, project_id: str) -> bool:
    """Record that a strategy moment occurred.

    Updates last_strategy_moment to current time.

    Returns True if updated.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return ops.update_lifecycle(
        conn,
        project_id,
        last_strategy_moment=now,
    )


def get_audience_introduced(conn: sqlite3.Connection, project_id: str) -> bool:
    """Check if the audience has been introduced for a project.

    DEPRECATED: Use ops.get_all_platform_introduced() instead.
    """
    return ops.get_audience_introduced(conn, project_id)


def set_audience_introduced(conn: sqlite3.Connection, project_id: str, value: bool) -> bool:
    """Set the audience_introduced flag for a project.

    DEPRECATED: Use ops.set_platform_introduced() instead.
    """
    return ops.set_audience_introduced(conn, project_id, value)
