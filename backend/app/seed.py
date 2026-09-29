from datetime import time

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import Agent, AvailabilityWindow, Company


def seed() -> None:
    Base.metadata.create_all(bind=engine)
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
        db.commit()
    print("Demo company and agents are ready (company ID 1).")


if __name__ == "__main__":
    seed()
