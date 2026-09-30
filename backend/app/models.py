from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .database import Base
from .timezones import validate_timezone


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    @validates("timezone")
    def validate_company_timezone(self, _key: str, value: str) -> str:
        return validate_timezone(value)

    agents: Mapped[list["Agent"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("max_active_tickets > 0", name="ck_agents_positive_capacity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey(Company.id, ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    max_active_tickets: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    last_assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    @validates("timezone")
    def validate_agent_timezone(self, _key: str, value: str) -> str:
        return validate_timezone(value)

    company: Mapped[Company] = relationship(back_populates="agents")
    availability_windows: Mapped[list["AvailabilityWindow"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by=lambda: (AvailabilityWindow.day_of_week, AvailabilityWindow.start_time),
    )


class AvailabilityWindow(Base):
    __tablename__ = "availability_windows"
    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_availability_day_range"),
        CheckConstraint("start_time <> end_time", name="ck_availability_nonzero_window"),
        UniqueConstraint("agent_id", "day_of_week", "start_time", "end_time", name="uq_availability_window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey(Agent.id, ondelete="CASCADE"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    agent: Mapped[Agent] = relationship(back_populates="availability_windows")


class CoverageWindow(Base):
    __tablename__ = "coverage_windows"
    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_coverage_day_range"),
        CheckConstraint("start_time <> end_time", name="ck_coverage_nonzero_window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey(Company.id, ondelete="CASCADE"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'pending', 'resolved', 'closed')",
            name="ck_tickets_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey(Company.id, ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped[Company] = relationship()
    assignment: Mapped[Optional["Assignment"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", uselist=False
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey(Ticket.id, ondelete="CASCADE"), nullable=False, unique=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey(Agent.id, ondelete="CASCADE"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)

    ticket: Mapped[Ticket] = relationship(back_populates="assignment")
    agent: Mapped[Agent] = relationship()
