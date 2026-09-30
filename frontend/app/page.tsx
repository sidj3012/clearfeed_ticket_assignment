"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const COMPANY_ID = 1;
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type WindowRow = { id?: number; day_of_week: number; start_time: string; end_time: string };
type Agent = {
  id: number;
  company_id: number;
  name: string;
  timezone: string;
  max_active_tickets: number;
  availability_windows: WindowRow[];
};
type Company = { id: number; name: string; timezone: string };
type Ticket = {
  id: number;
  subject: string;
  status: string;
  created_at: string;
  agent: { id: number; name: string } | null;
  assignment_reason: string | null;
};
type TicketResult = Ticket & {
  assigned: boolean;
  current_workload: number | null;
  reason_code: string | null;
  reason: string;
  available_agents: { id: number; name: string; active_ticket_count: number; max_active_tickets: number }[];
};
type AgentOverview = {
  id: number;
  name: string;
  timezone: string;
  max_active_tickets: number;
  active_ticket_count: number;
  is_available: boolean;
  availability_hours_utc: { day_of_week: number; start_time: string; end_time: string }[];
};
type CoverageWindow = { id?: number; day_of_week: number; start_time: string; end_time: string };
type CoverageSegment = { day_of_week: number; start_time: string; end_time: string; covered: boolean };
type CoverageSummary = {
  company_timezone: string;
  week_start: string;
  required_windows: CoverageWindow[];
  covered_periods: CoverageSegment[];
  gaps: CoverageSegment[];
};
const STATUSES = ["open", "in_progress", "pending", "resolved", "closed"];
const FALLBACK_TIMEZONES = ["UTC", "America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York", "America/Sao_Paulo", "Europe/London", "Europe/Paris", "Europe/Berlin", "Africa/Johannesburg", "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney", "Pacific/Auckland"];

function timezoneOptions(zones: string[], selected: string): string[] {
  return selected && !zones.includes(selected) ? [selected, ...zones] : zones;
}

function formatUtcTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

export default function HomePage() {
  const [company, setCompany] = useState<Company | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [drafts, setDrafts] = useState<Record<number, { timezone: string; capacity: number; windows: WindowRow[] }>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [creatingAgent, setCreatingAgent] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [newAgentTimezone, setNewAgentTimezone] = useState("UTC");
  const [newAgentCapacity, setNewAgentCapacity] = useState(5);
  const [newAgentWindows, setNewAgentWindows] = useState<WindowRow[]>([]);
  const [view, setView] = useState<"setup" | "agents" | "tickets" | "coverage">("setup");
  const [agentsOverview, setAgentsOverview] = useState<AgentOverview[]>([]);
  const [agentsOverviewLoading, setAgentsOverviewLoading] = useState(false);
  const [currentUtc, setCurrentUtc] = useState("");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [coverage, setCoverage] = useState<CoverageSummary | null>(null);
  const [coverageTimezone, setCoverageTimezone] = useState("UTC");
  const [coverageWindows, setCoverageWindows] = useState<CoverageWindow[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(false);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [savingCoverage, setSavingCoverage] = useState(false);
  const [ticketSubject, setTicketSubject] = useState("");
  const [creatingTicket, setCreatingTicket] = useState(false);
  const [ticketAction, setTicketAction] = useState<number | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error" | "info"; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [companyResponse, agentResponse] = await Promise.all([
        fetch(`${API_URL}/api/companies/${COMPANY_ID}`, { cache: "no-store" }),
        fetch(`${API_URL}/api/companies/${COMPANY_ID}/agents`, { cache: "no-store" }),
      ]);
      if (!companyResponse.ok || !agentResponse.ok) throw new Error("Could not load team settings. Is the API running?");
      const [companyData, agentData] = await Promise.all([companyResponse.json(), agentResponse.json()]);
      setCompany(companyData);
      setCoverageTimezone(companyData.timezone);
      setAgents(agentData);
      setDrafts(Object.fromEntries(agentData.map((agent: Agent) => [agent.id, {
        timezone: agent.timezone,
        capacity: agent.max_active_tickets,
        windows: agent.availability_windows.map((window) => ({ ...window, start_time: window.start_time.slice(0, 5), end_time: window.end_time.slice(0, 5) })),
      }])));
      setNotice(null);
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const updateClock = () => setCurrentUtc(`${new Date().toISOString().replace("T", " ").slice(0, 19)} UTC`);
    updateClock();
    const interval = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(interval);
  }, []);

  const loadAgentOverview = useCallback(async () => {
    setAgentsOverviewLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/agents/overview`, { cache: "no-store" });
      if (!response.ok) throw new Error(await apiError(response));
      setAgentsOverview(await response.json());
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setAgentsOverviewLoading(false);
    }
  }, []);

  useEffect(() => { if (view === "agents") void loadAgentOverview(); }, [view, loadAgentOverview]);

  const loadTickets = useCallback(async () => {
    setTicketsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/tickets`, { cache: "no-store" });
      if (!response.ok) throw new Error(await apiError(response));
      setTickets(await response.json());
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setTicketsLoading(false);
    }
  }, []);

  useEffect(() => { if (view === "tickets") void loadTickets(); }, [view, loadTickets]);

  const loadCoverage = useCallback(async () => {
    setCoverageLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/coverage`, { cache: "no-store" });
      if (!response.ok) throw new Error(await apiError(response));
      const data: CoverageSummary = await response.json();
      setCoverage(data);
      setCoverageTimezone(data.company_timezone);
      setCoverageWindows(data.required_windows.map((window) => ({
        ...window,
        start_time: window.start_time.slice(0, 5),
        end_time: window.end_time.slice(0, 5),
      })));
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setCoverageLoading(false);
    }
  }, []);

  useEffect(() => { if (view === "coverage") void loadCoverage(); }, [view, loadCoverage]);

  function updateDraft(agentId: number, update: Partial<{ timezone: string; capacity: number; windows: WindowRow[] }>) {
    setDrafts((current) => ({ ...current, [agentId]: { ...current[agentId], ...update } }));
  }

  async function saveAgent(agent: Agent) {
    const draft = drafts[agent.id];
    if (!draft) return;
    setSaving(agent.id);
    setNotice(null);
    try {
      const configResponse = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/agents/${agent.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timezone: draft.timezone, max_active_tickets: Number(draft.capacity) }),
      });
      if (!configResponse.ok) throw new Error(await apiError(configResponse));
      const scheduleResponse = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/agents/${agent.id}/availability`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft.windows.map(({ day_of_week, start_time, end_time }) => ({ day_of_week, start_time, end_time }))),
      });
      if (!scheduleResponse.ok) throw new Error(await apiError(scheduleResponse));
      setNotice({ kind: "success", text: `${agent.name}'s settings were saved.` });
      await load();
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setSaving(null);
    }
  }

  async function createAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatingAgent(true);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newAgentName.trim(),
          timezone: newAgentTimezone,
          max_active_tickets: Number(newAgentCapacity),
          availability_windows: newAgentWindows.map(({ day_of_week, start_time, end_time }) => ({
            day_of_week,
            start_time,
            end_time,
          })),
        }),
      });
      if (!response.ok) throw new Error(await apiError(response));
      const created: Agent = await response.json();
      setShowAgentForm(false);
      setNewAgentName("");
      setNewAgentTimezone(company?.timezone ?? "UTC");
      setNewAgentCapacity(5);
      setNewAgentWindows([]);
      await load();
      setNotice({ kind: "success", text: `${created.name} was added to the team.` });
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setCreatingAgent(false);
    }
  }

  async function saveCompanyTimezone(timezone: string) {
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}?timezone=${encodeURIComponent(timezone)}`, { method: "PUT" });
      if (!response.ok) throw new Error(await apiError(response));
      const updatedCompany: Company = await response.json();
      setCompany(updatedCompany);
      setCoverageTimezone(updatedCompany.timezone);
      setNotice({ kind: "success", text: "Company timezone saved." });
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    }
  }

  async function createTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const subject = ticketSubject.trim();
    if (!subject) return;
    setCreatingTicket(true);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/tickets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject }),
      });
      if (!response.ok) throw new Error(await apiError(response));
      const result: TicketResult = await response.json();
      setTicketSubject("");
      setNotice({
        kind: result.assigned ? "success" : "info",
        text: result.assigned
          ? `Ticket #${result.id} created and assigned to ${result.agent?.name}.`
          : `Ticket #${result.id} created but remains unassigned. ${result.reason}${capacitySummary(result.available_agents)}`,
      });
      await loadTickets();
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setCreatingTicket(false);
    }
  }

  async function retryTicket(ticket: Ticket) {
    setTicketAction(ticket.id);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/tickets/${ticket.id}/assign`, { method: "POST" });
      if (!response.ok) throw new Error(await apiError(response));
      const result: TicketResult = await response.json();
      setNotice({
        kind: result.assigned ? "success" : "info",
        text: result.assigned
          ? `Ticket #${result.id} assigned to ${result.agent?.name}.`
          : `Ticket #${result.id} remains unassigned. ${result.reason}${capacitySummary(result.available_agents)}`,
      });
      await loadTickets();
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setTicketAction(null);
    }
  }

  async function updateTicketStatus(ticket: Ticket, nextStatus: string) {
    setTicketAction(ticket.id);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/api/tickets/${ticket.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!response.ok) throw new Error(await apiError(response));
      setNotice({ kind: "success", text: `Ticket #${ticket.id} status updated.` });
      await loadTickets();
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setTicketAction(null);
    }
  }

  async function saveCoverage() {
    setSavingCoverage(true);
    setNotice(null);
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}/coverage`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          timezone: coverageTimezone,
          windows: coverageWindows.map(({ day_of_week, start_time, end_time }) => ({ day_of_week, start_time, end_time })),
        }),
      });
      if (!response.ok) throw new Error(await apiError(response));
      const data: CoverageSummary = await response.json();
      setCoverage(data);
      setCoverageWindows(data.required_windows.map((window) => ({
        ...window,
        start_time: window.start_time.slice(0, 5),
        end_time: window.end_time.slice(0, 5),
      })));
      setCompany((current) => current ? { ...current, timezone: data.company_timezone } : current);
      setNotice({ kind: "success", text: "Coverage settings saved." });
    } catch (error) {
      setNotice({ kind: "error", text: messageFromError(error) });
    } finally {
      setSavingCoverage(false);
    }
  }

  const coverageSegments = coverage
    ? [...coverage.covered_periods, ...coverage.gaps].sort((a, b) =>
      a.day_of_week - b.day_of_week || a.start_time.localeCompare(b.start_time))
    : [];

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Ticket Assignment home"><span className="brand-mark">T</span><span>Ticket Assignment</span></a>
        <span className="topbar-label">Team settings</span>
      </header>

      <div className="content" id="home">
        <div className="page-heading">
          <div>
            <p className="eyebrow">{view === "agents" ? "TEAM OVERVIEW" : "WORKSPACE"}</p>
            <h1>{view === "agents" ? "Agents" : company?.name ?? "Team settings"}</h1>
            <p className="subheading">{view === "agents" ? "Availability and active workload for your team." : "Manage schedules, tickets, and team coverage."}</p>
          </div>
          {view === "agents" && <div className="utc-clock"><span>Current time</span><strong>{currentUtc || "Loading UTC time…"}</strong></div>}
        </div>

        {notice && <div className={`notice ${notice.kind}`} role="status">{notice.text}</div>}

        <nav className="view-tabs" aria-label="Workspace sections">
          <button className={view === "setup" ? "active" : ""} onClick={() => setView("setup")}>Team setup</button>
          <button className={view === "agents" ? "active" : ""} onClick={() => setView("agents")}>Agents</button>
          <button className={view === "tickets" ? "active" : ""} onClick={() => setView("tickets")}>Tickets</button>
          <button className={view === "coverage" ? "active" : ""} onClick={() => setView("coverage")}>Coverage</button>
        </nav>

        {view === "setup" ? <>
        <section className="company-card" aria-labelledby="company-heading">
          <div className="section-copy">
            <p className="eyebrow">COMPANY</p>
            <h2 id="company-heading">Workspace timezone</h2>
            <p>Choose the timezone used for team coverage reporting.</p>
          </div>
          <div className="company-control">
            <label className="sr-only" htmlFor="company-timezone">Company timezone</label>
            <TimezoneSelect id="company-timezone" value={company?.timezone ?? "UTC"} onChange={(value) => { if (value !== company?.timezone) void saveCompanyTimezone(value); }} />
          </div>
        </section>

        <div className="section-heading">
          <div><h2>Agents</h2><p>Set each agent’s timezone, active ticket limit, and recurring hours.</p></div>
          <div className="section-heading-actions">
            {agents.length > 0 && <span className="count-pill">{agents.length} agents</span>}
            <button className="button primary" onClick={() => {
              setNewAgentTimezone(company?.timezone ?? "UTC");
              setShowAgentForm((current) => !current);
            }}>{showAgentForm ? "Cancel" : "+ Add agent"}</button>
          </div>
        </div>

        {showAgentForm && <section className="agent-card agent-create-card" aria-labelledby="add-agent-title">
          <div className="schedule-heading agent-create-heading">
            <div><h4 id="add-agent-title">Add an agent</h4><p>New agents start with no scheduled hours unless you add them here.</p></div>
          </div>
          <form className="agent-create-form" onSubmit={(event) => void createAgent(event)}>
            <div className="agent-fields">
              <label htmlFor="new-agent-name">Name
                <input id="new-agent-name" value={newAgentName} maxLength={160} onChange={(event) => setNewAgentName(event.target.value)} required />
              </label>
              <label htmlFor="new-agent-timezone">Timezone
                <TimezoneSelect id="new-agent-timezone" value={newAgentTimezone} onChange={setNewAgentTimezone} />
              </label>
              <label htmlFor="new-agent-capacity">Maximum active tickets
                <input id="new-agent-capacity" type="number" min="1" step="1" value={newAgentCapacity} onChange={(event) => setNewAgentCapacity(Number(event.target.value))} required />
              </label>
            </div>
            <div className="schedule-heading"><div><h4>Weekly availability</h4><p>Optional. Times use the selected agent timezone.</p></div>
              <button className="button secondary" type="button" onClick={() => setNewAgentWindows((windows) => [...windows, { day_of_week: 0, start_time: "09:00", end_time: "17:00" }])}>+ Add hours</button>
            </div>
            {newAgentWindows.length > 0 && <div className="window-list">
              {newAgentWindows.map((window, index) => <div className="window-row" key={`new-agent-${index}`}>
                <label className="sr-only" htmlFor={`new-agent-day-${index}`}>Day</label>
                <select id={`new-agent-day-${index}`} value={window.day_of_week} onChange={(event) => setNewAgentWindows((current) => current.map((item, i) => i === index ? { ...item, day_of_week: Number(event.target.value) } : item))}>{DAYS.map((day, value) => <option value={value} key={day}>{day}</option>)}</select>
                <label className="sr-only" htmlFor={`new-agent-start-${index}`}>Start time</label>
                <input id={`new-agent-start-${index}`} type="time" value={window.start_time} onChange={(event) => setNewAgentWindows((current) => current.map((item, i) => i === index ? { ...item, start_time: event.target.value } : item))} required />
                <span className="time-separator">to</span>
                <label className="sr-only" htmlFor={`new-agent-end-${index}`}>End time</label>
                <input id={`new-agent-end-${index}`} type="time" value={window.end_time} onChange={(event) => setNewAgentWindows((current) => current.map((item, i) => i === index ? { ...item, end_time: event.target.value } : item))} required />
                <button className="icon-button" type="button" title="Remove hours" aria-label={`Remove ${DAYS[window.day_of_week]} hours`} onClick={() => setNewAgentWindows((current) => current.filter((_, i) => i !== index))}>×</button>
              </div>)}
            </div>}
            <div className="agent-create-actions">
              <button className="button primary" type="submit" disabled={creatingAgent || !newAgentName.trim() || newAgentCapacity < 1}>{creatingAgent ? "Adding…" : "Add agent"}</button>
            </div>
          </form>
        </section>}

        {loading ? <div className="empty-state">Loading team settings…</div> : agents.length === 0 ? (
          <div className="empty-state">No agents are configured for this company.</div>
        ) : (
          <div className="agent-list">
            {agents.map((agent) => {
              const draft = drafts[agent.id];
              if (!draft) return null;
              return <section className="agent-card" key={agent.id}>
                <div className="agent-heading">
                  <div className="avatar" aria-hidden="true">{agent.name.split(" ").map((part) => part[0]).slice(0, 2).join("")}</div>
                  <div className="agent-name"><h3>{agent.name}</h3><span>Agent #{agent.id}</span></div>
                  <button className="button primary" onClick={() => void saveAgent(agent)} disabled={saving === agent.id}>
                    {saving === agent.id ? "Saving…" : "Save changes"}
                  </button>
                </div>

                <div className="agent-fields">
                  <label>Agent timezone
                    <TimezoneSelect value={draft.timezone} onChange={(value) => updateDraft(agent.id, { timezone: value })} />
                  </label>
                  <label>Maximum active tickets
                    <input type="number" min="1" step="1" value={draft.capacity} onChange={(event) => updateDraft(agent.id, { capacity: Number(event.target.value) })} />
                    <span className="field-hint">Positive whole number</span>
                  </label>
                </div>

                <div className="schedule-heading"><div><h4>Weekly availability</h4><p>Times are in this agent’s timezone. End earlier than start for overnight hours.</p></div>
                  <button className="button secondary" onClick={() => updateDraft(agent.id, { windows: [...draft.windows, { day_of_week: 0, start_time: "09:00", end_time: "17:00" }] })}>+ Add hours</button>
                </div>
                {draft.windows.length === 0 ? <p className="no-hours">No recurring hours added.</p> : <div className="window-list">
                  {draft.windows.map((window, index) => <div className="window-row" key={`${window.id ?? "new"}-${index}`}>
                    <label className="sr-only" htmlFor={`day-${agent.id}-${index}`}>Day</label>
                    <select id={`day-${agent.id}-${index}`} value={window.day_of_week} onChange={(event) => {
                      const windows = draft.windows.map((item, i) => i === index ? { ...item, day_of_week: Number(event.target.value) } : item);
                      updateDraft(agent.id, { windows });
                    }}>{DAYS.map((day, value) => <option value={value} key={day}>{day}</option>)}</select>
                    <label className="sr-only" htmlFor={`start-${agent.id}-${index}`}>Start time</label>
                    <input id={`start-${agent.id}-${index}`} type="time" value={window.start_time} onChange={(event) => updateWindow(agent.id, draft.windows, index, { start_time: event.target.value }, updateDraft)} />
                    <span className="time-separator">to</span>
                    <label className="sr-only" htmlFor={`end-${agent.id}-${index}`}>End time</label>
                    <input id={`end-${agent.id}-${index}`} type="time" value={window.end_time} onChange={(event) => updateWindow(agent.id, draft.windows, index, { end_time: event.target.value }, updateDraft)} />
                    <button className="icon-button" title="Remove hours" aria-label={`Remove ${DAYS[window.day_of_week]} hours`} onClick={() => updateDraft(agent.id, { windows: draft.windows.filter((_, i) => i !== index) })}>×</button>
                  </div>)}
                </div>}
              </section>;
            })}
          </div>
        )}
        <footer className="footer-note">Agent settings are applied when the assignment service evaluates a ticket.</footer>
        </> : view === "agents" ? <>
          {agentsOverviewLoading ? <div className="empty-state">Loading agent overview…</div> : agentsOverview.length === 0 ? (
            <div className="empty-state">No agents are configured for this company.</div>
          ) : <div className="agent-overview-list">
            {agentsOverview.map((agent) => <section className="agent-overview-card" key={agent.id}>
              <div className="agent-overview-heading">
                <div className="avatar" aria-hidden="true">{agent.name.split(" ").map((part) => part[0]).slice(0, 2).join("")}</div>
                <div className="agent-name"><h3>{agent.name}</h3><span>{agent.timezone}</span></div>
                <span className={`availability-pill ${agent.is_available ? "is-available" : "is-unavailable"}`}>{agent.is_available ? "Available" : "Not available"}</span>
              </div>
              <div className="agent-overview-stats">
                <div><span>Active tickets</span><strong>{agent.active_ticket_count}/{agent.max_active_tickets}</strong></div>
                <div className="utc-hours"><span>Availability hours · UTC this week</span>
                  {agent.availability_hours_utc.length === 0 ? <strong>No scheduled hours</strong> : <ul>
                    {agent.availability_hours_utc.map((window, index) => <li key={`${window.day_of_week}-${window.start_time}-${index}`}>{DAYS[window.day_of_week]} {window.start_time}–{window.end_time}</li>)}
                  </ul>}
                </div>
              </div>
            </section>)}
          </div>}
          <footer className="footer-note">Ticket counts include open, in-progress, and pending tickets. UTC hours show the current UTC week.</footer>
        </> : view === "tickets" ? <>
          <section className="ticket-create-card">
            <div><p className="eyebrow">TICKET QUEUE</p><h2>Create a ticket</h2><p>New tickets start open and are assigned automatically when an agent is eligible.</p></div>
            <form className="ticket-create-form" onSubmit={(event) => void createTicket(event)}>
              <label className="sr-only" htmlFor="ticket-subject">Ticket subject</label>
              <input id="ticket-subject" value={ticketSubject} maxLength={240} onChange={(event) => setTicketSubject(event.target.value)} placeholder="Briefly describe the customer’s issue" required />
              <button className="button primary" disabled={creatingTicket || !ticketSubject.trim()}>{creatingTicket ? "Creating…" : "Create ticket"}</button>
            </form>
          </section>

          <div className="section-heading tickets-heading"><div><h2>Tickets</h2><p>Update status or retry assignment for unassigned tickets.</p></div>
            {tickets.length > 0 && <span className="count-pill">{tickets.length} tickets</span>}
          </div>
          {ticketsLoading ? <div className="empty-state">Loading tickets…</div> : tickets.length === 0 ? (
            <div className="empty-state">No tickets yet. Create one to see assignment in action.</div>
          ) : <div className="ticket-list">
            {tickets.map((ticket) => <article className="ticket-card" key={ticket.id}>
              <div className="ticket-main">
                <div className="ticket-title-line"><h3>{ticket.subject}</h3><span className={`status-pill status-${ticket.status}`}>{ticket.status.replace("_", " ")}</span></div>
                <p className="ticket-meta">Ticket #{ticket.id} · Created {formatUtcTimestamp(ticket.created_at)}</p>
                <p className="ticket-assignee">{ticket.agent ? <>Assigned to <strong>{ticket.agent.name}</strong></> : <strong className="unassigned">Unassigned</strong>}</p>
                {ticket.assignment_reason && <p className="assignment-reason">{ticket.assignment_reason}</p>}
              </div>
              <div className="ticket-actions">
                {!ticket.agent && <button className="button secondary" onClick={() => void retryTicket(ticket)} disabled={ticketAction === ticket.id}>{ticketAction === ticket.id ? "Retrying…" : "Retry assignment"}</button>}
                <label className="sr-only" htmlFor={`status-${ticket.id}`}>Ticket status</label>
                <select id={`status-${ticket.id}`} value={ticket.status} disabled={ticketAction === ticket.id} onChange={(event) => void updateTicketStatus(ticket, event.target.value)}>
                  {STATUSES.map((status) => <option key={status} value={status}>{status.replace("_", " ")}</option>)}
                </select>
              </div>
            </article>)}
          </div>}
          <footer className="footer-note">Active tickets are open, in progress, or pending.</footer>
        </> : <>
          <section className="coverage-config">
            <div className="coverage-config-heading">
              <div><p className="eyebrow">WEEKLY REQUIREMENTS</p><h2>Required team coverage</h2><p>Set the periods when at least one agent should be available.</p></div>
              <button className="button primary" onClick={() => void saveCoverage()} disabled={savingCoverage}>{savingCoverage ? "Saving…" : "Save coverage"}</button>
            </div>
            <label className="coverage-timezone">Company timezone
              <TimezoneSelect value={coverageTimezone} onChange={setCoverageTimezone} />
            </label>
            <div className="coverage-windows-heading"><h3>Required hours</h3><button className="button secondary" onClick={() => setCoverageWindows((current) => [...current, { day_of_week: 0, start_time: "09:00", end_time: "17:00" }])}>+ Add hours</button></div>
            {coverageWindows.length === 0 ? <p className="no-hours">No required coverage periods. Add hours to see coverage and gaps.</p> : <div className="window-list coverage-window-list">
              {coverageWindows.map((window, index) => <div className="window-row" key={`${window.id ?? "new"}-${index}`}>
                <label className="sr-only" htmlFor={`coverage-day-${index}`}>Coverage day</label>
                <select id={`coverage-day-${index}`} value={window.day_of_week} onChange={(event) => setCoverageWindows((current) => current.map((item, i) => i === index ? { ...item, day_of_week: Number(event.target.value) } : item))}>{DAYS.map((day, value) => <option value={value} key={day}>{day}</option>)}</select>
                <label className="sr-only" htmlFor={`coverage-start-${index}`}>Coverage start time</label>
                <input id={`coverage-start-${index}`} type="time" value={window.start_time} onChange={(event) => setCoverageWindows((current) => current.map((item, i) => i === index ? { ...item, start_time: event.target.value } : item))} />
                <span className="time-separator">to</span>
                <label className="sr-only" htmlFor={`coverage-end-${index}`}>Coverage end time</label>
                <input id={`coverage-end-${index}`} type="time" value={window.end_time} onChange={(event) => setCoverageWindows((current) => current.map((item, i) => i === index ? { ...item, end_time: event.target.value } : item))} />
                <button className="icon-button" title="Remove required hours" aria-label={`Remove ${DAYS[window.day_of_week]} coverage`} onClick={() => setCoverageWindows((current) => current.filter((_, i) => i !== index))}>×</button>
              </div>)}
            </div>}
          </section>

          <section className="coverage-results">
            <div className="section-heading"><div><h2>Team coverage</h2><p>Combined agent availability compared with required hours.</p></div>
              {coverage && <span className="count-pill">Week of {coverage.week_start}</span>}
            </div>
            {coverageLoading ? <div className="empty-state">Calculating weekly coverage…</div> : !coverage || coverage.required_windows.length === 0 ? (
              <div className="empty-state">Configure required hours to view covered periods and gaps.</div>
            ) : coverageSegments.length === 0 ? (
              <div className="empty-state">The selected week has no clock minutes in its configured coverage periods.</div>
            ) : <>
              <div className="coverage-timezone-note"><span>Company timezone</span><strong>{coverage.company_timezone}</strong></div>
              <div className="coverage-summary-cards">
                <div><span className="summary-value">{coverage.covered_periods.length}</span><span>covered periods</span></div>
                <div className={coverage.gaps.length ? "has-gaps" : ""}><span className="summary-value">{coverage.gaps.length}</span><span>coverage gaps</span></div>
              </div>
              <div className="coverage-segments" role="table" aria-label={`Team coverage in ${coverage.company_timezone}`}>
                <div className="coverage-segment coverage-segment-header" role="row">
                  <span role="columnheader">Day</span>
                  <span role="columnheader">Time</span>
                  <span role="columnheader">Status</span>
                </div>
                {coverageSegments.map((segment, index) => <div className="coverage-segment" key={`${segment.day_of_week}-${segment.start_time}-${index}`}>
                  <span className="coverage-day">{DAYS[segment.day_of_week]}</span>
                  <span className="coverage-time">{segment.start_time} – {segment.end_time}</span>
                  <span className={`coverage-state ${segment.covered ? "covered" : "gap"}`}>{segment.covered ? "Covered" : "Gap"}</span>
                </div>)}
              </div>
            </>}
            <footer className="footer-note">The summary uses the current company-local week and recurring schedules.</footer>
          </section>
        </>}
      </div>
    </main>
  );
}

function TimezoneSelect({ id, value, onChange }: { id?: string; value: string; onChange: (timezone: string) => void }) {
  const [zones, setZones] = useState(FALLBACK_TIMEZONES);

  useEffect(() => {
    if (typeof Intl.supportedValuesOf !== "function") return;
    setZones(["UTC", ...Intl.supportedValuesOf("timeZone").filter((zone) => zone !== "UTC")]);
  }, []);

  return <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
    {timezoneOptions(zones, value).map((timezone) => <option key={timezone} value={timezone}>{timezone}</option>)}
  </select>;
}

function capacitySummary(agents: TicketResult["available_agents"]): string {
  if (!agents.length) return "";
  const summary = agents.map((agent) => `${agent.name} (${agent.active_ticket_count}/${agent.max_active_tickets})`).join(", ");
  return ` Available agents and active tickets: ${summary}.`;
}

function updateWindow(
  agentId: number,
  windows: WindowRow[],
  index: number,
  changes: Partial<WindowRow>,
  update: (id: number, value: Partial<{ timezone: string; capacity: number; windows: WindowRow[] }>) => void,
) {
  update(agentId, { windows: windows.map((item, i) => i === index ? { ...item, ...changes } : item) });
}

async function apiError(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(" ");
  return "The request could not be saved.";
}
