import uuid
from datetime import datetime, date
from sqlalchemy import (
    String, DateTime, Date, Boolean, Numeric, ForeignKey, UniqueConstraint, Index, Text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import UserRole, ProjectStatus, ContractType, TimesheetStatus, InvoiceStatus

def _uuid():
    return uuid.uuid4()

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    discipline: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    managed_projects = relationship("Project", back_populates="pm", foreign_keys="Project.pm_user_id")

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    division: Mapped[str] = mapped_column(String(10), nullable=False)
    discipline: Mapped[str] = mapped_column(String(100), nullable=False)
    pm_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    contract_type: Mapped[str] = mapped_column(String(20), nullable=False)
    approved_budget: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    not_awarded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    pm = relationship("User", back_populates="managed_projects", foreign_keys=[pm_user_id])
    rates = relationship("RateSchedule", back_populates="project", cascade="all, delete-orphan")

class RateSchedule(Base):
    __tablename__ = "rate_schedule"
    __table_args__ = (UniqueConstraint("project_id", "rate_key", name="uq_rate_project_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    rate_key: Mapped[str] = mapped_column(String(100), nullable=False)  # discipline or role
    rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    project = relationship("Project", back_populates="rates")

class Timesheet(Base):
    __tablename__ = "timesheets"
    __table_args__ = (
        Index("idx_timesheets_status", "status"),
        Index("idx_timesheets_project", "project_id"),
        Index("idx_timesheets_employee", "employee_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    employee_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TimesheetStatus.DRAFT.value)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_pm: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    entries = relationship("TimeEntry", back_populates="timesheet", cascade="all, delete-orphan")

class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("project_id", "invoice_month", name="uq_invoice_project_month"),
        Index("idx_invoices_project_month", "project_id", "invoice_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    invoice_month: Mapped[date] = mapped_column(Date, nullable=False)  # first day of month
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=InvoiceStatus.DRAFT.value)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    adjustments_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_finance: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    adjustments = relationship("InvoiceAdjustment", back_populates="invoice", cascade="all, delete-orphan")

class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (Index("idx_invoice_lines_invoice", "invoice_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"))
    rate_key: Mapped[str] = mapped_column(String(100), nullable=False)
    hours: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    invoice = relationship("Invoice", back_populates="lines")

class InvoiceAdjustment(Base):
    __tablename__ = "invoice_adjustments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="adjustments")

class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        Index("idx_entries_timesheet", "timesheet_id"),
        Index("idx_entries_invoiced", "invoiced_line_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    timesheet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("timesheets.id", ondelete="CASCADE"))
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    discipline: Mapped[str] = mapped_column(String(100), nullable=False)
    hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)

    invoiced_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoice_lines.id"), nullable=True)

    ai_billable_suggestion: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    ai_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    timesheet = relationship("Timesheet", back_populates="entries")

class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("idx_audit_ts", "ts"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

class UserPreference(Base):
    __tablename__ = "user_preferences"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True)
    prefs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class VectorDocument(Base):
    __tablename__ = "vector_documents"
    __table_args__ = (
        Index("idx_vector_source", "source_type", "source_id"),
        Index("idx_vector_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. time_entry_note
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    attrs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # keeps demo dependency-light
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
