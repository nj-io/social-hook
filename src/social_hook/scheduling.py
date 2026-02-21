"""Scheduling algorithm for optimal post timing."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from zoneinfo import ZoneInfo

from social_hook.db import operations as ops


@dataclass
class ScheduleResult:
    """Result of scheduling calculation."""

    datetime: datetime
    is_optimal_day: bool
    day_reason: str
    time_reason: str


# Day name to weekday number mapping (Monday=0)
_DAY_MAP = {
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
    "Fri": 4, "Sat": 5, "Sun": 6,
}


def calculate_optimal_time(
    conn: sqlite3.Connection,
    project_id: str,
    platform: Optional[str] = None,
    tz: str = "UTC",
    max_posts_per_day: int = 3,
    min_gap_minutes: int = 30,
    optimal_days: Optional[list[str]] = None,
    optimal_hours: Optional[list[int]] = None,
) -> ScheduleResult:
    """Calculate the optimal time to post.

    Algorithm:
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

    # Get today's start in UTC for querying
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(timezone.utc)

    # Count today's posts (filter by platform when provided)
    today_posts = ops.get_all_recent_posts(
        conn, today_start_utc.strftime("%Y-%m-%d %H:%M:%S")
    )
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
    due_drafts = ops.get_due_drafts(conn)
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
            candidate = candidate_date.replace(
                hour=hour, minute=0, second=0, microsecond=0
            )

            # Skip if in the past
            if candidate <= now_local:
                continue

            candidate_utc = candidate.astimezone(timezone.utc)

            # Check min gap
            if last_post_time and (candidate_utc - last_post_time) < timedelta(minutes=min_gap_minutes):
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
