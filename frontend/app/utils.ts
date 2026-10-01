import type { AgentDraft, TicketResult, WindowRow } from "./types";

// Keep a saved timezone selectable even if the browser omits it from its list.
export function timezoneOptions(zones: string[], selected: string): string[] {
  return selected && !zones.includes(selected) ? [selected, ...zones] : zones;
}

// Render server timestamps consistently as UTC in the ticket list.
export function formatUtcTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

// Normalize fetch and parsing failures into text suitable for the status notice.
export function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

// Show available-agent workload in assigned/max format when capacity blocks assignment.
export function capacitySummary(agents: TicketResult["available_agents"]): string {
  if (!agents.length) return "";
  const summary = agents.map((agent) => `${agent.name} (${agent.active_ticket_count}/${agent.max_active_tickets})`).join(", ");
  return ` Available agents and active tickets: ${summary}.`;
}

// Apply an edited field to only the selected recurring availability row.
export function updateWindow(
  agentId: number,
  windows: WindowRow[],
  index: number,
  changes: Partial<WindowRow>,
  update: (id: number, value: Partial<AgentDraft>) => void,
) {
  update(agentId, { windows: windows.map((item, i) => i === index ? { ...item, ...changes } : item) });
}

// Read FastAPI validation details and fall back to a concise generic message.
export async function apiError(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(" ");
  return "The request could not be saved.";
}
