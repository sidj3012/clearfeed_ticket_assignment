from __future__ import annotations

from datetime import datetime, time
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .timezones import validate_timezone


class AvailabilityWindowInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @field_validator("start_time", "end_time")
    @classmethod
    def require_minute_precision(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("Schedule times are local wall-clock times without a timezone offset.")
        if value.second or value.microsecond:
            raise ValueError("Times must use HH:MM precision.")
        return value

    @field_validator("end_time")
    @classmethod
    def end_differs_from_start(cls, value: time, info):
        start = info.data.get("start_time")
        if start is not None and start == value:
            raise ValueError("Start and end times must differ.")
        return value


class AvailabilityWindowRead(AvailabilityWindowInput):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AgentConfigUpdate(BaseModel):
    timezone: str
    max_active_tickets: int = Field(ge=1)

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str) -> str:
        return validate_timezone(value)


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    timezone: str
    max_active_tickets: int = Field(default=5, ge=1)
    availability_windows: list[AvailabilityWindowInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def agent_name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Agent name cannot be blank.")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str) -> str:
        return validate_timezone(value)


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    name: str
    timezone: str
    max_active_tickets: int
    availability_windows: list[AvailabilityWindowRead]


class AgentUTCAvailabilityRead(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str


class AgentOverviewRead(BaseModel):
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
    subject: str = Field(min_length=1, max_length=240)

    @field_validator("subject")
    @classmethod
    def subject_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ticket subject cannot be blank.")
        return value


class TicketStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_supported(cls, value: str) -> str:
        allowed = {"open", "in_progress", "pending", "resolved", "closed"}
        if value not in allowed:
            raise ValueError("Status must be open, in_progress, pending, resolved, or closed.")
        return value


class TicketAgentRead(BaseModel):
    id: int
    name: str


class AvailableAgentRead(BaseModel):
    id: int
    name: str
    active_ticket_count: int
    max_active_tickets: int


class TicketWorkflowRead(BaseModel):
    id: int
    company_id: int
    subject: str
    status: str
    created_at: datetime
    assigned: bool
    agent: Optional[TicketAgentRead] = None
    current_workload: Optional[int] = None
    assigned_at: Optional[datetime] = None
    reason_code: Optional[str] = None
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


class CoverageConfigUpdate(BaseModel):
    timezone: str
    windows: list[AvailabilityWindowInput]

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str) -> str:
        return validate_timezone(value)


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
