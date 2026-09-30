from datetime import datetime, time, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import assignment
from app import coverage as coverage_module
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
    monkeypatch.setattr(coverage_module, "utc_now", lambda: FIXED_NOW)
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


def set_agent_windows(testing_sessions, agent_id, windows):
    with testing_sessions() as session:
        session.query(AvailabilityWindow).filter(AvailabilityWindow.agent_id == agent_id).delete()
        session.add_all([
            AvailabilityWindow(
                agent_id=agent_id,
                day_of_week=day,
                start_time=time.fromisoformat(start),
                end_time=time.fromisoformat(end),
            )
            for day, start, end in windows
        ])
        session.commit()


def test_create_agent_persists_configuration_and_availability(api):
    client, testing_sessions = api

    response = client.post("/api/companies/1/agents", json={
        "name": "  Riley Chen  ",
        "timezone": "America/Los_Angeles",
        "max_active_tickets": 4,
        "availability_windows": [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"},
            {"day_of_week": 2, "start_time": "10:00", "end_time": "18:00"},
        ],
    })

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Riley Chen"
    assert created["company_id"] == 1
    assert created["timezone"] == "America/Los_Angeles"
    assert created["max_active_tickets"] == 4
    assert len(created["availability_windows"]) == 2
    assert created["availability_windows"][0]["start_time"].startswith("09:00")
    listed = client.get("/api/companies/1/agents")
    assert any(agent["id"] == created["id"] for agent in listed.json())
    with testing_sessions() as session:
        stored_agent = session.get(Agent, created["id"])
        assert stored_agent is not None
        assert stored_agent.name == "Riley Chen"
        assert len(stored_agent.availability_windows) == 2


def test_create_agent_defaults_capacity_and_availability(api):
    client, _ = api

    response = client.post("/api/companies/1/agents", json={"name": "Morgan", "timezone": "UTC"})

    assert response.status_code == 201
    assert response.json()["max_active_tickets"] == 5
    assert response.json()["availability_windows"] == []


def test_create_agent_validates_company_and_fields(api):
    client, _ = api
    payload = {"name": "Casey", "timezone": "UTC", "max_active_tickets": 3}

    missing_company = client.post("/api/companies/55/agents", json=payload)
    blank_name = client.post("/api/companies/1/agents", json={**payload, "name": "   "})
    bad_timezone = client.post("/api/companies/1/agents", json={**payload, "timezone": "Not/A_Zone"})
    bad_capacity = client.post("/api/companies/1/agents", json={**payload, "max_active_tickets": 0})
    bad_schedule = client.post("/api/companies/1/agents", json={
        **payload,
        "availability_windows": [{"day_of_week": 0, "start_time": "09:00", "end_time": "09:00"}],
    })

    assert missing_company.status_code == 404
    assert blank_name.status_code == 422
    assert bad_timezone.status_code == 422
    assert bad_capacity.status_code == 422
    assert bad_schedule.status_code == 422


def test_create_ticket_assigns_available_agent(api, monkeypatch):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)
    assign_calls = []
    original_assign = main_module.assign_ticket

    def track_assignment(db, ticket):
        assign_calls.append(ticket.id)
        return original_assign(db, ticket)

    monkeypatch.setattr(main_module, "assign_ticket", track_assignment)

    response = client.post("/api/companies/1/tickets", json={"subject": "Customer cannot log in"})

    assert response.status_code == 201
    data = response.json()
    assert data["subject"] == "Customer cannot log in"
    assert data["status"] == "open"
    assert data["created_at"]
    assert data["assigned"] is True
    assert data["agent"]["id"] == agent_id
    assert data["current_workload"] == 1
    assert data["assigned_at"] is not None
    assert data["reason"]
    assert assign_calls == [data["id"]]
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

    still_unassigned = client.post(f"/api/companies/1/tickets/{created.json()['id']}/assign")
    assert still_unassigned.status_code == 200
    assert still_unassigned.json()["assigned"] is False
    assert still_unassigned.json()["reason_code"] == "NO_AVAILABLE_AGENT"

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


def test_ticket_creation_uses_company_id_from_request_path(api):
    client, testing_sessions = api
    with testing_sessions() as session:
        company = Company(name="Second company", timezone="UTC")
        session.add(company)
        session.flush()
        agent = Agent(company_id=company.id, name="Company two agent", timezone="UTC", max_active_tickets=5)
        session.add(agent)
        session.flush()
        agent_id = agent.id
        session.add(AvailabilityWindow(
            agent_id=agent.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0),
        ))
        company_id = company.id
        session.commit()

    response = client.post(f"/api/companies/{company_id}/tickets", json={"subject": "Company two request"})

    assert response.status_code == 201
    assert response.json()["company_id"] == company_id
    assert response.json()["agent"]["id"] == agent_id


def test_retry_returns_not_found_for_missing_or_other_company_ticket(api):
    client, testing_sessions = api
    with testing_sessions() as session:
        company = Company(name="Second company", timezone="UTC")
        session.add(company)
        session.flush()
        ticket = Ticket(company_id=company.id, subject="Private ticket", status="open")
        session.add(ticket)
        session.flush()
        ticket_id = ticket.id
        session.commit()

    missing = client.post("/api/companies/1/tickets/999/assign")
    wrong_company = client.post(f"/api/companies/1/tickets/{ticket_id}/assign")

    assert missing.status_code == 404
    assert wrong_company.status_code == 404


def test_assignment_retry_is_idempotent(api):
    client, testing_sessions = api
    add_agent(testing_sessions)

    created = client.post("/api/companies/1/tickets", json={"subject": "Shipping delay"})
    ticket_id = created.json()["id"]
    retried = client.post(f"/api/companies/1/tickets/{ticket_id}/assign")

    assert retried.status_code == 200
    assert retried.json()["assigned"] is True
    assert retried.json()["agent"] == created.json()["agent"]
    assigned_at_values = [
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in (retried.json()["assigned_at"], created.json()["assigned_at"])
    ]
    assigned_at_values = [
        value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        for value in assigned_at_values
    ]
    assert assigned_at_values[0] == assigned_at_values[1]
    assert retried.json()["reason"] == created.json()["reason"]
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


def test_active_workload_counts_only_open_in_progress_and_pending(api):
    _, testing_sessions = api
    agent_id = add_agent(testing_sessions)
    statuses = ["open", "in_progress", "pending", "resolved", "closed"]
    with testing_sessions() as session:
        for index, ticket_status in enumerate(statuses):
            ticket = Ticket(company_id=1, subject=f"Workload status {index}", status=ticket_status)
            session.add(ticket)
            session.flush()
            session.add(Assignment(
                ticket_id=ticket.id,
                agent_id=agent_id,
                assigned_at=FIXED_NOW,
                reason="Workload status test",
            ))
        session.flush()

        assert assignment.active_workload(session, agent_id) == 3


def test_validation_rejects_invalid_timezone_day_time_and_equal_schedule_times(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)

    invalid_company_timezone = client.put("/api/companies/1?timezone=Not/A_Timezone")
    invalid_agent_timezone = client.put(
        f"/api/companies/1/agents/{agent_id}",
        json={"timezone": "Not/A_Timezone", "max_active_tickets": 5},
    )
    invalid_day = client.put(
        f"/api/companies/1/agents/{agent_id}/availability",
        json=[{"day_of_week": 7, "start_time": "09:00", "end_time": "17:00"}],
    )
    invalid_time = client.put(
        f"/api/companies/1/agents/{agent_id}/availability",
        json=[{"day_of_week": 0, "start_time": "not-a-time", "end_time": "17:00"}],
    )
    equal_times = client.put(
        f"/api/companies/1/agents/{agent_id}/availability",
        json=[{"day_of_week": 0, "start_time": "09:00", "end_time": "09:00"}],
    )

    assert invalid_company_timezone.status_code == 422
    assert invalid_agent_timezone.status_code == 422
    assert invalid_day.status_code == 422
    assert invalid_time.status_code == 422
    assert equal_times.status_code == 422


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
    assert response.json()["available_agents"] == [{
        "id": agent_id,
        "name": "Alex",
        "active_ticket_count": 1,
        "max_active_tickets": 1,
    }]


def test_assignment_excludes_unavailable_and_at_capacity_agents(api):
    client, testing_sessions = api
    unavailable_id = add_agent(testing_sessions, available=False, name="Unavailable")
    full_id = add_agent(testing_sessions, capacity=1, name="At capacity")
    eligible_id = add_agent(testing_sessions, capacity=5, name="Eligible")
    with testing_sessions() as session:
        existing = Ticket(company_id=1, subject="Existing active work", status="open")
        session.add(existing)
        session.flush()
        session.add(Assignment(ticket_id=existing.id, agent_id=full_id, assigned_at=FIXED_NOW, reason="Existing"))
        session.commit()

    response = client.post("/api/companies/1/tickets", json={"subject": "Route to eligible agent"})

    assert response.status_code == 201
    assert response.json()["assigned"] is True
    assert response.json()["agent"]["id"] == eligible_id
    assert response.json()["agent"]["id"] not in {unavailable_id, full_id}


def test_assignment_chooses_agent_with_lowest_active_workload(api):
    client, testing_sessions = api
    higher_workload_id = add_agent(testing_sessions, name="Higher workload")
    lower_workload_id = add_agent(testing_sessions, name="Lower workload")
    unavailable_id = add_agent(testing_sessions, available=False, name="Unavailable but idle")
    with testing_sessions() as session:
        for agent_id, ticket_count in ((higher_workload_id, 2), (lower_workload_id, 1)):
            for index in range(ticket_count):
                ticket = Ticket(company_id=1, subject=f"Existing {agent_id}-{index}", status="open")
                session.add(ticket)
                session.flush()
                session.add(Assignment(
                    ticket_id=ticket.id,
                    agent_id=agent_id,
                    assigned_at=FIXED_NOW,
                    reason="Existing work",
                ))
        session.commit()

    response = client.post("/api/companies/1/tickets", json={"subject": "Fair workload"})

    assert response.status_code == 201
    assert response.json()["agent"]["id"] == lower_workload_id
    assert response.json()["agent"]["id"] != unavailable_id


def test_assignment_handles_agents_without_last_assignment_timestamp(api):
    client, testing_sessions = api
    first_id = add_agent(testing_sessions, name="First idle agent")
    second_id = add_agent(testing_sessions, name="Second idle agent")

    response = client.post("/api/companies/1/tickets", json={"subject": "No assignment history"})

    assert response.status_code == 201
    assert response.json()["agent"]["id"] == min(first_id, second_id)


def test_agent_overview_reports_workload_live_availability_and_utc_hours(api, monkeypatch):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions, capacity=5, name="Asha Patel")
    set_agent_windows(testing_sessions, agent_id, [(0, "17:00", "20:00")])
    with testing_sessions() as session:
        session.get(Agent, agent_id).timezone = "Asia/Kolkata"
        session.commit()
    monkeypatch.setattr(main_module, "utc_now", lambda: FIXED_NOW)

    created = client.post("/api/companies/1/tickets", json={"subject": "India shift issue"})
    response = client.get("/api/companies/1/agents/overview")

    assert created.status_code == 201
    overview = response.json()[0]
    assert overview["id"] == agent_id
    assert overview["active_ticket_count"] == 1
    assert overview["max_active_tickets"] == 5
    assert overview["is_available"] is True
    assert overview["availability_hours_utc"] == [
        {"day_of_week": 0, "start_time": "11:30", "end_time": "14:30"}
    ]


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
        session.get(Agent, first_agent_id).last_assigned_at = datetime(2026, 9, 28, 11, 0, tzinfo=timezone.utc)
        session.get(Agent, second_agent_id).last_assigned_at = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
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


def test_coverage_reports_complete_coverage(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)
    set_agent_windows(testing_sessions, agent_id, [(0, "09:00", "17:00")])

    response = client.put("/api/companies/1/coverage", json={
        "timezone": "UTC",
        "windows": [{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}],
    })

    assert response.status_code == 200
    assert response.json()["gaps"] == []
    assert response.json()["covered_periods"] == [
        {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00", "covered": True}
    ]


def test_coverage_marks_uncovered_periods_as_gaps(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)
    set_agent_windows(testing_sessions, agent_id, [(0, "09:00", "12:00")])

    response = client.put("/api/companies/1/coverage", json={
        "timezone": "UTC",
        "windows": [{"day_of_week": 0, "start_time": "09:00", "end_time": "13:00"}],
    })

    data = response.json()
    assert data["covered_periods"] == [
        {"day_of_week": 0, "start_time": "09:00", "end_time": "12:00", "covered": True}
    ]
    assert data["gaps"] == [
        {"day_of_week": 0, "start_time": "12:00", "end_time": "13:00", "covered": False}
    ]


def test_multiple_agents_can_combine_to_cover_a_window(api):
    client, testing_sessions = api
    first = add_agent(testing_sessions, name="Morning Agent")
    second = add_agent(testing_sessions, name="Afternoon Agent")
    set_agent_windows(testing_sessions, first, [(0, "09:00", "12:00")])
    set_agent_windows(testing_sessions, second, [(0, "12:00", "15:00")])

    response = client.put("/api/companies/1/coverage", json={
        "timezone": "UTC",
        "windows": [{"day_of_week": 0, "start_time": "09:00", "end_time": "15:00"}],
    })

    assert response.json()["gaps"] == []
    assert response.json()["covered_periods"][0]["start_time"] == "09:00"
    assert response.json()["covered_periods"][0]["end_time"] == "15:00"


def test_overnight_agent_availability_covers_the_following_day(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)
    set_agent_windows(testing_sessions, agent_id, [(0, "22:00", "02:00")])

    response = client.put("/api/companies/1/coverage", json={
        "timezone": "UTC",
        "windows": [{"day_of_week": 1, "start_time": "00:00", "end_time": "06:00"}],
    })

    data = response.json()
    assert data["covered_periods"] == [
        {"day_of_week": 1, "start_time": "00:00", "end_time": "02:00", "covered": True}
    ]
    assert data["gaps"] == [
        {"day_of_week": 1, "start_time": "02:00", "end_time": "06:00", "covered": False}
    ]


def test_overnight_coverage_window_is_split_at_midnight(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)
    set_agent_windows(testing_sessions, agent_id, [(0, "22:00", "02:00")])

    response = client.put("/api/companies/1/coverage", json={
        "timezone": "UTC",
        "windows": [{"day_of_week": 0, "start_time": "22:00", "end_time": "02:00"}],
    })

    assert response.json()["gaps"] == []
    assert [(p["day_of_week"], p["start_time"], p["end_time"]) for p in response.json()["covered_periods"]] == [
        (0, "22:00", "24:00"), (1, "00:00", "02:00")
    ]


def test_weekend_overnight_schedule_covers_sunday_and_reports_remaining_gap(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)
    set_agent_windows(testing_sessions, agent_id, [(5, "22:00", "02:00")])

    response = client.put("/api/companies/1/coverage", json={
        "timezone": "UTC",
        "windows": [{"day_of_week": 6, "start_time": "00:00", "end_time": "06:00"}],
    })

    data = response.json()
    assert data["covered_periods"][0]["end_time"] == "02:00"
    assert data["gaps"][0]["start_time"] == "02:00"
    assert data["gaps"][0]["end_time"] == "06:00"


def test_coverage_converts_agent_timezones_into_company_timezone(api):
    client, testing_sessions = api
    with testing_sessions() as session:
        agent = Agent(company_id=1, name="New York Agent", timezone="America/New_York", max_active_tickets=5)
        session.add(agent)
        session.flush()
        session.add(AvailabilityWindow(agent_id=agent.id, day_of_week=0, start_time=time(9), end_time=time(17)))
        session.commit()

    response = client.put("/api/companies/1/coverage", json={
        "timezone": "Asia/Kolkata",
        "windows": [
            {"day_of_week": 0, "start_time": "18:30", "end_time": "00:00"},
            {"day_of_week": 1, "start_time": "00:00", "end_time": "02:30"},
        ],
    })

    assert response.status_code == 200
    assert response.json()["company_timezone"] == "Asia/Kolkata"
    assert response.json()["gaps"] == []


def test_multiple_coverage_windows_on_one_day_are_kept_separate(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions)
    set_agent_windows(testing_sessions, agent_id, [(0, "09:00", "12:00"), (0, "14:00", "17:00")])

    response = client.put("/api/companies/1/coverage", json={
        "timezone": "UTC",
        "windows": [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "12:00"},
            {"day_of_week": 0, "start_time": "14:00", "end_time": "17:00"},
        ],
    })

    assert response.json()["gaps"] == []
    assert len(response.json()["covered_periods"]) == 2


def test_no_configured_coverage_returns_empty_summary(api):
    client, _ = api

    response = client.get("/api/companies/1/coverage")

    assert response.status_code == 200
    assert response.json()["required_windows"] == []
    assert response.json()["covered_periods"] == []
    assert response.json()["gaps"] == []


def test_complete_team_to_ticket_and_coverage_flow(api):
    client, testing_sessions = api
    agent_id = add_agent(testing_sessions, available=False, capacity=4)

    configured = client.put(
        f"/api/companies/1/agents/{agent_id}",
        json={"timezone": "UTC", "max_active_tickets": 1},
    )
    availability = client.put(
        f"/api/companies/1/agents/{agent_id}/availability",
        json=[{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}],
    )
    coverage = client.put(
        "/api/companies/1/coverage",
        json={
            "timezone": "UTC",
            "windows": [{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}],
        },
    )
    first_ticket = client.post("/api/companies/1/tickets", json={"subject": "First customer request"})
    resolved = client.patch(f"/api/tickets/{first_ticket.json()['id']}", json={"status": "resolved"})
    second_ticket = client.post("/api/companies/1/tickets", json={"subject": "Next customer request"})
    ticket_list = client.get("/api/companies/1/tickets")
    coverage_view = client.get("/api/companies/1/coverage")

    assert configured.status_code == 200
    assert availability.status_code == 200
    assert coverage.status_code == 200
    assert first_ticket.status_code == 201 and first_ticket.json()["assigned"] is True
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    assert second_ticket.status_code == 201 and second_ticket.json()["assigned"] is True
    assert len(ticket_list.json()) == 2
    assert coverage_view.status_code == 200 and coverage_view.json()["gaps"] == []
