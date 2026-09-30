import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .assignment import assign_ticket
from .coverage import build_coverage_summary
from .database import get_db
from .models import Assignment, Company, CoverageWindow, Ticket
from .routers.agents import router as agents_router
from .schemas import (
    CompanyRead,
    CoverageConfigUpdate,
    CoverageRead,
    TicketCreate,
    TicketListRead,
    TicketStatusUpdate,
    TicketWorkflowRead,
)


app = FastAPI(title="Ticket Assignment API", version="0.1.0")
app.include_router(agents_router)
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
