from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from .enums import TicketStatus, UnassignedReasonCode
from .models import Agent, Assignment, Ticket


ACTIVE_STATUSES = (TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value, TicketStatus.PENDING.value)


def utc_now() -> datetime:
    # Keep time generation centralized so time-dependent behavior is easy to test.
    return datetime.now(timezone.utc)


def agent_is_available(agent: Agent, instant: datetime) -> bool:
    # Compare the instant in the agent's own timezone, including overnight schedules.
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
    # Resolved and closed tickets no longer consume an agent's active-ticket capacity.
    query = (
        select(func.count(Assignment.id))
        .join(Ticket, Ticket.id == Assignment.ticket_id)
        .where(Assignment.agent_id == agent_id, Ticket.status.in_(ACTIVE_STATUSES))
    )
    return int(db.scalar(query) or 0)


def agents_with_workload(db: Session, company_id: int, *, lock: bool = False) -> list[tuple[Agent, int]]:
    """Load agents and workload totals in one query, optionally locking agent rows."""
    # Aggregate tickets once, then join those totals onto the company agent query.
    workload_totals = (
        select(Assignment.agent_id.label("agent_id"), func.count(Assignment.id).label("active_workload"))
        .join(Ticket, Ticket.id == Assignment.ticket_id)
        .where(
            Ticket.status.in_(ACTIVE_STATUSES),
            Assignment.agent_id.in_(select(Agent.id).where(Agent.company_id == company_id).correlate(None)),
        )
        .group_by(Assignment.agent_id)
        .subquery()
    )
    query = (
        select(Agent, func.coalesce(workload_totals.c.active_workload, 0).label("active_workload"))
        .outerjoin(workload_totals, workload_totals.c.agent_id == Agent.id)
        .where(Agent.company_id == company_id)
        .options(selectinload(Agent.availability_windows))
        .order_by(Agent.id)
    )
    if lock:
        # Lock only agent rows while reading counts; concurrent assignments must wait here.
        query = query.with_for_update(of=Agent)
    return [(agent, int(count or 0)) for agent, count in db.execute(query).all()]


def no_assignment_result(
    ticket: Ticket,
    reason_code: UnassignedReasonCode,
    available_agents: list[Agent] | None = None,
    workloads: dict[int, int] | None = None,
) -> dict:
    # Return a consistent API shape so callers can explain every unassigned outcome.
    reasons = {
        UnassignedReasonCode.NO_AGENTS_FOUND: "No agents are configured for this company.",
        UnassignedReasonCode.NO_AVAILABLE_AGENT: "No agent is currently scheduled to be available.",
        UnassignedReasonCode.ALL_AGENTS_AT_CAPACITY: "All currently available agents have reached their active ticket limit.",
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
        "reason_code": reason_code.value,
        "reason": reasons[reason_code],
        "available_agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "active_ticket_count": (workloads or {}).get(agent.id, 0),
                "max_active_tickets": agent.max_active_tickets,
            }
            for agent in available_agents or []
        ],
    }


def assign_ticket(db: Session, ticket: Ticket, instant: datetime | None = None) -> dict:
    # Retries are idempotent: return the original assignment if one already exists.
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

    # Lock agents in ID order while reading aggregate counts so concurrent requests
    # cannot both claim the same last slot, and avoid one ticket-count query per agent.
    agent_workloads = agents_with_workload(db, ticket.company_id, lock=True)
    agents = [agent for agent, _workload in agent_workloads]
    if not agents:
        return no_assignment_result(ticket, UnassignedReasonCode.NO_AGENTS_FOUND)

    # Use one timestamp for eligibility, fairness bookkeeping, and the assignment record.
    check_at = instant or utc_now()
    available_workloads = [
        (agent, workload)
        for agent, workload in agent_workloads
        if agent_is_available(agent, check_at)
    ]
    available = [agent for agent, _workload in available_workloads]
    if not available:
        return no_assignment_result(ticket, UnassignedReasonCode.NO_AVAILABLE_AGENT)

    # Reuse the workload totals returned with the agent query for eligibility and tie breaks.
    counts = {agent.id: workload for agent, workload in available_workloads}
    eligible = [agent for agent in available if counts[agent.id] < agent.max_active_tickets]
    if not eligible:
        return no_assignment_result(
            ticket,
            UnassignedReasonCode.ALL_AGENTS_AT_CAPACITY,
            available,
            counts,
        )

    # Prefer least-recently assigned when workloads tie; agent ID makes ties deterministic.
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
    # Save assignment and fairness timestamp together inside a savepoint.
    # The unique ticket constraint is a final guard against duplicate concurrent retries.
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
