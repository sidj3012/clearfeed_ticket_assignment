from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from .models import Agent, Assignment, AvailabilityWindow, Ticket


ACTIVE_STATUSES = ("open", "in_progress", "pending")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def agent_is_available(agent: Agent, instant: datetime) -> bool:
    local = instant.astimezone(ZoneInfo(agent.timezone))
    weekday = local.weekday()
    local_time = local.timetz().replace(tzinfo=None)
    previous_day = (weekday - 1) % 7

    for window in agent.availability_windows:
        if window.start_time < window.end_time:
            if window.day_of_week == weekday and window.start_time <= local_time < window.end_time:
                return True
        else:
            if window.day_of_week == weekday and local_time >= window.start_time:
                return True
            if window.day_of_week == previous_day and local_time < window.end_time:
                return True
    return False


def active_workload(db: Session, agent_id: int) -> int:
    query = (
        select(func.count(Assignment.id))
        .join(Ticket, Ticket.id == Assignment.ticket_id)
        .where(Assignment.agent_id == agent_id, Ticket.status.in_(ACTIVE_STATUSES))
    )
    return int(db.scalar(query) or 0)


def no_assignment_result(
    db: Session,
    ticket: Ticket,
    reason_code: str,
    available_agents: list[Agent] | None = None,
) -> dict:
    reasons = {
        "NO_AGENTS_FOUND": "No agents are configured for this company.",
        "NO_AVAILABLE_AGENT": "No agent is currently scheduled to be available.",
        "ALL_AGENTS_AT_CAPACITY": "All currently available agents have reached their active ticket limit.",
    }
    return {
        "id": ticket.id,
        "company_id": ticket.company_id,
        "subject": ticket.subject,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "assigned": False,
        "agent": None,
        "current_workload": None,
        "assigned_at": None,
        "reason_code": reason_code,
        "reason": reasons[reason_code],
        "available_agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "active_ticket_count": active_workload(db, agent.id),
                "max_active_tickets": agent.max_active_tickets,
            }
            for agent in available_agents or []
        ],
    }


def assign_ticket(db: Session, ticket: Ticket, instant: datetime | None = None) -> dict:
    existing = db.scalar(
        select(Assignment).where(Assignment.ticket_id == ticket.id).options(joinedload(Assignment.agent))
    )
    if existing is not None:
        return {
            "id": ticket.id,
            "company_id": ticket.company_id,
            "subject": ticket.subject,
            "status": ticket.status,
            "created_at": ticket.created_at,
            "assigned": True,
            "agent": {"id": existing.agent.id, "name": existing.agent.name},
            "current_workload": active_workload(db, existing.agent_id),
            "assigned_at": existing.assigned_at,
            "reason_code": None,
            "reason": existing.reason,
        }

    agents = list(
        db.scalars(
            select(Agent)
            .where(Agent.company_id == ticket.company_id)
            .options(selectinload(Agent.availability_windows))
            .with_for_update()
            .order_by(Agent.id)
        ).all()
    )
    if not agents:
        return no_assignment_result(db, ticket, "NO_AGENTS_FOUND")

    check_at = instant or utc_now()
    available = [agent for agent in agents if agent_is_available(agent, check_at)]
    if not available:
        return no_assignment_result(db, ticket, "NO_AVAILABLE_AGENT")

    counts = {agent.id: active_workload(db, agent.id) for agent in available}
    eligible = [agent for agent in available if counts[agent.id] < agent.max_active_tickets]
    if not eligible:
        return no_assignment_result(db, ticket, "ALL_AGENTS_AT_CAPACITY", available)

    def tie_break_key(agent: Agent) -> tuple[datetime, int]:
        last_assigned = agent.last_assigned_at
        if last_assigned is None:
            last_assigned = datetime.min.replace(tzinfo=timezone.utc)
        elif last_assigned.tzinfo is None:
            last_assigned = last_assigned.replace(tzinfo=timezone.utc)
        return last_assigned, agent.id

    lowest_workload = min(counts[agent.id] for agent in eligible)
    fairest_candidates = [agent for agent in eligible if counts[agent.id] == lowest_workload]
    selected = min(fairest_candidates, key=tie_break_key)
    assigned_at = check_at
    reason = f"{selected.name} was selected because they are currently available and have the lowest active workload ({lowest_workload})."
    if len(fairest_candidates) > 1:
        reason += " They were assigned least recently among candidates tied on workload."
    try:
        with db.begin_nested():
            assignment = Assignment(ticket_id=ticket.id, agent_id=selected.id, assigned_at=assigned_at, reason=reason)
            db.add(assignment)
            selected.last_assigned_at = assigned_at
            db.flush()
    except IntegrityError:
        existing = db.scalar(
            select(Assignment).where(Assignment.ticket_id == ticket.id).options(joinedload(Assignment.agent))
        )
        if existing is None:
            raise
        return assign_ticket(db, ticket, check_at)

    return {
        "id": ticket.id,
        "company_id": ticket.company_id,
        "subject": ticket.subject,
        "status": ticket.status,
        "created_at": ticket.created_at,
        "assigned": True,
        "agent": {"id": selected.id, "name": selected.name},
        "current_workload": counts[selected.id] + (1 if ticket.status in ACTIVE_STATUSES else 0),
        "assigned_at": assigned_at,
        "reason_code": None,
        "reason": reason,
    }
