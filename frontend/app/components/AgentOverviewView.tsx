import { DAYS } from "../constants";
import type { AgentOverview } from "../types";

type AgentOverviewViewProps = { agents: AgentOverview[]; loading: boolean };

// Present the live workload, availability state, and UTC hours for each agent.
export function AgentOverviewView({ agents, loading }: AgentOverviewViewProps) {
  return loading ? <div className="empty-state">Loading agent overview…</div> : agents.length === 0 ? (
    <div className="empty-state">No agents are configured for this company.</div>
  ) : <>
    <div className="agent-overview-list">
      {agents.map((agent) => <section className="agent-overview-card" key={agent.id}>
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
    </div>
    <footer className="footer-note">Ticket counts include open, in-progress, and pending tickets. UTC hours show the current UTC week.</footer>
  </>;
}
