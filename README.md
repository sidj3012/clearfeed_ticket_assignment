# Ticket Assignment

An MVP for managing agent schedules and assigning support tickets fairly across timezones.

## Delivery phases

1. **Agent setup (implemented):** FastAPI/PostgreSQL foundation, demo seed data, company timezone, agent timezone and capacity, and recurring weekly availability.
2. **Ticket workflow:** Ticket creation and status updates, assignment decisions, workload counting, fairness, and clear no-assignment results.
3. **Coverage and reliability:** Coverage calculations and gap view, plus transaction and concurrency protection for assignment.

The UI uses a restrained white and slate palette with teal accents. It does not use purple or gradients.

## Phase 1 local setup

### Start PostgreSQL

From the repository root:

```sh
docker compose up -d db
```

### Start the API

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`; interactive API documentation is at `http://localhost:8000/docs`. The seed command creates the demo company with ID `1` and three agents. Startup creates the database tables if they do not exist.

To use a different database, set `DATABASE_URL` before starting the API. `backend/.env.example` shows the local default connection string.

### Start the UI

In another terminal:

```sh
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The UI uses company ID `1` from the seed data and the API at `http://localhost:8000`. Set `NEXT_PUBLIC_API_URL` when the API uses a different address.

## Phase 1 API

- `GET /health`
- `GET /api/companies/{company_id}`
- `PUT /api/companies/{company_id}?timezone=Asia%2FKolkata`
- `GET /api/companies/{company_id}/agents`
- `PUT /api/companies/{company_id}/agents/{agent_id}`
- `PUT /api/companies/{company_id}/agents/{agent_id}/availability`

Availability days use Monday `0` through Sunday `6`. A start time later than the end time represents an overnight window. Equal start and end times are rejected.
