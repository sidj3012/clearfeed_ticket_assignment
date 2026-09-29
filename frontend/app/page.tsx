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
};
const STATUSES = ["open", "in_progress", "pending", "resolved", "closed"];

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

export default function HomePage() {
  const [company, setCompany] = useState<Company | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [drafts, setDrafts] = useState<Record<number, { timezone: string; capacity: number; windows: WindowRow[] }>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [view, setView] = useState<"setup" | "tickets">("setup");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(false);
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

  async function saveCompanyTimezone(timezone: string) {
    try {
      const response = await fetch(`${API_URL}/api/companies/${COMPANY_ID}?timezone=${encodeURIComponent(timezone)}`, { method: "PUT" });
      if (!response.ok) throw new Error(await apiError(response));
      setCompany(await response.json());
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
          : `Ticket #${result.id} created but remains unassigned. ${result.reason}`,
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
          : `Ticket #${result.id} remains unassigned. ${result.reason}`,
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

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Ticket Assignment home"><span className="brand-mark">T</span><span>Ticket Assignment</span></a>
        <span className="topbar-label">Team settings</span>
      </header>

      <div className="content" id="home">
        <div className="page-heading">
          <div>
            <p className="eyebrow">WORKSPACE SETUP</p>
            <h1>{company?.name ?? "Team settings"}</h1>
            <p className="subheading">Manage agent schedules and workload limits.</p>
          </div>
          <div className="phase-chip"><span className="status-dot" /> Phase 2 · Ticket workflow</div>
        </div>

        {notice && <div className={`notice ${notice.kind}`} role="status">{notice.text}</div>}

        <nav className="view-tabs" aria-label="Workspace sections">
          <button className={view === "setup" ? "active" : ""} onClick={() => setView("setup")}>Team setup</button>
          <button className={view === "tickets" ? "active" : ""} onClick={() => setView("tickets")}>Tickets</button>
        </nav>

        {view === "setup" ? <>
        <section className="company-card" aria-labelledby="company-heading">
          <div className="section-copy">
            <p className="eyebrow">COMPANY</p>
            <h2 id="company-heading">Workspace timezone</h2>
            <p>Used for reporting team coverage in a later phase.</p>
          </div>
          <div className="company-control">
            <label className="sr-only" htmlFor="company-timezone">Company timezone</label>
            <input id="company-timezone" defaultValue={company?.timezone ?? ""} key={company?.timezone} placeholder="Asia/Kolkata" onBlur={(event) => {
              const value = event.currentTarget.value.trim();
              if (value && value !== company?.timezone) void saveCompanyTimezone(value);
            }} />
            <span className="field-hint">IANA timezone</span>
          </div>
        </section>

        <div className="section-heading">
          <div><h2>Agents</h2><p>Set each agent’s timezone, active ticket limit, and recurring hours.</p></div>
          {agents.length > 0 && <span className="count-pill">{agents.length} agents</span>}
        </div>

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
                    <input value={draft.timezone} onChange={(event) => updateDraft(agent.id, { timezone: event.target.value })} placeholder="Europe/London" />
                    <span className="field-hint">Example: America/New_York</span>
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
        </> : <>
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
                <p className="ticket-meta">Ticket #{ticket.id} · Created {new Date(ticket.created_at).toLocaleString()}</p>
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
        </>}
      </div>
    </main>
  );
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
