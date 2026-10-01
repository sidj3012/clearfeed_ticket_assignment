"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { API_URL, COMPANY_ID } from "./constants";
import { AgentOverviewView } from "./components/AgentOverviewView";
import { CoverageView } from "./components/CoverageView";
import { TeamSetupView } from "./components/TeamSetupView";
import { TicketsView } from "./components/TicketsView";
import type { Agent, AgentDraft, AgentOverview, Company, CoverageSummary, CoverageWindow, Notice, Ticket, TicketResult, WindowRow, WorkspaceView } from "./types";
import { apiError, capacitySummary, messageFromError } from "./utils";

export default function HomePage() {
  // Keep server data separate from editable drafts so users can save changes explicitly.
  const [company, setCompany] = useState<Company | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [drafts, setDrafts] = useState<Record<number, AgentDraft>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [creatingAgent, setCreatingAgent] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [newAgentTimezone, setNewAgentTimezone] = useState("UTC");
  const [newAgentCapacity, setNewAgentCapacity] = useState(5);
  const [newAgentWindows, setNewAgentWindows] = useState<WindowRow[]>([]);
  const [view, setView] = useState<WorkspaceView>("setup");
  // State for the live dashboard, ticket workflow, coverage editor, and feedback messages.
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
  const [notice, setNotice] = useState<Notice | null>(null);

  const load = useCallback(async () => {
    // Load company and agent configuration together to initialize the setup screen.
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
    // Update the visible UTC clock once per second while this page is mounted.
    const updateClock = () => setCurrentUtc(`${new Date().toISOString().replace("T", " ").slice(0, 19)} UTC`);
    updateClock();
    const interval = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(interval);
  }, []);

  const loadAgentOverview = useCallback(async () => {
    // Refresh availability and ticket counts from the server when needed.
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
    // Retrieve tickets after entering the ticket view or completing a ticket action.
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
    // Load saved coverage requirements and the calculated covered/gap intervals.
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

  function updateDraft(agentId: number, update: Partial<AgentDraft>) {
    // Update one agent's local edits without affecting other agent forms.
    setDrafts((current) => ({ ...current, [agentId]: { ...current[agentId], ...update } }));
  }

  async function saveAgent(agent: Agent) {
    // Save agent settings and recurring availability, then reload canonical server state.
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
    // Submit a new agent and its initial schedule as one API operation.
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
    // Persist the timezone that coverage reporting uses for the company.
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
    // Ticket creation runs assignment immediately and reports why assignment did or did not happen.
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
    // Ask the API to retry assignment after team availability or capacity may have changed.
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
    // Status updates refresh ticket workload and can free capacity when work is resolved.
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
    // Replace required hours and refresh the server's coverage calculation.
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

        {view === "setup" && <TeamSetupView
          company={company}
          agents={agents}
          drafts={drafts}
          loading={loading}
          savingAgentId={saving}
          showAgentForm={showAgentForm}
          creatingAgent={creatingAgent}
          newAgentName={newAgentName}
          newAgentTimezone={newAgentTimezone}
          newAgentCapacity={newAgentCapacity}
          newAgentWindows={newAgentWindows}
          setShowAgentForm={setShowAgentForm}
          setNewAgentName={setNewAgentName}
          setNewAgentTimezone={setNewAgentTimezone}
          setNewAgentCapacity={setNewAgentCapacity}
          setNewAgentWindows={setNewAgentWindows}
          onSaveCompanyTimezone={(timezone) => void saveCompanyTimezone(timezone)}
          onCreateAgent={createAgent}
          onSaveAgent={(agent) => void saveAgent(agent)}
          onUpdateDraft={updateDraft}
        />}
        {view === "agents" && <AgentOverviewView agents={agentsOverview} loading={agentsOverviewLoading} />}
        {view === "tickets" && <TicketsView
          tickets={tickets}
          loading={ticketsLoading}
          creatingTicket={creatingTicket}
          ticketSubject={ticketSubject}
          ticketActionId={ticketAction}
          setTicketSubject={setTicketSubject}
          onCreateTicket={createTicket}
          onRetryTicket={(ticket) => void retryTicket(ticket)}
          onUpdateStatus={(ticket, status) => void updateTicketStatus(ticket, status)}
        />}
        {view === "coverage" && <CoverageView
          coverage={coverage}
          timezone={coverageTimezone}
          windows={coverageWindows}
          loading={coverageLoading}
          saving={savingCoverage}
          setTimezone={setCoverageTimezone}
          setWindows={setCoverageWindows}
          onSave={() => void saveCoverage()}
        />}
      </div>
    </main>
  );
}
