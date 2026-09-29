from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Use a valid IANA timezone, such as Asia/Kolkata.") from None
    return value


class AvailabilityWindowInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @field_validator("start_time", "end_time")
    @classmethod
    def require_minute_precision(cls, value: time) -> time:
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


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    name: str
    timezone: str
    max_active_tickets: int
    availability_windows: list[AvailabilityWindowRead]


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    timezone: str
