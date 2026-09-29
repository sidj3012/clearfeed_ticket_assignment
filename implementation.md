# Implementation Plan

## 1. Approach

- Frontend: Next.js + TypeScript
- Backend: FastAPI + Python
- Database: PostgreSQL
- Tests: Pytest

The UI will be used by the team lead or any member of company to manage agent availability, agent workload limits, company timezone, create new ticket, change ticket status,  and required team coverage.

The backend will expose the assignment API and will be the source of truth for availability and assignment decisions.

---

## 2. Data Model

### companies

- `id`
- `name`
- `timezone`

`timezone` is the company's timezone, for example `Asia/Kolkata`.

The company timezone is used for required coverage configuration and coverage reporting.

### agents

- `id`
- `company_id`
- `name`
- `timezone`
- `max_active_tickets`
- `last_assigned_at`



### availability_windows

- `id`
- `agent_id`
- `day_of_week`
- `start_time`
- `end_time`

These are recurring weekly schedules.

The day of week is the day on which the shift starts.

### coverage_windows

- `id`
- `company_id`
- `day_of_week`
- `start_time`
- `end_time`

These are the recurring periods during which the company expects at least one agent to be available.

Coverage windows use the company's timezone.

### tickets

- `id`
- `company_id`
- `status`
- `subject`
- `created_at`

Active statuses:

- `open`
- `in_progress`
- `pending`

Inactive statuses:

- `resolved`
- `closed`

Ticket can be created from UI.  
Ticket status can be updated from UI.

### assignments

- `id`
- `ticket_id`
- `agent_id`
- `assigned_at`
- `reason`

There should be a unique constraint on `ticket_id` so one ticket cannot have two assignments.

---



## 3. Recurring Availability

Each agent can have one or more recurring weekly availability windows.

The schedule is always interpreted in the agent's own timezone.

For example:

```text
Agent timezone: Asia/Kolkata
Schedule: Monday 09:00 - 17:00
```

means the agent is available from 9 AM to 5 PM on Monday in India time.

### Same-day schedule

If:

```text
start_time < end_time
```

the schedule stays on the same calendar day.

Example:

```text
Monday 09:00 - 17:00
```

means:

```text
Monday 09:00 -> Monday 17:00
```



### Overnight schedule

If:

```text
start_time > end_time
```

the schedule crosses midnight into the following calendar day.

Example:

```text
Monday 22:00 - 02:00
```

means:

```text
Monday 22:00
        |
        | overnight
        v
Tuesday 02:00
```

So this schedule contributes:

```text
Monday:  22:00 - 24:00
Tuesday: 00:00 - 02:00
```

The schedule is still stored as a Monday schedule because Monday is its starting day.

Another example:

```text
Saturday 22:00 - 02:00
```

means:

```text
Saturday 22:00 -> Sunday 02:00
```

So it contributes availability to early Sunday.

---



## 4. Availability Check

The backend captures the current instant once as a timezone-aware UTC timestamp.

For each agent, that timestamp is converted to the agent's configured timezone.

The resulting local day and local time are used to check the recurring schedule.

This matters because the same instant can fall on different days for different agents.

Example:

```text
Current instant: 10:00 UTC
```

For an agent in `Asia/Kolkata`:

```text
Local time: Tuesday 15:30
```

For an agent in `America/New_York`:

```text
Local time: Tuesday 06:00
```

Each agent is checked using their own local date and time.

### Checking a normal schedule

For a schedule such as:

```text
09:00 - 17:00
```

the agent is available when:

```text
09:00 <= current_local_time < 17:00
```

This means:

- exactly 9:00 AM -> available
- 2:00 PM -> available
- exactly 5:00 PM -> not available



### Checking an overnight schedule

For a schedule such as:

```text
22:00 - 02:00
```

the shift is split conceptually across two days.

For the starting day (Monday), check:

```text
current_local_time >= 22:00
```

For the following day (Tuesday), check the previous day's overnight schedule:

```text
current_local_time < 02:00
```

Example:

```text
Monday 23:30 -> available
Tuesday 01:30 -> available
Tuesday 03:00 -> not available
```

The implementation must therefore check both:

1. schedules that start on the current local day
2. overnight schedules that started on the previous local day

This prevents a Monday 10 PM-2 AM shift from incorrectly disappearing at midnight.

---



## 5. Required Coverage

The team lead configures recurring required coverage through the UI.

The lead sets:

- company timezone
- day of week
- coverage start time
- coverage end time

The company timezone is the timezone used for all coverage requirements.

For example:

```text
Company timezone: Asia/Kolkata
Required coverage:
Monday 09:00 - 18:00
```

means the company wants at least one agent scheduled between 9 AM and 6 PM India time.

### Agent schedules vs company coverage

Agent availability remains in each agent's own timezone.

When calculating coverage, agent schedules are converted to the company's timezone and compared against the required coverage windows.

### Overnight coverage

Coverage windows use the same overnight rule as agent schedules.

For example:

```text
Company coverage:
Saturday 22:00 - 02:00
```

means:

```text
Saturday 22:00 -> Sunday 02:00
```

An overnight agent schedule can therefore satisfy part of the following day's coverage requirement.

Example:

```text
Agent availability:
Saturday 22:00 - 02:00

Required coverage:
Sunday 00:00 - 06:00
```

The agent provides coverage from:

```text
Sunday 00:00 - 02:00
```

and the remaining period is a coverage gap.

### Coverage result

The UI should show:

- required coverage
- periods currently covered by at least one agent
- uncovered periods/gaps

The coverage feature is for planning and visibility. It does not directly assign tickets.

---



## 6. Assignment Logic

When:

```text
POST /api/companies/{company_id}/tickets/{ticket_id}/assign
```

is called:

### Step 1: Validate the company and ticket

Make sure:

- company exists
- ticket exists
- ticket belongs to the company

If not, return an appropriate not-found response.

### Step 2: Check existing assignment

Before creating a new assignment, check whether the ticket is already assigned.

If it is already assigned, return the existing assignment instead of assigning it again.

This makes repeated requests for the same ticket safe.

### Step 3: Find agents in the company

Only agents belonging to the requested company are considered.

If there are no agents:

```text
reason_code = NO_AGENTS_FOUND
```



### Step 4: Check current availability

For every company agent, check whether they are currently available using the agent's own timezone and the recurring schedule rules described above.

If nobody is currently available:

```text
reason_code = NO_AVAILABLE_AGENT
```



### Step 5: Check workload capacity

For each currently available agent, count their active tickets.

An active ticket has one of these statuses:

```text
open
in_progress
pending
```

If:

```text
active_ticket_count >= max_active_tickets
```

the agent is not eligible.

If agents are available but every available agent is at capacity:

```text
reason_code = ALL_AGENTS_AT_CAPACITY
```



### Step 6: Choose the fairest eligible agent

Among eligible agents:

1. choose the agent with the fewest active tickets
2. if tied, choose the agent who was assigned a ticket least recently

`last_assigned_at = NULL` is treated as least recently assigned, so an agent who has never received a ticket can win a tie.

Example:

```text
Agent A -> 2 active tickets
Agent B -> 4 active tickets
Agent C -> 2 active tickets
```

A and C are tied.

If C was assigned more recently than A:

```text
A -> selected
C -> not selected
```



### Step 7: Save the assignment

Create the assignment record and update the selected agent's `last_assigned_at` in the same database transaction.

The response includes the selected agent, current workload, assignment time, and a human-readable reason.

Example:

```json
{
  "assigned": true,
  "agent": {
    "id": "agent_123",
    "name": "Rahul"
  },
  "current_workload": 2,
  "assigned_at": "2026-09-29T12:30:00Z",
  "reason": "Rahul was selected because he is currently available, has the lowest active workload, and has not been assigned as recently as the other tied candidate."
}
```

---



## 7. No-Assignment Responses

The API should return a specific reason whenever possible.

### No agents configured

```json
{
  "assigned": false,
  "reason_code": "NO_AGENTS_FOUND",
  "reason": "No agents are configured for this company."
}
```



### Nobody is currently working

```json
{
  "assigned": false,
  "reason_code": "NO_AVAILABLE_AGENT",
  "reason": "No agent is currently scheduled to be available."
}
```



### Everyone available is at capacity

```json
{
  "assigned": false,
  "reason_code": "ALL_AGENTS_AT_CAPACITY",
  "reason": "All currently available agents have reached their active ticket limit."
}
```

`NO_ELIGIBLE_AGENT` can remain as a generic fallback for unexpected cases where no agent satisfies all assignment conditions but a more specific reason is not available.

---



## 8. Ticket Status and External Sync

Ticket status can be updated through UI.

If a ticket changes from:

```text
open / in_progress / pending
```

to:

```text
resolved / closed
```

 it stops counting toward capacity for subsequent assignment requests.

External ticketing-system integrations are out of scope for the MVP.

If an external source system is introduced later, an API integration or synchronization mechanism will be required to keep the local ticket status up to date or ticket status can be updated manually through UI. Otherwise, the workload calculation could use stale status data.

**Ticket Management (MVP)**

The UI will include a lightweight Tickets section for viewing existing tickets and changing their status. This is provided to make workload and assignment behavior demonstrable without an external ticketing integration.

Supported statuses are `open`, `in_progress`, `pending`, `resolved`, and `closed`.

Status changes will be persisted through `PATCH /api/tickets/{ticket_id}`. The local PostgreSQL `tickets.status` value is the source of truth for workload calculations. `open`, `in_progress`, and `pending` count toward an agent's active workload, while `resolved` and `closed` do not.

---



## 9. Idempotency and Concurrency

The same ticket must never be assigned to two agents.

To support this:

- put a unique database constraint on `assignments.ticket_id`
- check for an existing assignment before creating one
- create the assignment inside a database transaction

For concurrent assignment requests, the backend should use row-level locking on the candidate agent records while making the final selection.

The transaction should:

1. lock the candidate agents
2. recalculate their current active-ticket counts
3. select the fairest eligible agent
4. create the assignment
5. update `last_assigned_at`
6. commit

This prevents two concurrent requests from making a selection using the same stale workload state.

If two requests arrive for the same ticket at the same time, the unique `ticket_id` constraint ensures that only one assignment can be created. The losing request should then return the assignment that already exists.

---



## 10. API Endpoints



### Assignment

```text
POST /api/companies/{company_id}/tickets/{ticket_id}/assign
```

Assigns the ticket or returns a clear no-assignment reason.

This endpoint also retries assignment for a previously unassigned ticket. Repeated requests return the existing assignment.


### Ticket management

```text
POST /api/companies/{company_id}/tickets
GET /api/companies/{company_id}/tickets
PATCH /api/tickets/{ticket_id}
```

Ticket creation starts with `open` status and immediately attempts assignment using the shared assignment service. If no agent is eligible, the ticket is still created and the response explains why it remains unassigned. The list endpoint returns tickets with their assigned agent, when present. The status endpoint accepts `open`, `in_progress`, `pending`, `resolved`, or `closed`.

### Agent list

```text
GET /api/companies/{company_id}/agents
```

Returns agents, timezone, capacity, and availability configuration needed by the UI.

### Agent availability

```text
PUT /api/companies/{company_id}/agents/{agent_id}/availability
```

Creates or replaces an agent's recurring availability windows.

The API validates:

- valid day of week
- valid time format
- `start_time != end_time`
- valid IANA timezone for the agent



### Agent Configuration

The UI will allow the team lead to view and update each agent's configuration, including their maximum active-ticket capacity.

Agent capacity will be persisted through:

```http
PUT /api/companies/{company_id}/agents/{agent_id}

```

Example request:

```json
{
  "max_active_tickets": 10
}
```

The endpoint will validate that `max_active_tickets` is a positive integer and update the corresponding agent record.

The agent configuration UI will:

- Display the agent's name.
- Display the agent's timezone.
- Display the current maximum active-ticket limit.
- Allow the team lead to update the maximum active-ticket limit.
- Save the updated limit through the agent update endpoint.



### Coverage configuration

```text
PUT /api/companies/{company_id}/coverage
```

Creates or replaces the company's recurring required coverage windows.

The API validates:

- valid company timezone
- valid day of week
- valid time format
- `start_time != end_time`



### Coverage view

```text
GET /api/companies/{company_id}/coverage
```

Returns the configured required coverage and calculated covered/gap periods for the UI.

---



## 11. UI

The UI will have two main areas.

### Availability

The team lead can:

- see the list of agents
- see each agent's timezone
- set the maximum active tickets
- add/edit recurring weekly availability
- see overnight schedules clearly, for example `Mon 10 PM - Tue 2 AM`



### Coverage

The team lead can:

- set the company timezone
- configure required recurring coverage
- view combined team availability
- see coverage gaps inside required coverage windows

A simple weekly table/calendar view is enough for the MVP.

The UI will include a lightweight Tickets section for viewing existing tickets and changing their status.

---



### Ticket Creation and Automatic Assignment

The MVP will provide a lightweight ticket creation flow so the complete assignment workflow can be exercised from the UI without manually inserting tickets into the database.

The UI will provide a `+ Create Ticket` action in the Tickets section.

The creation form will contain:

- Ticket subject

New tickets will always start with `open` status. The system will automatically attempt to assign the ticket immediately after creation.

#### Create Ticket API

```http
POST /api/companies/{company_id}/tickets
```

Example request:

```json
{
  "subject": "Customer cannot login"
}
```

The backend will create the ticket with:

```text
status = open
company_id = path parameter
created_at = current timestamp
```

It will then invoke the same assignment service used by the explicit assignment API.

If an eligible agent is found, the ticket is assigned automatically:

```json
{
  "id": 104,
  "company_id": 1,
  "subject": "Customer cannot login",
  "status": "open",
  "assigned": true,
  "agent": {
    "id": 12,
    "name": "Rahul"
  },
  "reason": "Assigned to Rahul because he has the lowest active workload among currently available agents."
}
```

If no eligible agent is available, the ticket remains unassigned rather than failing to create:

```json
{
  "id": 104,
  "company_id": 1,
  "subject": "Customer cannot login",
  "status": "open",
  "assigned": false,
  "reason_code": "ALL_AGENTS_AT_CAPACITY",
  "reason": "All currently available agents have reached their active ticket limit."
}
```

The API will validate that the company exists before creating the ticket.

#### Assignment Logic Reuse

Automatic assignment and the explicit assignment API will use the same assignment service to avoid duplicate assignment logic.

```text
Create Ticket ──→ Assignment Service
                         ↑
Explicit Assign API ────┘

```



#### Ticket UI

The Tickets section will display:

- Ticket ID
- Subject
- Current status
- Assigned agent, if any
- Status change action
- Assignment/retry action for unassigned tickets

After creation, the UI will immediately show whether the ticket was assigned.

Example:

```text
Ticket #104 created and assigned to Rahul.

```

or:

```text
Ticket #104 created but remains unassigned.

Reason:
All currently available agents have reached their active ticket limit.

```



#### Ticket Lifecycle

The supported statuses are:

```text
open
in_progress
pending
resolved
closed
```

`open`, `in_progress`, and `pending` count toward active workload. `resolved` and `closed` do not.

A typical flow is:

```text
Create Ticket
      ↓
Open + automatic assignment
      ↓
In Progress
      ↓
Pending (if required)
      ↓
Resolved / Closed
      ↓
No longer counted toward active workload
```

Status changes are handled separately through the ticket status update flow.

### Demo Data / Seed Process

Since company and agent creation are out of scope for the MVP, the application will provide a database seed script containing the records required to exercise the complete flow locally.

The seed data will include:

- One demo company with a configured company timezone.
- Multiple agents belonging to the company.
- Different agent timezones.
- Recurring availability schedules, including at least one overnight schedule.
- Different `max_active_tickets` values.
- A recurring company coverage requirement.
- Multiple tickets with a mix of `open`, `in_progress`, `pending`, `resolved`, and `closed` statuses.
- Existing assignments where useful for demonstrating workload and fairness.

The seed script will be safe to run against a fresh local database and will create the required records in the correct dependency order:

```text
Company
   ↓
Agents
   ↓
Availability
   ↓
Coverage configuration
   ↓
Tickets
   ↓
Existing assignments

```

The exact seeded IDs will be documented or made visible through the UI/API so the assignment flow can be exercised without manually creating records.

---



## 12. Validation and Edge Cases

The implementation should handle:

- company not found
- ticket not found
- ticket belongs to another company
- no agents configured
- agents exist but none are currently available
- all currently available agents are at capacity
- ticket already assigned
- invalid IANA timezone
- invalid day of week
- invalid time format
- `start_time == end_time`
- overnight schedules
- previous-day overnight availability
- overnight coverage
- weekend schedules crossing into the next day
- agents in different timezones
- timezone conversion that changes the local day
- concurrent assignment requests
- status changes from active to resolved/closed
- zero configured coverage requirements

---



## 13. Tests



### Availability

Test:

- normal same-day schedule
- exactly at shift start
- exactly at shift end
- before shift
- after shift
- overnight schedule
- time during the overnight portion
- time after the overnight shift
- previous-day overnight schedule
- different agent timezones
- timezone conversion that changes the local date
- invalid `start_time == end_time`



### Coverage

Test:

- complete coverage
- coverage gaps
- multiple agents combining to provide coverage
- overnight agent availability contributing to the next day
- overnight coverage windows
- weekend overnight schedules
- company timezone conversion
- multiple coverage windows on a day



### Assignment

Test:

- assigns an available agent
- excludes unavailable agents
- excludes agents at capacity
- chooses the lowest active workload
- uses least recently assigned as the tie-breaker
- handles an agent with no `last_assigned_at`
- returns `NO_AGENTS_FOUND`
- returns `NO_AVAILABLE_AGENT`
- returns `ALL_AGENTS_AT_CAPACITY`
- returns the existing assignment for an already assigned ticket
- prevents duplicate assignment under concurrent requests


### Ticket Creation

Test:

- creates a ticket for the company in the request path
- persists the submitted subject and generated `created_at` timestamp
- creates every new ticket with `open` status
- returns not found when the requested company does not exist


### Automatic Assignment on Creation

Test:

- invokes the shared assignment service after creating the ticket
- assigns the fairest eligible agent immediately when one is available
- returns the created ticket, assigned agent, assignment reason, and current workload
- keeps the created ticket when no agent is eligible and returns `assigned: false`
- returns the appropriate no-assignment reason when there are no agents, no available agents, or all available agents are at capacity


### Unassigned Tickets and Retry

Test:

- leaves a newly created ticket unassigned when no agent is eligible
- allows an unassigned ticket to be retried through the assignment endpoint
- assigns the ticket on retry when an agent has since become eligible
- keeps the ticket unassigned and returns the current reason when no agent is eligible on retry
- returns the existing assignment on repeated retries after the ticket has been assigned
- does not create more than one assignment when retries arrive concurrently



### Workload

Test:

- `open` counts as active
- `in_progress` counts as active
- `pending` counts as active
- `resolved` does not count
- `closed` does not count
- changing a ticket to `resolved` frees capacity for later assignment decisions

---



## 15. Out of Scope

The implementation will not include:

- authentication
- roles and permissions
- billing
- account management
- holiday calendars
- one-off schedule overrides
- external ticketing-system integrations
- skills-based routing
- ticket priority rules
- ticket duration or overtime prediction
- mobile-specific UI

The MVP assumes:

- recurring weekly schedules are sufficient
- each ticket takes roughly the same amount of work/time
- any agent can handle any ticket
- ticket status is not changed externally
- each agent has one timezone
- PostgreSQL is the source of truth for tickets, schedules, and assignments
