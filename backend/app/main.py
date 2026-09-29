import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .database import Base, engine, get_db
from .models import Agent, AvailabilityWindow, Company
from .schemas import AgentConfigUpdate, AgentRead, AvailabilityWindowInput, CompanyRead


app = FastAPI(title="Ticket Assignment API", version="0.1.0")
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "PUT", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


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
