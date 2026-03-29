"""Scheduling algorithm for optimal post timing.

The core algorithm (find_optimal_slot) is a pure function with zero
database or domain dependencies — it takes lists of existing times
and scheduling constraints, and returns the next available slot.

calculate_optimal_time() wraps find_optimal_slot() with DB queries
for the social-hook domain (posts, scheduled drafts, weekly limits).
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from social_hook.db import operations as ops

logger = logging.getLogger(__name__)


@dataclass
class ScheduleResult:
    """Result of scheduling calculation."""

    datetime: datetime
    is_optimal_day: bool
    day_reason: str
    time_reason: str
    deferred: bool = False


@dataclass
class PlatformSchedulingState:
    """Per-platform scheduling state snapshot."""

    platform: str
    posts_today: int
    max_posts_per_day: int
    pending_drafts: int
    deferred_drafts: int
    slots_remaining_today: int


@dataclass
class ProjectSchedulingState:
    """Project-wide scheduling state snapshot."""

    weekly_posts: int
    max_per_week: int | None
    platform_states: list[PlatformSchedulingState]


# Day name to weekday number mapping (Monday=0)
_DAY_MAP = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}


def find_optimal_slot(
    existing_post_times: list[datetime],
    scheduled_times: list[datetime],
    *,
    tz: str = "UTC",
    posts_today_count: int = 0,
    max_posts_per_day: int = 3,
    min_gap_minutes: int = 30,
    optimal_days: list[str] | None = None,
    optimal_hours: list[int] | None = None,
    weekly_count: int = 0,
    max_per_week: int | None = None,
    now: datetime | None = None,
) -> ScheduleResult:
    """Find the next optimal time slot given constraints.

    Pure function — no database or domain dependencies. Takes lists of
    existing times and scheduling parameters, returns the best slot.

    REUSABILITY: This function has zero project-specific dependencies.
    It works with any system that needs rate-limited, time-optimized
    scheduling (social media, email campaigns, notification batching, etc.).

    Algorithm:
    0. If max_per_week set and weekly_count >= limit → defer
    1. Check posts_today_count against max_posts_per_day
    2. Enforce min_gap_minutes from last post and scheduled times
    3. Find first available optimal hour satisfying all constraints
    4. If no slots today → advance to next day, prefer optimal_days
    5. Scan up to 7 days out, then fallback to 1 hour from now

    Args:
        existing_post_times: UTC datetimes of already-published posts
            (most recent first). Used for min-gap enforcement.
        scheduled_times: UTC datetimes of already-scheduled-but-not-posted
            items. Used to avoid scheduling conflicts.
        tz: Timezone string for local time interpretation.
        posts_today_count: Number of posts already made today.
        max_posts_per_day: Maximum posts per day.
        min_gap_minutes: Minimum minutes between posts.
        optimal_days: Preferred days (e.g. ["Tue", "Wed", "Thu"]).
        optimal_hours: Preferred hours in local time (e.g. [9, 12, 17]).
        weekly_count: Number of posts in the last 7 days.
        max_per_week: Maximum posts per week (None = no limit).
        now: Current time override (for testing). Defaults to now(UTC).

    Returns:
        ScheduleResult with optimal datetime (UTC) and reasoning.
    """
    if optimal_days is None:
        optimal_days = ["Tue", "Wed", "Thu"]
    if optimal_hours is None:
        optimal_hours = [9, 12, 17]

    try:
        user_tz = ZoneInfo(tz)
    except (KeyError, ValueError):
        user_tz = ZoneInfo("UTC")

    now_utc = now if now is not None else datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_local = now_utc.astimezone(user_tz)

    # Weekly limit check
    if max_per_week is not None and weekly_count >= max_per_week:
        return ScheduleResult(
            datetime=now_utc,
            deferred=True,
            is_optimal_day=False,
            day_reason=f"Weekly limit ({weekly_count}/{max_per_week}) reached",
            time_reason="deferred",
        )

    # Most recent post time for gap enforcement
    last_post_time = None
    if existing_post_times:
        last_post_time = existing_post_times[0]
        if last_post_time.tzinfo is None:
            last_post_time = last_post_time.replace(tzinfo=timezone.utc)

    for day_name in optimal_days:
        if day_name not in _DAY_MAP:
            logger.warning(
                "Unrecognized day name in optimal_days: %r (expected: %s)",
                day_name,
                list(_DAY_MAP.keys()),
            )
    optimal_day_nums = [_DAY_MAP[d] for d in optimal_days if d in _DAY_MAP]
    sorted_optimal_hours = sorted(optimal_hours)

    for day_offset in range(8):
        candidate_date = now_local + timedelta(days=day_offset)
        candidate_weekday = candidate_date.weekday()
        is_optimal = candidate_weekday in optimal_day_nums

        if day_offset == 0 and posts_today_count >= max_posts_per_day:
            continue

        day_reason = (
            f"Optimal day ({optimal_days})"
            if is_optimal
            else f"Non-optimal day (preferred: {optimal_days})"
        )

        for hour in sorted_optimal_hours:
            candidate = candidate_date.replace(hour=hour, minute=0, second=0, microsecond=0)

            if candidate <= now_local:
                continue

            candidate_utc = candidate.astimezone(timezone.utc)

            if last_post_time and (candidate_utc - last_post_time) < timedelta(
                minutes=min_gap_minutes
            ):
                continue

            conflict = False
            for st in scheduled_times:
                if abs((candidate_utc - st).total_seconds()) < min_gap_minutes * 60:
                    conflict = True
                    break
            if conflict:
                continue

            return ScheduleResult(
                datetime=candidate_utc,
                is_optimal_day=is_optimal,
                day_reason=day_reason,
                time_reason=f"Optimal hour ({hour}:00 {tz})",
            )

        if is_optimal:
            continue

    fallback = now_utc + timedelta(hours=1)
    fallback_local = fallback.astimezone(user_tz)
    return ScheduleResult(
        datetime=fallback,
        is_optimal_day=fallback_local.weekday() in optimal_day_nums,
        day_reason="No optimal slot available within 7 days",
        time_reason="Fallback: 1 hour from now",
    )


def calculate_optimal_time(
    conn: sqlite3.Connection,
    project_id: str,
    platform: str | None = None,
    tz: str = "UTC",
    max_posts_per_day: int = 3,
    min_gap_minutes: int = 30,
    optimal_days: list[str] | None = None,
    optimal_hours: list[int] | None = None,
    max_per_week: int | None = None,
) -> ScheduleResult:
    """Calculate the optimal time to post (DB-aware wrapper).

    Queries the database for existing posts and scheduled drafts,
    then delegates to ``find_optimal_slot()`` for the pure algorithm.

    Args:
        conn: Database connection
        project_id: Project ID (for weekly limit queries)
        platform: Filter by platform (None = cross-platform behavior)
        tz: Timezone string (e.g. "America/Los_Angeles")
        max_posts_per_day: Maximum posts per day across all projects
        min_gap_minutes: Minimum minutes between posts
        optimal_days: Preferred days (e.g. ["Tue", "Wed", "Thu"])
        optimal_hours: Preferred hours in local time (e.g. [9, 12, 17])
        max_per_week: Maximum posts per week for this project (None = no limit)

    Returns:
        ScheduleResult with optimal datetime (UTC) and reasoning
    """
    try:
        user_tz = ZoneInfo(tz)
    except (KeyError, ValueError):
        user_tz = ZoneInfo("UTC")

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(user_tz)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(timezone.utc)

    # Weekly count
    weekly_count = 0
    if max_per_week is not None:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE project_id = ? AND posted_at >= datetime('now', '-7 days')",
            (project_id,),
        )
        weekly_count = cursor.fetchone()[0]

    # Today's posts
    today_posts = ops.get_all_recent_posts(conn, today_start_utc.strftime("%Y-%m-%d %H:%M:%S"))
    if platform:
        today_posts = [p for p in today_posts if p.platform == platform]

    # Extract post times for the pure function
    existing_post_times: list[datetime] = []
    for p in today_posts:
        if p.posted_at:
            pt = (
                datetime.fromisoformat(p.posted_at) if isinstance(p.posted_at, str) else p.posted_at
            )
            if pt.tzinfo is None:
                pt = pt.replace(tzinfo=timezone.utc)
            existing_post_times.append(pt)

    # Scheduled-but-not-posted times
    all_pending = ops.get_all_pending_drafts(conn)
    sched_times: list[datetime] = []
    for d in all_pending:
        if d.status == "scheduled" and d.scheduled_time:
            if platform and d.platform != platform:
                continue
            st = (
                datetime.fromisoformat(d.scheduled_time)
                if isinstance(d.scheduled_time, str)
                else d.scheduled_time
            )
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            sched_times.append(st)

    return find_optimal_slot(
        existing_post_times,
        sched_times,
        tz=tz,
        posts_today_count=len(today_posts),
        max_posts_per_day=max_posts_per_day,
        min_gap_minutes=min_gap_minutes,
        optimal_days=optimal_days,
        optimal_hours=optimal_hours,
        weekly_count=weekly_count,
        max_per_week=max_per_week,
        now=now_utc,
    )


def _is_today(dt: datetime, user_tz: ZoneInfo) -> bool:
    """Check if a datetime falls on today in the given timezone."""
    now_local = datetime.now(timezone.utc).astimezone(user_tz)
    dt_local = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(user_tz)
    return dt_local.date() == now_local.date()


def get_scheduling_state(
    conn: sqlite3.Connection,
    project_id: str,
    config,
) -> ProjectSchedulingState:
    """Gather current scheduling state for a project across all enabled platforms.

    Args:
        conn: Database connection.
        project_id: Project ID.
        config: Global Config object (needs .platforms, .scheduling).

    Returns:
        ProjectSchedulingState with per-platform breakdowns.
    """
    from social_hook.config.platforms import resolve_platform

    try:
        user_tz = ZoneInfo(config.scheduling.timezone)
    except (KeyError, ValueError):
        user_tz = ZoneInfo("UTC")

    # Timezone-aware today start (same pattern as calculate_optimal_time)
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(user_tz)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(timezone.utc)

    # Get today's posts across all platforms
    today_posts = ops.get_all_recent_posts(conn, today_start_utc.strftime("%Y-%m-%d %H:%M:%S"))

    # Get all pending drafts for this project
    all_pending = ops.get_pending_drafts(conn, project_id)

    # Weekly total
    cursor = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE project_id = ? AND posted_at >= datetime('now', '-7 days')",
        (project_id,),
    )
    weekly_posts = cursor.fetchone()[0]

    platform_states = []
    for pname, pcfg in config.platforms.items():
        if not pcfg.enabled:
            continue

        resolved = resolve_platform(pname, pcfg, config.scheduling)

        # Count today's posts for this platform
        platform_posts_today = len([p for p in today_posts if p.platform == pname])

        # Split pending drafts by status for this platform
        platform_pending = [
            d for d in all_pending if d.platform == pname and d.status != "deferred"
        ]
        platform_deferred = [
            d for d in all_pending if d.platform == pname and d.status == "deferred"
        ]

        # Count scheduled-for-today drafts to compute remaining slots
        scheduled_today = 0
        for d in platform_pending:
            if d.scheduled_time:
                st = d.scheduled_time
                if isinstance(st, str):
                    st = datetime.fromisoformat(st)
                if _is_today(st, user_tz):
                    scheduled_today += 1

        slots_remaining = max(
            0, resolved.max_posts_per_day - platform_posts_today - scheduled_today
        )

        platform_states.append(
            PlatformSchedulingState(
                platform=pname,
                posts_today=platform_posts_today,
                max_posts_per_day=resolved.max_posts_per_day,
                pending_drafts=len(platform_pending),
                deferred_drafts=len(platform_deferred),
                slots_remaining_today=slots_remaining,
            )
        )

    return ProjectSchedulingState(
        weekly_posts=weekly_posts,
        max_per_week=config.scheduling.max_per_week,
        platform_states=platform_states,
    )
