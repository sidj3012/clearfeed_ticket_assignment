# Ticket Assignment

An MVP for managing agent schedules and assigning support tickets fairly across timezones.

### Setup

### Start PostgreSQL

From the repository root:

```sh
docker compose up -d db
```

PostgreSQL is published on host port `5433`.

### Start the API

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`; interactive API documentation is at `http://localhost:8000/docs`. The seed command creates the demo company with ID `1`, three agents, example schedules and coverage, and five sample tickets with several statuses and assignments. Startup creates the database tables if they do not exist.

To use a different database, set `DATABASE_URL` before starting the API. `backend/.env.example` shows the local default connection string (`localhost:5433`).

### Start the UI

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The UI uses company ID `1` from the seed data and the API at `http://localhost:8000`. Set `NEXT_PUBLIC_API_URL` when the API uses a different address.

## API

- `GET /health`
- `GET /api/companies/{company_id}`
- `PUT /api/companies/{company_id}?timezone=Asia%2FKolkata`
- `GET /api/companies/{company_id}/agents`
- `POST /api/companies/{company_id}/agents`
- `GET /api/companies/{company_id}/agents/overview`
- `PUT /api/companies/{company_id}/agents/{agent_id}`
- `PUT /api/companies/{company_id}/agents/{agent_id}/availability`
- `POST /api/companies/{company_id}/tickets`
- `GET /api/companies/{company_id}/tickets`
- `POST /api/companies/{company_id}/tickets/{ticket_id}/assign`
- `PATCH /api/tickets/{ticket_id}`
- `GET /api/companies/{company_id}/coverage`
- `PUT /api/companies/{company_id}/coverage`



### Add an agent

Create an agent for a company either through UI or:

```http
POST /api/companies/{company_id}/agents
Content-Type: application/json
```

Request body (`availability_windows` is optional; it defaults to an empty list, and `max_active_tickets` defaults to `5`):

```json
{
  "name": "Riley Chen",
  "timezone": "America/Los_Angeles",
  "max_active_tickets": 4,
  "availability_windows": [
    { "day_of_week": 0, "start_time": "09:00", "end_time": "17:00" },
    { "day_of_week": 2, "start_time": "10:00", "end_time": "18:00" }
  ]
}
```

The response is `201 Created` and returns the created agent, including its generated ID and saved availability windows. Unknown companies return `404`; invalid names, timezones, limits, or schedules return `422`.

### Assignment API

Ticket can be created through UI. Ticket creation triggers the following API:

```http
POST /api/companies/{company_id}/tickets
Content-Type: application/json
```

Request body:

```json
{
  "subject": "Customer cannot log in"
}
```

The service creates the ticket with `open` status and attempts assignment. The response is `201 Created` and includes the ticket, assignment result, and reason. For example, when an agent is assigned:

```json
{
  "id": 42,
  "company_id": 1,
  "subject": "Customer cannot log in",
  "status": "open",
  "created_at": "2026-09-30T10:00:00Z",
  "assigned": true,
  "agent": { "id": 3, "name": "Sam Taylor" },
  "current_workload": 3,
  "assigned_at": "2026-09-30T10:00:00Z",
  "reason_code": null,
  "reason": "Sam Taylor was selected because they are currently available and have the lowest active workload (2).",
  "available_agents": []
}
```

To retry assignment for an existing unassigned ticket, send a bodyless request:

```http
POST /api/companies/{company_id}/tickets/{ticket_id}/assign
```

This returns `200 OK` with the same response shape. If no available agent can accept the ticket, the ticket remains unassigned. For example, when all currently available agents are at capacity:

```json
{
  "id": 42,
  "company_id": 1,
  "subject": "Customer cannot log in",
  "status": "open",
  "created_at": "2026-09-30T10:00:00Z",
  "assigned": false,
  "agent": null,
  "current_workload": null,
  "assigned_at": null,
  "reason_code": "ALL_AGENTS_AT_CAPACITY",
  "reason": "All currently available agents have reached their active ticket limit.",
  "available_agents": [
    { "id": 3, "name": "Sam Taylor", "active_ticket_count": 5, "max_active_tickets": 5 }
  ]
}
```

`available_agents` is empty for other unassigned outcomes, such as no configured agents or no agents currently scheduled to work.

Availability days use Monday `0` through Sunday `6`. A start time later than the end time represents an overnight window. Equal start and end times are rejected.

Coverage is summarized for the current company-local week at one-minute precision. During a daylight-saving fall-back, repeated local clock minutes are combined into a single weekly time range.

## Automated tests

From the repository root, create and activate the backend environment and install its dependencies if you have not already:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the unit and API workflow tests (SQLite in-memory; PostgreSQL is not required for these tests):

```sh
pytest
```

To run the PostgreSQL row-lock concurrency tests, start the Compose database from the repository root (`docker compose up -d db`), return to `backend/`, then run the full suite with `TEST_DATABASE_URL`:

```sh
TEST_DATABASE_URL='postgresql+psycopg://ticket_assignment:ticket_assignment@localhost:5433/ticket_assignment' pytest
```

The PostgreSQL tests verify that competing tickets cannot exceed an agent's capacity and that simultaneous retries of the same ticket create only one assignment. They are skipped when `TEST_DATABASE_URL` is unset and clean up their test data afterward.

All test cases listed in `implementation.md` are automated. None of those planned cases are manual-only. 

## What to build next

1. Priority Tickets - If an urgent/priority ticket comes and if no agent is available, then also assign it and send a notification to agent that there is a priority ticket which needs to be resolved first.
2. Ticket escalation - If an agent is unable to resolve the ticket, the ticket can be escalated to senior agent or any other agent.
3. Ticket time consideration - Different tickets can consume different amount of time, so it should be considered during ticket assignement.
4. Domain/Skill based ticket assignment
5. Specific timezone holiday and leave consideration.
6. Automatically retry assignment when it has failed previously  with FCFS or priority queue.
7. Apart from agent's timezone, all timezone in UI should be displayed in company's timezone for better visualization.
8. With current MVP, agent might have to do overtime - For example, let's say agent logout time is 6 pm and 5 tickets are assigned at 5:30 pm, then agent might have to do overtime. To solve this we can change the availability formula to 'start_time <= current_time < (end_time - number_of_tickets_assigned * average_time_for_one_ticket)

