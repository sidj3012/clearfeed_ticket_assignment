"use client";

import type { FormEvent } from "react";

import { STATUSES } from "../constants";
import type { Ticket } from "../types";
import { formatUtcTimestamp } from "../utils";

type TicketsViewProps = {
  tickets: Ticket[];
  loading: boolean;
  creatingTicket: boolean;
  ticketSubject: string;
  ticketActionId: number | null;
  setTicketSubject: (subject: string) => void;
  onCreateTicket: (event: FormEvent<HTMLFormElement>) => void;
  onRetryTicket: (ticket: Ticket) => void;
  onUpdateStatus: (ticket: Ticket, status: string) => void;
};

// Ticket queue view for creating, retrying, and changing ticket status.
export function TicketsView(props: TicketsViewProps) {
  const { tickets, loading, creatingTicket, ticketSubject, ticketActionId, setTicketSubject, onCreateTicket, onRetryTicket, onUpdateStatus } = props;

  return (
    <>
      <section className="ticket-create-card">
        <div><p className="eyebrow">TICKET QUEUE</p><h2>Create a ticket</h2><p>New tickets start open and are assigned automatically when an agent is eligible.</p></div>
        <form className="ticket-create-form" onSubmit={(event) => { event.preventDefault(); onCreateTicket(event); }}>
          <label className="sr-only" htmlFor="ticket-subject">Ticket subject</label>
          <input id="ticket-subject" value={ticketSubject} maxLength={240} onChange={(event) => setTicketSubject(event.target.value)} placeholder="Briefly describe the customer’s issue" required />
          <button className="button primary" disabled={creatingTicket || !ticketSubject.trim()}>{creatingTicket ? "Creating…" : "Create ticket"}</button>
        </form>
      </section>

      <div className="section-heading tickets-heading">
        <div><h2>Tickets</h2><p>Update status or retry assignment for unassigned tickets.</p></div>
        {tickets.length > 0 && <span className="count-pill">{tickets.length} tickets</span>}
      </div>
      {loading ? <div className="empty-state">Loading tickets…</div> : tickets.length === 0 ? (
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
            {!ticket.agent && <button className="button secondary" onClick={() => onRetryTicket(ticket)} disabled={ticketActionId === ticket.id}>{ticketActionId === ticket.id ? "Retrying…" : "Retry assignment"}</button>}
            <label className="sr-only" htmlFor={`status-${ticket.id}`}>Ticket status</label>
            <select id={`status-${ticket.id}`} value={ticket.status} disabled={ticketActionId === ticket.id} onChange={(event) => onUpdateStatus(ticket, event.target.value)}>
              {STATUSES.map((status) => <option key={status} value={status}>{status.replace("_", " ")}</option>)}
            </select>
          </div>
        </article>)}
      </div>}
      <footer className="footer-note">Active tickets are open, in progress, or pending.</footer>
    </>
  );
}
