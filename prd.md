# Product Requirements Document

## 1. Overview

The goal of this project is to automate support ticket assignment for teams where agents work different schedules and in different timezones.

Today, a team lead may have to keep checking the ticket queue and manually decide who should get each new ticket. That works for a small team, but it becomes difficult as the team grows. Tickets can stay unassigned when the lead is offline, the lead spends time on repetitive work, and some agents can end up with much more work than others.

This product should handle that decision automatically. When a new ticket comes in, the system should look at the agents who are working at that time, check their current workload, and assign the ticket to a suitable person.

The team lead should also be able to manage schedules and see when the team does not have enough coverage.

## 2. Who is this for?

The main user is a support team lead or manager of any company.

They need to:

- Set and update when agents are available.
- See which timezone each agent works in.
- Set a reasonable workload limit for each agent.
- See periods where the team has no coverage.
- Understand why a ticket was assigned to a particular agent.



## 3. What problem are we solving?

There are three main problems:

### Manual assignment

The team lead has to watch the queue and decide where every ticket should go.

### Uneven workload

Without a consistent rule, one agent can receive many tickets while another agent has very little work.

### Coverage gaps

The team may think it has enough coverage, but there can still be periods where nobody is scheduled to work.

The product should reduce the manual work while making the assignment decision predictable and easy to understand.

## 4. Goals

The product should support the following:

1. A team lead/ someone in company can configure recurring weekly availability for each agent.
2. Each agent can have their own timezone.
3. Each agent can have a maximum number of active tickets.
4. The system can show periods where the team's required coverage is not met.
5. A ticket can be assigned through an API.
6. The assignment only considers agents who are currently available.
7. Agents who are already at their workload limit are not considered.
8. Tickets are spread reasonably fairly between eligible agents.
9. The API explains why the selected agent was chosen, or why nobody was eligible.



### Recurring Availability

- Availability is configured as recurring weekly schedules for each agent.
- Each schedule has a day of week, start time, end time, and the agent's timezone.
- Start and end times are interpreted in the agent's own timezone.
- A schedule where `start_time < end_time` stays within the same calendar day.
- A schedule where `start_time > end_time` crosses midnight into the following calendar day. For example, Monday 10:00 PM–2:00 AM means Monday 10:00 PM through Tuesday 2:00 AM.
- The schedule is associated with its starting day. Therefore, Monday 10:00 PM–2:00 AM is a Monday schedule even though part of it falls on Tuesday.
- When checking availability, the system converts the current timestamp to the agent's timezone and checks whether it falls within the applicable schedule, including overnight schedules.
- Weekend schedules follow the same rule. For example, Saturday 10:00 PM–2:00 AM covers Saturday night through Sunday 2:00 AM.



### Coverage Configuration

The team lead can configure the company's recurring required coverage from the UI.

The lead specifies:

- Company timezone
- Days of the week requiring coverage
- Start and end time for each required coverage window

Required coverage is defined in the company's timezone. Agent availability is defined in each agent's own timezone.

The system compares the required coverage windows with the combined availability of all agents and highlights periods where no agent is scheduled to be available.



## 5. What does "fair" mean?

I would keep fairness simple and predictable for the first version.

Among agents who are currently available and still have capacity, the system will prefer:

1. The agent with the fewest active tickets.
2. If there is a tie, the agent who received a ticket least recently.

For example:

- Agent A has 2 active tickets.
- Agent B has 4 active tickets.
- Agent C has 2 active tickets.

A and C are the candidates because they have the lower workload. If C was assigned work more recently than A, A gets the next ticket.

## 6. Workload limits

Each agent will have a maximum number of active tickets.

An active ticket is a ticket whose status is not finished. For the MVP, statuses such as `open`, `in_progress`, and `pending` count as active, while `resolved` and `closed` do not. 

Ticket status will be read from `tickets` table in PostgreSQL, which is the source of truth for assignment decisions.  
A ticket counts toward capacity while its status is `open`, `in_progress`, or `pending`. Once its status changes to `resolved` or `closed` in our database, it stops counting toward capacity for subsequent assignment requests.

If an agent has reached their limit, they should not receive another ticket even if they are currently working.

For example, if an agent's limit is 5 and they already have 5 active tickets, they are not eligible for a new assignment.

## 7. Assignment behavior

When the assignment API is called for a ticket, the system should:

1. Check that the company and ticket exist.
2. Check whether the ticket has already been assigned.
3. Find agents who belong to that company.
4. Check which agents are currently available.
5. Remove agents who are already at their workload limit.
6. Choose the fairest remaining agent.
7. Save the assignment.
8. Return the selected agent and a reason for the decision.

If there is nobody eligible, the API should return a clear "not assigned" result instead of treating this as a server error.

Possible reasons include:

- No agents are currently available.
- All available agents are already at capacity.
- There are no agents configured for the company.



## 8. UI requirements



### Availability management

The lead/employee should be able to:

- See the list of agents.
- See each agent's timezone.
- Set the maximum active-ticket count.
- Add or edit recurring weekly availability.



### Coverage view

There should also be a simple way to see when team coverage is missing.

The team lead should be able to compare the required coverage with the combined schedules of the agents.

For example, if the team needs coverage from 9 AM to 6 PM but nobody is scheduled from 2 PM to 3 PM, the UI should make that gap obvious.

## 9. API requirement

The main API should accept a company and ticket and decide who should receive it.

Example:

`POST /api/companies/{company_id}/tickets/{ticket_id}/assign`

A successful response should contain:

- Whether the ticket was assigned.
- The assigned agent.
- The agent's current workload.
- The assignment time.
- The reason.

When nobody is eligible, the response should contain:

- `assigned: false`
- A reason code.
- A human-readable reason.



## 10. Idempotency and concurrent requests

A ticket should not accidentally be assigned to two people if the same request is sent more than once.

The system should return the existing assignment when the ticket has already been assigned.

There is also a concurrency concern. Two new tickets may arrive at almost the same time, and both requests may try to assign work to the same agent.

The assignment decision and the corresponding database update should therefore happen inside a transaction so that workload limits are not incorrectly exceeded because of two requests reading the same old state.

## 11. Out of scope

To keep the trial focused, I would not build the following:

- Login or authentication.
- Roles and permissions.
- Billing or account management.
- Holiday calendars.
- One-off schedule overrides.
- PagerDuty, Opsgenie, or other third-party integrations.
- Skills-based routing.
- Ticket priority rules.



## 12. Assumptions

A few things need to be simplified for the MVP:

- Availability repeats every week.
- While assigning, I assume that each ticket would take same amount of time.
- Any agent can solve any ticket irrespective of domain.
- Each agent has one configured timezone.
- Existing ticket data is enough to calculate active workload.
- PostgreSQL will be the source of truth for assignments and availability.

