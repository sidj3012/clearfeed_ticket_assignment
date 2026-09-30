from datetime import datetime, time, timedelta, timezone as dt_timezone

from sqlalchemy import select, text

from .database import SessionLocal, engine
from .models import Agent, Assignment, AvailabilityWindow, Company, CoverageWindow, Ticket


def seed() -> None:
    with SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.id == 1))
        if company is None:
            company = Company(id=1, name="Northstar Support", timezone="Asia/Kolkata")
            db.add(company)
            db.flush()

        seeded_agents = [
            (1, "Asha Patel", "Asia/Kolkata", 8),
            (2, "Jordan Lee", "America/New_York", 6),
            (3, "Sam Taylor", "Europe/London", 7),
        ]
        for agent_id, name, timezone, capacity in seeded_agents:
            agent = db.scalar(select(Agent).where(Agent.id == agent_id))
            if agent is None:
                agent = Agent(
                    id=agent_id,
                    company_id=company.id,
                    name=name,
                    timezone=timezone,
                    max_active_tickets=capacity,
                )
                db.add(agent)
                db.flush()
                if agent_id == 1:
                    windows = [
                        (0, time(9, 0), time(17, 0)),
                        (1, time(9, 0), time(17, 0)),
                        (2, time(9, 0), time(17, 0)),
                        (3, time(9, 0), time(17, 0)),
                        (4, time(9, 0), time(17, 0)),
                    ]
                elif agent_id == 2:
                    windows = [
                        (0, time(9, 0), time(17, 0)),
                        (1, time(9, 0), time(17, 0)),
                        (2, time(9, 0), time(17, 0)),
                        (3, time(9, 0), time(17, 0)),
                        (4, time(9, 0), time(17, 0)),
                    ]
                else:
                    windows = [
                        (0, time(22, 0), time(2, 0)),
                        (1, time(22, 0), time(2, 0)),
                        (2, time(22, 0), time(2, 0)),
                        (3, time(22, 0), time(2, 0)),
                        (4, time(22, 0), time(2, 0)),
                    ]
                db.add_all(
                    [AvailabilityWindow(agent_id=agent.id, day_of_week=day, start_time=start, end_time=end)
                     for day, start, end in windows]
                )

        for day in range(5):
            existing_window = db.scalar(
                select(CoverageWindow).where(
                    CoverageWindow.company_id == company.id,
                    CoverageWindow.day_of_week == day,
                    CoverageWindow.start_time == time(9, 0),
                    CoverageWindow.end_time == time(18, 0),
                )
            )
            if existing_window is None:
                db.add(
                    CoverageWindow(
                        company_id=company.id,
                        day_of_week=day,
                        start_time=time(9, 0),
                        end_time=time(18, 0),
                    )
                )

        ticket_seeds = [
            (1, "Customer cannot log in", "open", 1),
            (2, "Invoice needs correction", "in_progress", 2),
            (3, "Question about plan limits", "pending", None),
            (4, "Duplicate charge review", "resolved", 3),
            (5, "Old delivery request", "closed", None),
        ]
        now = datetime.now(dt_timezone.utc)
        for ticket_id, subject, ticket_status, agent_id in ticket_seeds:
            ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id))
            if ticket is None:
                ticket = Ticket(
                    id=ticket_id,
                    company_id=company.id,
                    subject=subject,
                    status=ticket_status,
                )
                db.add(ticket)
                db.flush()
            if agent_id is not None:
                existing_assignment = db.scalar(
                    select(Assignment).where(Assignment.ticket_id == ticket.id)
                )
                if existing_assignment is None:
                    assigned_at = now - timedelta(days=agent_id)
                    db.add(
                        Assignment(
                            ticket_id=ticket.id,
                            agent_id=agent_id,
                            assigned_at=assigned_at,
                            reason=f"Seeded example assignment for {subject}.",
                        )
                    )
                    agent = db.get(Agent, agent_id)
                    if agent is not None:
                        agent.last_assigned_at = assigned_at

        # Explicit demo IDs must not leave PostgreSQL's generated ID sequences behind.
        for table in ("companies", "agents", "availability_windows", "coverage_windows", "tickets", "assignments"):
            db.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1), true)"
                )
            )
        db.commit()
    print("Demo company and agents are ready (company ID 1).")


if __name__ == "__main__":
    seed()
