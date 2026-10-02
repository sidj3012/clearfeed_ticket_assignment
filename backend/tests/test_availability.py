"""Unit tests for local-time schedule matching and overnight boundaries."""

from datetime import datetime, time, timezone

from app.assignment import agent_is_available
from app.models import Agent, AvailabilityWindow


def make_agent(windows, timezone_name="UTC"):
    # Build a transient agent so schedule rules can be tested without a database.
    agent = Agent(id=1, company_id=1, name="Test Agent", timezone=timezone_name, max_active_tickets=5)
    agent.availability_windows = [
        AvailabilityWindow(
            id=index + 1,
            agent_id=agent.id,
            day_of_week=day,
            start_time=time.fromisoformat(start),
            end_time=time.fromisoformat(end),
        )
        for index, (day, start, end) in enumerate(windows)
    ]
    return agent


def at(hour, minute=0, day=28):
    # September 28, 2026 is a Monday, which keeps weekday expectations explicit.
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


def test_same_day_availability_includes_start_and_excludes_end():
    # Schedule ranges include the start minute and exclude the end minute.
    agent = make_agent([(0, "09:00", "17:00")])

    assert agent_is_available(agent, at(9)) is True
    assert agent_is_available(agent, at(16, 59)) is True
    assert agent_is_available(agent, at(8, 59)) is False
    assert agent_is_available(agent, at(17)) is False


def test_overnight_availability_spans_midnight_and_excludes_end():
    # Overnight windows continue into the following local day, stopping at end time.
    agent = make_agent([(0, "22:00", "02:00")])

    assert agent_is_available(agent, at(23)) is True
    assert agent_is_available(agent, datetime(2026, 9, 29, 1, 59, tzinfo=timezone.utc)) is True
    assert agent_is_available(agent, datetime(2026, 9, 29, 2, 0, tzinfo=timezone.utc)) is False


def test_saturday_overnight_availability_carries_into_sunday():
    agent = make_agent([(5, "22:00", "02:00")])
    saturday_night = datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc)
    sunday_early = datetime(2026, 10, 4, 1, 30, tzinfo=timezone.utc)

    assert agent_is_available(agent, saturday_night) is True
    assert agent_is_available(agent, sunday_early) is True


def test_availability_uses_the_agent_local_weekday():
    # 02:00 UTC on Monday is still Sunday evening in New York.
    agent = make_agent([(6, "21:00", "23:00")], timezone_name="America/New_York")

    assert agent_is_available(agent, at(2)) is True
