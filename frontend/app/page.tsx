"use client";

import { useCallback, useEffect, useState } from "react";

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

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

export default function HomePage() {
  const [company, setCompany] = useState<Company | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [drafts, setDrafts] = useState<Record<number, { timezone: string; capacity: number; windows: WindowRow[] }>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);
  const [notice, setNotice] = useState<{ kind: "success" | "error"; text: string } | null>(null);

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
          <div className="phase-chip"><span className="status-dot" /> Phase 1 · Agent setup</div>
        </div>

        {notice && <div className={`notice ${notice.kind}`} role="status">{notice.text}</div>}

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
        <footer className="footer-note">Changes are used by ticket assignment in the next phase.</footer>
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
