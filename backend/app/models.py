from datetime import datetime, time

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    agents: Mapped[list["Agent"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("max_active_tickets > 0", name="ck_agents_positive_capacity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    max_active_tickets: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    last_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship(back_populates="agents")
    availability_windows: Mapped[list["AvailabilityWindow"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by=("AvailabilityWindow.day_of_week", "AvailabilityWindow.start_time"),
    )


class AvailabilityWindow(Base):
    __tablename__ = "availability_windows"
    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_availability_day_range"),
        CheckConstraint("start_time <> end_time", name="ck_availability_nonzero_window"),
        UniqueConstraint("agent_id", "day_of_week", "start_time", "end_time", name="uq_availability_window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
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
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
