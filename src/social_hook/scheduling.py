"""Scheduling algorithm for optimal post timing."""

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
    """Calculate the optimal time to post.

    Algorithm:
    0. If max_per_week set, count posts in last 7 days → defer if limit reached
    1. Count today's posts (cross-project) → check max_posts_per_day
    2. Get last post time (cross-project) → enforce min_gap_minutes
    3. Find first available optimal hour satisfying all constraints
    4. If no slots today → advance to next day, prefer optimal_days
    5. FIFO: earlier created_at gets the slot if two drafts target same time

    Args:
        conn: Database connection
        project_id: Project ID (for future per-project limits)
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
    if optimal_days is None:
        optimal_days = ["Tue", "Wed", "Thu"]
    if optimal_hours is None:
        optimal_hours = [9, 12, 17]

    try:
        user_tz = ZoneInfo(tz)
    except (KeyError, ValueError):
        user_tz = ZoneInfo("UTC")

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(user_tz)

    # Check weekly limit (early exit)
    if max_per_week is not None:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE project_id = ? AND posted_at >= datetime('now', '-7 days')",
            (project_id,),
        )
        weekly_count = cursor.fetchone()[0]
        if weekly_count >= max_per_week:
            return ScheduleResult(
                datetime=now_utc,
                deferred=True,
                is_optimal_day=False,
                day_reason=f"Weekly limit ({weekly_count}/{max_per_week}) reached",
                time_reason="deferred",
            )

    # Get today's start in UTC for querying
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(timezone.utc)

    # Count today's posts (filter by platform when provided)
    today_posts = ops.get_all_recent_posts(conn, today_start_utc.strftime("%Y-%m-%d %H:%M:%S"))
    if platform:
        today_posts = [p for p in today_posts if p.platform == platform]
    posts_today_count = len(today_posts)

    # Get last post time
    last_post_time = None
    if today_posts:
        # Posts are ordered DESC, first is most recent
        last_posted_at = today_posts[0].posted_at
        if last_posted_at:
            if isinstance(last_posted_at, str):
                last_post_time = datetime.fromisoformat(last_posted_at)
            else:
                last_post_time = last_posted_at
            if last_post_time.tzinfo is None:
                last_post_time = last_post_time.replace(tzinfo=timezone.utc)

    # Also check scheduled drafts that haven't posted yet
    ops.get_due_drafts(conn)
    all_pending = ops.get_all_pending_drafts(conn)
    scheduled_times = []
    for d in all_pending:
        if d.status == "scheduled" and d.scheduled_time:
            # Filter by platform when provided
            if platform and d.platform != platform:
                continue
            st = d.scheduled_time
            if isinstance(st, str):
                st = datetime.fromisoformat(st)
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            scheduled_times.append(st)

    for d in optimal_days:
        if d not in _DAY_MAP:
            logger.warning(
                "Unrecognized day name in optimal_days: %r (expected: %s)", d, list(_DAY_MAP.keys())
            )
    optimal_day_nums = [_DAY_MAP[d] for d in optimal_days if d in _DAY_MAP]

    # Try to find a slot, starting from now, up to 7 days out
    for day_offset in range(8):
        candidate_date = now_local + timedelta(days=day_offset)
        candidate_weekday = candidate_date.weekday()
        is_optimal = candidate_weekday in optimal_day_nums

        # Check if we're over max posts for this day
        if day_offset == 0 and posts_today_count >= max_posts_per_day:
            continue

        day_reason = (
            f"Optimal day ({optimal_days})"
            if is_optimal
            else f"Non-optimal day (preferred: {optimal_days})"
        )

        # Try each optimal hour
        sorted_hours = sorted(optimal_hours)
        for hour in sorted_hours:
            candidate = candidate_date.replace(hour=hour, minute=0, second=0, microsecond=0)

            # Skip if in the past
            if candidate <= now_local:
                continue

            candidate_utc = candidate.astimezone(timezone.utc)

            # Check min gap
            if last_post_time and (candidate_utc - last_post_time) < timedelta(
                minutes=min_gap_minutes
            ):
                continue

            # Check against already-scheduled times
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

        # If today is optimal but all hours are taken, note it
        if is_optimal:
            continue

    # Fallback: schedule for 1 hour from now if no optimal slot found
    fallback = now_utc + timedelta(hours=1)
    fallback_local = fallback.astimezone(user_tz)
    return ScheduleResult(
        datetime=fallback,
        is_optimal_day=fallback_local.weekday() in optimal_day_nums,
        day_reason="No optimal slot available within 7 days",
        time_reason="Fallback: 1 hour from now",
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
