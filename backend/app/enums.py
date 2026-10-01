"""String enums for values shared by API schemas and assignment logic."""

from enum import Enum


class TicketStatus(str, Enum):
    """Ticket lifecycle states accepted by the API and used for workload counts."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


class UnassignedReasonCode(str, Enum):
    """Stable reason identifiers for tickets that could not be assigned."""

    NO_AGENTS_FOUND = "NO_AGENTS_FOUND"
    NO_AVAILABLE_AGENT = "NO_AVAILABLE_AGENT"
    ALL_AGENTS_AT_CAPACITY = "ALL_AGENTS_AT_CAPACITY"
