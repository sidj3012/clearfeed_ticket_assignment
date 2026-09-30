import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Agent, Assignment, AvailabilityWindow, Company, Ticket


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL to run PostgreSQL locking coverage.")
def test_concurrent_retries_do_not_exceed_agent_capacity(monkeypatch):
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_size=8, max_overflow=4, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.main.engine", engine)
    with sessions() as session:
        company = Company(name="Concurrency test", timezone="UTC")
        session.add(company)
        session.flush()
        company_id = company.id
        agent = Agent(
            company_id=company_id,
            name="Single-slot agent",
            timezone="UTC",
            max_active_tickets=1,
        )
        session.add(agent)
        session.flush()
        agent_id = agent.id
        first = Ticket(company_id=company_id, subject="Concurrent ticket one", status="open")
        second = Ticket(company_id=company_id, subject="Concurrent ticket two", status="open")
        session.add_all([first, second])
        session.flush()
        first_id, second_id = first.id, second.id
        session.commit()

    # Both requests are started with a free agent and race to claim the final slot.
    with sessions() as session:
        session.add(
            AvailabilityWindow(
                agent_id=agent_id,
                day_of_week=datetime.now(timezone.utc).weekday(),
                start_time=time(0, 0),
                end_time=time(23, 59, 59),
            )
        )
        session.commit()

    try:
        with TestClient(app) as client:
            def retry(ticket_id):
                return client.post(f"/api/companies/{company_id}/tickets/{ticket_id}/assign")

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(retry, [first_id, second_id]))
            assert all(result.status_code == 200 for result in results)
            assert sum(result.json()["assigned"] for result in results) == 1

        with sessions() as session:
            assert session.scalar(select(func.count(Assignment.id)).join(Ticket).where(Ticket.company_id == company_id)) == 1
    finally:
        app.dependency_overrides.clear()
        with sessions() as session:
            company = session.get(Company, company_id)
            if company is not None:
                session.delete(company)
                session.commit()
        engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL to run PostgreSQL locking coverage.")
def test_concurrent_retries_for_same_ticket_create_only_one_assignment(monkeypatch):
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_size=8, max_overflow=4, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.main.engine", engine)
    with sessions() as session:
        company = Company(name="Concurrent retry test", timezone="UTC")
        session.add(company)
        session.flush()
        company_id = company.id
        agent = Agent(
            company_id=company_id,
            name="Available agent",
            timezone="UTC",
            max_active_tickets=5,
        )
        session.add(agent)
        session.flush()
        agent_id = agent.id
        ticket = Ticket(company_id=company_id, subject="Repeated concurrent retry", status="open")
        session.add(ticket)
        session.flush()
        ticket_id = ticket.id
        session.add(AvailabilityWindow(
            agent_id=agent_id,
            day_of_week=datetime.now(timezone.utc).weekday(),
            start_time=time(0, 0),
            end_time=time(23, 59, 59),
        ))
        session.commit()

    try:
        with TestClient(app) as client:
            def retry():
                return client.post(f"/api/companies/{company_id}/tickets/{ticket_id}/assign")

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _index: retry(), range(2)))

            assert all(result.status_code == 200 for result in results)
            assert all(result.json()["assigned"] is True for result in results)
            assert {result.json()["agent"]["id"] for result in results} == {agent_id}

        with sessions() as session:
            assignment_count = session.scalar(
                select(func.count(Assignment.id)).where(Assignment.ticket_id == ticket_id)
            )
            assert assignment_count == 1
    finally:
        app.dependency_overrides.clear()
        with sessions() as session:
            company = session.get(Company, company_id)
            if company is not None:
                session.delete(company)
                session.commit()
        engine.dispose()
