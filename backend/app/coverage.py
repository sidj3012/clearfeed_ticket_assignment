from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .assignment import agent_is_available
from .models import Agent, Company, CoverageWindow


def utc_now() -> datetime:
    # Centralize the clock so coverage calculations can be tested at fixed instants.
    return datetime.now(timezone.utc)


def coverage_window_contains(window: CoverageWindow, weekday: int, local_time: time) -> bool:
    # Treat end times as exclusive and associate overnight hours with their start day.
    previous_day = (weekday - 1) % 7
    if window.start_time < window.end_time:
        return window.day_of_week == weekday and window.start_time <= local_time < window.end_time
    if window.day_of_week == weekday and local_time >= window.start_time:
        return True
    return window.day_of_week == previous_day and local_time < window.end_time


def _segments(required: list[list[bool]], covered: list[list[bool]]) -> tuple[list[dict], list[dict]]:
    # Compress minute-level coverage into readable contiguous ranges for the API.
    covered_periods: list[dict] = []
    gaps: list[dict] = []
    for weekday in range(7):
        minute = 0
        while minute < 1440:
            if not required[weekday][minute]:
                minute += 1
                continue
            is_covered = covered[weekday][minute]
            start = minute
            minute += 1
            while minute < 1440 and required[weekday][minute] and covered[weekday][minute] == is_covered:
                minute += 1
            segment = {
                "day_of_week": weekday,
                "start_time": f"{start // 60:02d}:{start % 60:02d}",
                "end_time": "24:00" if minute == 1440 else f"{minute // 60:02d}:{minute % 60:02d}",
                "covered": is_covered,
            }
            (covered_periods if is_covered else gaps).append(segment)
    return covered_periods, gaps


def build_coverage_summary(
    db: Session,
    company: Company,
    instant: datetime | None = None,
) -> dict:
    # Build a company-local week, then evaluate each minute against all agent schedules.
    company_zone = ZoneInfo(company.timezone)
    now_local = (instant or utc_now()).astimezone(company_zone)
    week_start = now_local.date() - timedelta(days=now_local.weekday())
    start_local = datetime.combine(week_start, time.min, tzinfo=company_zone)
    next_week = week_start + timedelta(days=7)
    end_local = datetime.combine(next_week, time.min, tzinfo=company_zone)
    cursor = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    windows = list(
        db.scalars(
            select(CoverageWindow)
            .where(CoverageWindow.company_id == company.id)
            .order_by(CoverageWindow.day_of_week, CoverageWindow.start_time)
        ).all()
    )
    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.company_id == company.id)
            .options(selectinload(Agent.availability_windows))
            .order_by(Agent.id)
        ).all()
    )

    # Boolean minute grids make overlapping schedules combine naturally.
    required = [[False] * 1440 for _ in range(7)]
    covered = [[False] * 1440 for _ in range(7)]
    while cursor < end_utc:
        local = cursor.astimezone(company_zone)
        weekday = local.weekday()
        minute = local.hour * 60 + local.minute
        local_time = local.timetz().replace(tzinfo=None)
        is_required = any(coverage_window_contains(window, weekday, local_time) for window in windows)
        if is_required:
            required[weekday][minute] = True
            if any(agent_is_available(agent, cursor) for agent in agents):
                covered[weekday][minute] = True
        cursor += timedelta(minutes=1)

    covered_periods, gaps = _segments(required, covered)
    return {
        "company_timezone": company.timezone,
        "week_start": week_start.isoformat(),
        "required_windows": [
            {
                "id": window.id,
                "day_of_week": window.day_of_week,
                "start_time": window.start_time.strftime("%H:%M"),
                "end_time": window.end_time.strftime("%H:%M"),
                "company_id": window.company_id,
            }
            for window in windows
        ],
        "covered_periods": covered_periods,
        "gaps": gaps,
    }
