"use client";

import type { Dispatch, FormEvent, SetStateAction } from "react";

import { DAYS } from "../constants";
import type { Agent, AgentDraft, Company, WindowRow } from "../types";
import { updateWindow } from "../utils";
import { TimezoneSelect } from "./TimezoneSelect";

type TeamSetupViewProps = {
  company: Company | null;
  agents: Agent[];
  drafts: Record<number, AgentDraft>;
  loading: boolean;
  savingAgentId: number | null;
  showAgentForm: boolean;
  creatingAgent: boolean;
  newAgentName: string;
  newAgentTimezone: string;
  newAgentCapacity: number;
  newAgentWindows: WindowRow[];
  setShowAgentForm: Dispatch<SetStateAction<boolean>>;
  setNewAgentName: Dispatch<SetStateAction<string>>;
  setNewAgentTimezone: Dispatch<SetStateAction<string>>;
  setNewAgentCapacity: Dispatch<SetStateAction<number>>;
  setNewAgentWindows: Dispatch<SetStateAction<WindowRow[]>>;
  onSaveCompanyTimezone: (timezone: string) => void;
  onCreateAgent: (event: FormEvent<HTMLFormElement>) => void;
  onSaveAgent: (agent: Agent) => void;
  onUpdateDraft: (agentId: number, update: Partial<AgentDraft>) => void;
};

// Company and agent configuration, including each agent's recurring local-time hours.
export function TeamSetupView(props: TeamSetupViewProps) {
  const {
    company,
    agents,
    drafts,
    loading,
    savingAgentId,
    showAgentForm,
    creatingAgent,
    newAgentName,
    newAgentTimezone,
    newAgentCapacity,
    newAgentWindows,
    setShowAgentForm,
    setNewAgentName,
    setNewAgentTimezone,
    setNewAgentCapacity,
    setNewAgentWindows,
    onSaveCompanyTimezone,
    onCreateAgent,
    onSaveAgent,
    onUpdateDraft,
  } = props;

  return (
    <>
      <section className="company-card" aria-labelledby="company-heading">
        <div className="section-copy">
          <p className="eyebrow">COMPANY</p>
          <h2 id="company-heading">Workspace timezone</h2>
          <p>Choose the timezone used for team coverage reporting.</p>
        </div>
        <div className="company-control">
          <label className="sr-only" htmlFor="company-timezone">Company timezone</label>
          <TimezoneSelect
            id="company-timezone"
            value={company?.timezone ?? "UTC"}
            onChange={(value) => { if (value !== company?.timezone) onSaveCompanyTimezone(value); }}
          />
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
        <form className="agent-create-form" onSubmit={(event) => { event.preventDefault(); onCreateAgent(event); }}>
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
          <div className="schedule-heading">
            <div><h4>Weekly availability</h4><p>Optional. Times use the selected agent timezone.</p></div>
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
                <button className="button primary" onClick={() => onSaveAgent(agent)} disabled={savingAgentId === agent.id}>
                  {savingAgentId === agent.id ? "Saving…" : "Save changes"}
                </button>
              </div>
              <div className="agent-fields">
                <label>Agent timezone
                  <TimezoneSelect value={draft.timezone} onChange={(value) => onUpdateDraft(agent.id, { timezone: value })} />
                </label>
                <label>Maximum active tickets
                  <input type="number" min="1" step="1" value={draft.capacity} onChange={(event) => onUpdateDraft(agent.id, { capacity: Number(event.target.value) })} />
                  <span className="field-hint">Positive whole number</span>
                </label>
              </div>
              <div className="schedule-heading">
                <div><h4>Weekly availability</h4><p>Times are in this agent’s timezone. End earlier than start for overnight hours.</p></div>
                <button className="button secondary" onClick={() => onUpdateDraft(agent.id, { windows: [...draft.windows, { day_of_week: 0, start_time: "09:00", end_time: "17:00" }] })}>+ Add hours</button>
              </div>
              {draft.windows.length === 0 ? <p className="no-hours">No recurring hours added.</p> : <div className="window-list">
                {draft.windows.map((window, index) => <div className="window-row" key={`${window.id ?? "new"}-${index}`}>
                  <label className="sr-only" htmlFor={`day-${agent.id}-${index}`}>Day</label>
                  <select id={`day-${agent.id}-${index}`} value={window.day_of_week} onChange={(event) => {
                    const windows = draft.windows.map((item, i) => i === index ? { ...item, day_of_week: Number(event.target.value) } : item);
                    onUpdateDraft(agent.id, { windows });
                  }}>{DAYS.map((day, value) => <option value={value} key={day}>{day}</option>)}</select>
                  <label className="sr-only" htmlFor={`start-${agent.id}-${index}`}>Start time</label>
                  <input id={`start-${agent.id}-${index}`} type="time" value={window.start_time} onChange={(event) => updateWindow(agent.id, draft.windows, index, { start_time: event.target.value }, onUpdateDraft)} />
                  <span className="time-separator">to</span>
                  <label className="sr-only" htmlFor={`end-${agent.id}-${index}`}>End time</label>
                  <input id={`end-${agent.id}-${index}`} type="time" value={window.end_time} onChange={(event) => updateWindow(agent.id, draft.windows, index, { end_time: event.target.value }, onUpdateDraft)} />
                  <button className="icon-button" title="Remove hours" aria-label={`Remove ${DAYS[window.day_of_week]} hours`} onClick={() => onUpdateDraft(agent.id, { windows: draft.windows.filter((_, i) => i !== index) })}>×</button>
                </div>)}
              </div>}
            </section>;
          })}
        </div>
      )}
      <footer className="footer-note">Agent settings are applied when the assignment service evaluates a ticket.</footer>
    </>
  );
}
