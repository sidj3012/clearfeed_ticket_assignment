from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..assignment import agent_is_available, agents_with_workload, utc_now
from ..database import get_db
from ..models import Agent, AvailabilityWindow, Company
from ..schemas import (
    AgentConfigUpdate,
    AgentConfigRead,
    AgentCreate,
    AgentOverviewRead,
    AgentRead,
    AvailabilityWindowRead,
    UniqueScheduleWindows,
)


# Share the company path prefix while keeping agent handlers separate from ticket routes.
router = APIRouter(prefix="/api/companies/{company_id}", tags=["agents"])


@router.get("/agents", response_model=list[AgentRead])
def list_agents(company_id: int, db: Session = Depends(get_db)) -> list[Agent]:
    # Include recurring windows so the setup screen can edit the full agent record.
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    query = (
        select(Agent)
        .where(Agent.company_id == company_id)
        .options(selectinload(Agent.availability_windows))
        .order_by(Agent.id)
    )
    return list(db.scalars(query).all())


@router.post("/agents", response_model=AgentRead, status_code=201)
def create_agent(company_id: int, payload: AgentCreate, db: Session = Depends(get_db)) -> Agent:
    # Validate the company and unique schedule rows before storing a new agent.
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    agent = Agent(
        company_id=company_id,
        name=payload.name,
        timezone=payload.timezone,
        max_active_tickets=payload.max_active_tickets,
    )
    # Attach schedules through the relationship so the response can reuse this object.
    agent.availability_windows = [
        AvailabilityWindow(**window.model_dump()) for window in payload.availability_windows
    ]
    db.add(agent)
    db.commit()
    return agent


def availability_hours_in_utc(agent: Agent, instant: datetime) -> list[dict]:
    """Convert recurring agent schedules into UTC ranges for the current UTC week."""
    week_start = instant.astimezone(timezone.utc).date()
    week_start -= timedelta(days=week_start.weekday())
    week_end = week_start + timedelta(days=7)
    utc_zone = timezone.utc
    local_zone = ZoneInfo(agent.timezone)
    ranges: list[dict] = []

    # Include adjacent local dates so windows crossing the UTC week boundary are clipped correctly.
    local_day = week_start - timedelta(days=1)
    while local_day <= week_end:
        for window in agent.availability_windows:
            if window.day_of_week != local_day.weekday():
                continue
            local_start = datetime.combine(local_day, window.start_time, tzinfo=local_zone)
            end_day = local_day + timedelta(days=1) if window.start_time > window.end_time else local_day
            local_end = datetime.combine(end_day, window.end_time, tzinfo=local_zone)
            cursor = max(local_start.astimezone(utc_zone), datetime.combine(week_start, time.min, tzinfo=utc_zone))
            end_utc = min(local_end.astimezone(utc_zone), datetime.combine(week_end, time.min, tzinfo=utc_zone))

            # Split overnight ranges at UTC midnight for a simple weekday/time response.
            while cursor < end_utc:
                next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min, tzinfo=utc_zone)
                segment_end = min(next_midnight, end_utc)
                ranges.append({
                    "day_of_week": cursor.weekday(),
                    "start_time": cursor.strftime("%H:%M"),
                    "end_time": "24:00" if segment_end.date() > cursor.date() else segment_end.strftime("%H:%M"),
                })
                cursor = segment_end
        local_day += timedelta(days=1)

    return sorted(ranges, key=lambda item: (item["day_of_week"], item["start_time"], item["end_time"]))


@router.get("/agents/overview", response_model=list[AgentOverviewRead])
def list_agent_overview(company_id: int, db: Session = Depends(get_db)) -> list[dict]:
    # Combine live workload and schedule-derived availability for the agents dashboard.
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    instant = utc_now()
    # Fetch all agent workload totals in one query instead of issuing one count per agent.
    agents = agents_with_workload(db, company_id)
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "timezone": agent.timezone,
            "max_active_tickets": agent.max_active_tickets,
            "active_ticket_count": workload,
            "is_available": agent_is_available(agent, instant),
            "availability_hours_utc": availability_hours_in_utc(agent, instant),
        }
        for agent, workload in agents
    ]


@router.put("/agents/{agent_id}", response_model=AgentConfigRead)
def update_agent_config(
    company_id: int,
    agent_id: int,
    payload: AgentConfigUpdate,
    db: Session = Depends(get_db),
) -> Agent:
    # Update the agent's timezone and capacity without replacing their weekly schedule.
    agent = db.scalar(
        select(Agent)
        .where(Agent.id == agent_id, Agent.company_id == company_id)
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found for this company.")
    agent.timezone = payload.timezone
    agent.max_active_tickets = payload.max_active_tickets
    db.commit()
    db.refresh(agent)
    return agent


@router.put("/agents/{agent_id}/availability", response_model=list[AvailabilityWindowRead])
def replace_agent_availability(
    company_id: int,
    agent_id: int,
    windows: UniqueScheduleWindows,
    db: Session = Depends(get_db),
) -> list[AvailabilityWindow]:
    # Replace all recurring windows atomically so a failed schedule cannot leave partial data.
    agent = db.scalar(select(Agent).where(Agent.id == agent_id, Agent.company_id == company_id))
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found for this company.")

    # Roll back the delete and inserts together if a database constraint rejects a window.
    try:
        db.query(AvailabilityWindow).filter(AvailabilityWindow.agent_id == agent_id).delete()
        records = [AvailabilityWindow(agent_id=agent_id, **window.model_dump()) for window in windows]
        db.add_all(records)
        db.commit()
    except IntegrityError:
        db.rollback()
        # The JSON is valid, but its schedule violates a domain constraint, so return 422.
        raise HTTPException(status_code=422, detail="Availability contains an invalid or duplicate window.") from None

    return list(
        db.scalars(
            select(AvailabilityWindow)
            .where(AvailabilityWindow.agent_id == agent_id)
            .order_by(AvailabilityWindow.day_of_week, AvailabilityWindow.start_time)
        ).all()
    )
