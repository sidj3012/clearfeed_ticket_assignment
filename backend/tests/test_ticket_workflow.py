from datetime import datetime, time, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import assignment
from app.database import Base, get_db
from app import main as main_module
from app.main import app
from app.models import Agent, Assignment, AvailabilityWindow, Company, Ticket


FIXED_NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def api(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main_module, "engine", engine)
    testing_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with testing_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(assignment, "utc_now", lambda: FIXED_NOW)
    with testing_sessions() as session:
        session.add(Company(id=1, name="Demo Support", timezone="UTC"))
        session.commit()

    with TestClient(app) as client:
        yield client, testing_sessions
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_agent(testing_sessions, *, available=True, capacity=5, name="Alex"):
    with testing_sessions() as session:
        agent = Agent(
            company_id=1,
            name=name,
            timezone="UTC",
            max_active_tickets=capacity,
        )
        session.add(agent)
        session.flush()
        if available:
            session.add(
                AvailabilityWindow(
                    agent_id=agent.id,
                    day_of_week=0,
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                )
            )
        agent_id = agent.id
        session.commit()
        return agent_id


def test_create_ticket_assigns_available_agent(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)

    response = client.post("/api/companies/1/tickets", json={"subject": "Customer cannot log in"})

    assert response.status_code == 201
    data = response.json()
    assert data["subject"] == "Customer cannot log in"
    assert data["status"] == "open"
    assert data["assigned"] is True
    assert data["agent"]["id"] == agent_id
    assert data["current_workload"] == 1
    assert data["assigned_at"] is not None
    assert data["reason"]
    with testing_sessions() as session:
        assert session.scalar(select(func.count(Ticket.id))) == 1
        assert session.scalar(select(func.count(Assignment.id))) == 1


def test_unassigned_ticket_can_be_retried_when_agent_becomes_available(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions, available=False)

    created = client.post("/api/companies/1/tickets", json={"subject": "Billing question"})
    assert created.status_code == 201
    assert created.json()["assigned"] is False
    assert created.json()["reason_code"] == "NO_AVAILABLE_AGENT"

    with testing_sessions() as session:
        session.add(
            AvailabilityWindow(
                agent_id=agent_id,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(17, 0),
            )
        )
        session.commit()

    ticket_id = created.json()["id"]
    retried = client.post(f"/api/companies/1/tickets/{ticket_id}/assign")
    assert retried.status_code == 200
    assert retried.json()["assigned"] is True
    assert retried.json()["agent"]["id"] == agent_id


def test_create_keeps_ticket_when_company_has_no_agents(api):
    client, testing_sessions = api

    response = client.post("/api/companies/1/tickets", json={"subject": "Need a refund"})

    assert response.status_code == 201
    assert response.json()["assigned"] is False
    assert response.json()["reason_code"] == "NO_AGENTS_FOUND"
    with testing_sessions() as session:
        ticket = session.scalar(select(Ticket))
        assert ticket is not None
        assert ticket.status == "open"
        assert session.scalar(select(func.count(Assignment.id))) == 0


def test_assignment_retry_is_idempotent(api):
    client, testing_sessions = api
    add_agent(testing_sessions)

    created = client.post("/api/companies/1/tickets", json={"subject": "Shipping delay"})
    ticket_id = created.json()["id"]
    retried = client.post(f"/api/companies/1/tickets/{ticket_id}/assign")

    assert retried.status_code == 200
    assert retried.json()["assigned"] is True
    with testing_sessions() as session:
        assert session.scalar(select(func.count(Assignment.id))) == 1


def test_ticket_status_update_is_validated_and_persisted(api):
    client, testing_sessions = api
    add_agent(testing_sessions)
    ticket = client.post("/api/companies/1/tickets", json={"subject": "Update my order"}).json()

    updated = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "resolved"})
    invalid = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "waiting"})

    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"
    assert invalid.status_code == 422
    with testing_sessions() as session:
        assert session.get(Ticket, ticket["id"]).status == "resolved"


def test_create_returns_capacity_reason_when_all_available_agents_are_full(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions, capacity=1)
    with testing_sessions() as session:
        existing_ticket = Ticket(company_id=1, subject="Existing work", status="open")
        session.add(existing_ticket)
        session.flush()
        session.add(
            Assignment(
                ticket_id=existing_ticket.id,
                agent_id=agent_id,
                assigned_at=FIXED_NOW,
                reason="Existing assignment",
            )
        )
        session.commit()

    response = client.post("/api/companies/1/tickets", json={"subject": "Another request"})

    assert response.status_code == 201
    assert response.json()["assigned"] is False
    assert response.json()["reason_code"] == "ALL_AGENTS_AT_CAPACITY"


def test_assignment_breaks_equal_workload_by_least_recent_assignment(api):
    client, testing_sessions = api
    first_agent_id = add_agent(testing_sessions, name="Recently Assigned")
    second_agent_id = add_agent(testing_sessions, name="Least Recently Assigned")
    with testing_sessions() as session:
        recent_ticket = Ticket(company_id=1, subject="Recent completed work", status="resolved")
        older_ticket = Ticket(company_id=1, subject="Older completed work", status="closed")
        session.add_all([recent_ticket, older_ticket])
        session.flush()
        session.add_all([
            Assignment(ticket_id=recent_ticket.id, agent_id=first_agent_id, assigned_at=datetime(2026, 9, 28, 11, 0, tzinfo=timezone.utc), reason="Earlier test assignment"),
            Assignment(ticket_id=older_ticket.id, agent_id=second_agent_id, assigned_at=datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc), reason="Older test assignment"),
        ])
        session.commit()

    response = client.post("/api/companies/1/tickets", json={"subject": "Fair assignment"})

    assert response.status_code == 201
    assert response.json()["agent"]["id"] == second_agent_id


def test_resolving_ticket_frees_capacity_for_a_new_assignment(api):
    client, testing_sessions = api
    add_agent(testing_sessions, capacity=1)
    first_ticket = client.post("/api/companies/1/tickets", json={"subject": "First request"}).json()

    resolved = client.patch(f"/api/tickets/{first_ticket['id']}", json={"status": "resolved"})
    second_ticket = client.post("/api/companies/1/tickets", json={"subject": "Second request"})

    assert resolved.status_code == 200
    assert second_ticket.status_code == 201
    assert second_ticket.json()["assigned"] is True


def test_ticket_creation_rejects_unknown_company_and_blank_subject(api):
    client, _ = api

    missing_company = client.post("/api/companies/44/tickets", json={"subject": "Help"})
    blank_subject = client.post("/api/companies/1/tickets", json={"subject": "   "})

    assert missing_company.status_code == 404
    assert blank_subject.status_code == 422
