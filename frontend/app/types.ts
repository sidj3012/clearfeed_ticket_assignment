// Shared API and form types used by the workspace page and its view components.
export type WindowRow = { id?: number; day_of_week: number; start_time: string; end_time: string };
export type Agent = {
  id: number;
  company_id: number;
  name: string;
  timezone: string;
  max_active_tickets: number;
  availability_windows: WindowRow[];
};
export type AgentDraft = { timezone: string; capacity: number; windows: WindowRow[] };
export type Company = { id: number; name: string; timezone: string };
export type Ticket = {
  id: number;
  subject: string;
  status: string;
  created_at: string;
  agent: { id: number; name: string } | null;
  assignment_reason: string | null;
};
export type TicketResult = Ticket & {
  assigned: boolean;
  current_workload: number | null;
  reason_code: string | null;
  reason: string;
  available_agents: { id: number; name: string; active_ticket_count: number; max_active_tickets: number }[];
};
export type AgentOverview = {
  id: number;
  name: string;
  timezone: string;
  max_active_tickets: number;
  active_ticket_count: number;
  is_available: boolean;
  availability_hours_utc: { day_of_week: number; start_time: string; end_time: string }[];
};
export type CoverageWindow = { id?: number; day_of_week: number; start_time: string; end_time: string };
export type CoverageSegment = { day_of_week: number; start_time: string; end_time: string; covered: boolean };
export type CoverageSummary = {
  company_timezone: string;
  week_start: string;
  required_windows: CoverageWindow[];
  covered_periods: CoverageSegment[];
  gaps: CoverageSegment[];
};
export type Notice = { kind: "success" | "error" | "info"; text: string };
export type WorkspaceView = "setup" | "agents" | "tickets" | "coverage";
