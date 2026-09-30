import os
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from .assignment import active_workload, agent_is_available, assign_ticket, utc_now
from .coverage import build_coverage_summary
from .database import Base, engine, get_db
from .models import Agent, Assignment, AvailabilityWindow, Company, CoverageWindow, Ticket
from .schemas import (
    AgentCreate,
    AgentConfigUpdate,
    AgentOverviewRead,
    AgentRead,
    AvailabilityWindowInput,
    AvailabilityWindowRead,
    CompanyRead,
    CoverageConfigUpdate,
    CoverageRead,
    TicketCreate,
    TicketListRead,
    TicketStatusUpdate,
    TicketWorkflowRead,
)


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Ticket Assignment API", version="0.1.0", lifespan=lifespan)
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "PUT", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/companies/{company_id}", response_model=CompanyRead)
def get_company(company_id: int, db: Session = Depends(get_db)) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return company


@app.get("/api/companies/{company_id}/agents", response_model=list[AgentRead])
def list_agents(company_id: int, db: Session = Depends(get_db)) -> list[Agent]:
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    query = (
        select(Agent)
        .where(Agent.company_id == company_id)
        .options(selectinload(Agent.availability_windows))
        .order_by(Agent.id)
    )
    return list(db.scalars(query).all())


@app.post(
    "/api/companies/{company_id}/agents",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent(company_id: int, payload: AgentCreate, db: Session = Depends(get_db)) -> Agent:
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    keys = [
        (window.day_of_week, window.start_time, window.end_time)
        for window in payload.availability_windows
    ]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=422, detail="Availability windows must be unique.")

    agent = Agent(
        company_id=company_id,
        name=payload.name,
        timezone=payload.timezone,
        max_active_tickets=payload.max_active_tickets,
    )
    db.add(agent)
    db.flush()
    db.add_all([
        AvailabilityWindow(agent_id=agent.id, **window.model_dump())
        for window in payload.availability_windows
    ])
    db.commit()
    return db.scalar(
        select(Agent)
        .where(Agent.id == agent.id)
        .options(selectinload(Agent.availability_windows))
    )


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

            while cursor < end_utc:
                next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min, tzinfo=utc_zone)
                segment_end = min(next_midnight, end_utc)
                segment_start_text = cursor.strftime("%H:%M")
                segment_end_text = "24:00" if segment_end.date() > cursor.date() else segment_end.strftime("%H:%M")
                ranges.append({
                    "day_of_week": cursor.weekday(),
                    "start_time": segment_start_text,
                    "end_time": segment_end_text,
                })
                cursor = segment_end
        local_day += timedelta(days=1)

    return sorted(ranges, key=lambda item: (item["day_of_week"], item["start_time"], item["end_time"]))


@app.get("/api/companies/{company_id}/agents/overview", response_model=list[AgentOverviewRead])
def list_agent_overview(company_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    instant = utc_now()
    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.company_id == company_id)
            .options(selectinload(Agent.availability_windows))
            .order_by(Agent.id)
        ).all()
    )
    return [
        {
            "id": agent.id,
            "name": agent.name,
            "timezone": agent.timezone,
            "max_active_tickets": agent.max_active_tickets,
            "active_ticket_count": active_workload(db, agent.id),
            "is_available": agent_is_available(agent, instant),
            "availability_hours_utc": availability_hours_in_utc(agent, instant),
        }
        for agent in agents
    ]


@app.put("/api/companies/{company_id}/agents/{agent_id}", response_model=AgentRead)
def update_agent_config(
    company_id: int,
    agent_id: int,
    payload: AgentConfigUpdate,
    db: Session = Depends(get_db),
) -> Agent:
    agent = db.scalar(
        select(Agent)
        .where(Agent.id == agent_id, Agent.company_id == company_id)
        .options(selectinload(Agent.availability_windows))
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found for this company.")
    agent.timezone = payload.timezone
    agent.max_active_tickets = payload.max_active_tickets
    db.commit()
    db.refresh(agent)
    return agent


@app.put("/api/companies/{company_id}/agents/{agent_id}/availability", response_model=list[AvailabilityWindowRead])
def replace_agent_availability(
    company_id: int,
    agent_id: int,
    windows: list[AvailabilityWindowInput],
    db: Session = Depends(get_db),
) -> list[AvailabilityWindow]:
    agent = db.scalar(select(Agent).where(Agent.id == agent_id, Agent.company_id == company_id))
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found for this company.")

    keys = [(w.day_of_week, w.start_time, w.end_time) for w in windows]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=422, detail="Availability windows must be unique.")

    try:
        db.query(AvailabilityWindow).filter(AvailabilityWindow.agent_id == agent_id).delete()
        records = [AvailabilityWindow(agent_id=agent_id, **window.model_dump()) for window in windows]
        db.add_all(records)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=422, detail="Availability contains an invalid or duplicate window.") from None

    return list(
        db.scalars(
            select(AvailabilityWindow)
            .where(AvailabilityWindow.agent_id == agent_id)
            .order_by(AvailabilityWindow.day_of_week, AvailabilityWindow.start_time)
        ).all()
    )


@app.put("/api/companies/{company_id}", response_model=CompanyRead)
def update_company_timezone(
    company_id: int,
    timezone: str,
    db: Session = Depends(get_db),
) -> Company:
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail="Use a valid IANA timezone, such as Asia/Kolkata.") from None
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    company.timezone = timezone
    db.commit()
    db.refresh(company)
    return company


@app.get("/api/companies/{company_id}/coverage", response_model=CoverageRead)
def get_coverage(company_id: int, db: Session = Depends(get_db)) -> dict:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return build_coverage_summary(db, company)


@app.put("/api/companies/{company_id}/coverage", response_model=CoverageRead)
def replace_coverage(
    company_id: int,
    payload: CoverageConfigUpdate,
    db: Session = Depends(get_db),
) -> dict:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    keys = [(window.day_of_week, window.start_time, window.end_time) for window in payload.windows]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=422, detail="Coverage windows must be unique.")

    company.timezone = payload.timezone
    db.query(CoverageWindow).filter(CoverageWindow.company_id == company_id).delete()
    db.add_all(
        [CoverageWindow(company_id=company_id, **window.model_dump()) for window in payload.windows]
    )
    db.commit()
    return build_coverage_summary(db, company)


@app.post(
    "/api/companies/{company_id}/tickets",
    response_model=TicketWorkflowRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(company_id: int, payload: TicketCreate, db: Session = Depends(get_db)) -> dict:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    ticket = Ticket(company_id=company_id, subject=payload.subject, status="open")
    db.add(ticket)
    db.flush()
    result = assign_ticket(db, ticket)
    db.commit()
    return result


@app.get("/api/companies/{company_id}/tickets", response_model=list[TicketListRead])
def list_tickets(company_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    tickets = list(
        db.scalars(
            select(Ticket)
            .where(Ticket.company_id == company_id)
            .options(joinedload(Ticket.assignment).joinedload(Assignment.agent))
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        ).all()
    )
    return [
        {
            "id": ticket.id,
            "company_id": ticket.company_id,
            "subject": ticket.subject,
            "status": ticket.status,
            "created_at": ticket.created_at,
            "agent": (
                {"id": ticket.assignment.agent.id, "name": ticket.assignment.agent.name}
                if ticket.assignment is not None
                else None
            ),
            "assignment_reason": ticket.assignment.reason if ticket.assignment is not None else None,
        }
        for ticket in tickets
    ]


@app.post(
    "/api/companies/{company_id}/tickets/{ticket_id}/assign",
    response_model=TicketWorkflowRead,
)
def retry_ticket_assignment(company_id: int, ticket_id: int, db: Session = Depends(get_db)) -> dict:
    ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id, Ticket.company_id == company_id))
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found for this company.")
    result = assign_ticket(db, ticket)
    db.commit()
    return result


@app.patch("/api/tickets/{ticket_id}", response_model=TicketListRead)
def update_ticket_status(ticket_id: int, payload: TicketStatusUpdate, db: Session = Depends(get_db)) -> dict:
    ticket = db.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(joinedload(Ticket.assignment).joinedload(Assignment.agent))
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    ticket.status = payload.status
    db.commit()
    return {
        "id": ticket.id,
        "company_id": ticket.company_id,
        "subject": ticket.subject,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "agent": (
            {"id": ticket.assignment.agent.id, "name": ticket.assignment.agent.name}
            if ticket.assignment is not None
            else None
        ),
        "assignment_reason": ticket.assignment.reason if ticket.assignment is not None else None,
    }
