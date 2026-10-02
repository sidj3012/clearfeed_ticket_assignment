from __future__ import annotations

from datetime import datetime, time
from typing import Annotated, Optional
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from .enums import TicketStatus, UnassignedReasonCode
from .timezones import validate_timezone


class IanaTimezoneModel(BaseModel):
    """Shared base for request models that carry an IANA timezone."""

    timezone: str

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str) -> str:
        return validate_timezone(value)


class AvailabilityWindowInput(BaseModel):
    # API schedule times are local wall-clock values with minute precision.
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @field_validator("start_time", "end_time")
    @classmethod
    def require_minute_precision(cls, value: time) -> time:
        # Offsets and seconds are rejected to keep recurring schedules unambiguous.
        if value.tzinfo is not None:
            raise ValueError("Schedule times are local wall-clock times without a timezone offset.")
        if value.second or value.microsecond:
            raise ValueError("Times must use HH:MM precision.")
        return value

    @field_validator("end_time")
    @classmethod
    def end_differs_from_start(cls, value: time, info):
        # Equal endpoints would otherwise represent either an empty or ambiguous full-day shift.
        start = info.data.get("start_time")
        if start is not None and start == value:
            raise ValueError("Start and end times must differ.")
        return value


def require_unique_schedule_windows(windows: list[AvailabilityWindowInput]) -> list[AvailabilityWindowInput]:
    """Reject duplicate recurring windows during request validation."""
    keys = [(window.day_of_week, window.start_time, window.end_time) for window in windows]
    if len(keys) != len(set(keys)):
        raise ValueError("Schedule windows must be unique.")
    return windows


# Reuse list-level validation for both agent creation and schedule replacement.
UniqueScheduleWindows = Annotated[list[AvailabilityWindowInput], AfterValidator(require_unique_schedule_windows)]


class AvailabilityWindowRead(AvailabilityWindowInput):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AgentConfigUpdate(IanaTimezoneModel):
    # Only editable agent settings are accepted by the configuration endpoint.
    max_active_tickets: int = Field(ge=1)


class AgentCreate(IanaTimezoneModel):
    # Creation accepts core settings and an optional set of weekly windows.
    name: str = Field(min_length=1, max_length=160)
    max_active_tickets: int = Field(default=5, ge=1)
    availability_windows: UniqueScheduleWindows = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def agent_name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Agent name cannot be blank.")
        return value


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    name: str
    timezone: str
    max_active_tickets: int
    availability_windows: list[AvailabilityWindowRead]


class AgentConfigRead(BaseModel):
    """Response for timezone/capacity edits that do not read availability windows."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    name: str
    timezone: str
    max_active_tickets: int


class AgentUTCAvailabilityRead(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str


class AgentOverviewRead(BaseModel):
    # Read model for the workload, live availability, and UTC schedule overview.
    id: int
    name: str
    timezone: str
    max_active_tickets: int
    active_ticket_count: int
    is_available: bool
    availability_hours_utc: list[AgentUTCAvailabilityRead]


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    timezone: str


class TicketCreate(BaseModel):
    # Require a human-readable, nonblank subject before a ticket is persisted.
    subject: str = Field(min_length=1, max_length=240)

    @field_validator("subject")
    @classmethod
    def subject_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ticket subject cannot be blank.")
        return value


class TicketStatusUpdate(BaseModel):
    # Restrict ticket status values to the workload states supported by this service.
    status: TicketStatus


class TicketAgentRead(BaseModel):
    id: int
    name: str


class AvailableAgentRead(BaseModel):
    id: int
    name: str
    active_ticket_count: int
    max_active_tickets: int


class TicketWorkflowRead(BaseModel):
    # Assignment response includes either the selected agent or an actionable reason.
    id: int
    company_id: int
    subject: str
    status: str
    created_at: datetime
    assigned: bool
    agent: Optional[TicketAgentRead] = None
    current_workload: Optional[int] = None
    assigned_at: Optional[datetime] = None
    reason_code: Optional[UnassignedReasonCode] = None
    reason: str
    available_agents: list[AvailableAgentRead] = Field(default_factory=list)


class TicketListRead(BaseModel):
    id: int
    company_id: int
    subject: str
    status: str
    created_at: datetime
    agent: Optional[TicketAgentRead] = None
    assignment_reason: Optional[str] = None


class CoverageConfigUpdate(IanaTimezoneModel):
    # Company timezone controls how required coverage windows are interpreted.
    windows: UniqueScheduleWindows


class CoverageWindowRead(AvailabilityWindowRead):
    company_id: int


class CoverageSegment(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str
    covered: bool


class CoverageRead(BaseModel):
    company_timezone: str
    week_start: str
    required_windows: list[CoverageWindowRead]
    covered_periods: list[CoverageSegment]
    gaps: list[CoverageSegment]
