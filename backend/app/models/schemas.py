from datetime import date
from pydantic import BaseModel, Field
from typing import Optional, List

class UserOut(BaseModel):
    id: str
    name: str
    role: str
    discipline: str

class ProjectOut(BaseModel):
    id: str
    project_name: str
    client_name: str
    division: str
    discipline: str
    pm_user_id: str
    start_date: date
    end_date: date
    contract_type: str
    approved_budget: float
    status: str
    not_awarded_reason: Optional[str] = None


class RateScheduleIn(BaseModel):
    rate_key: str
    rate: float = Field(gt=0)


class RateScheduleOut(BaseModel):
    id: str
    project_id: str
    rate_key: str
    rate: float


class ProjectCreateIn(BaseModel):
    project_name: str
    client_name: str
    division: str
    discipline: str
    pm_user_id: str
    start_date: date
    end_date: date
    contract_type: str
    approved_budget: float = Field(gt=0)
    status: str
    not_awarded_reason: Optional[str] = None
    rates: List[RateScheduleIn] = Field(default_factory=list)


class ProjectUpdateIn(BaseModel):
    project_name: Optional[str] = None
    client_name: Optional[str] = None
    division: Optional[str] = None
    discipline: Optional[str] = None
    pm_user_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    contract_type: Optional[str] = None
    approved_budget: Optional[float] = Field(default=None, gt=0)
    status: Optional[str] = None
    not_awarded_reason: Optional[str] = None


class ProjectDetailOut(ProjectOut):
    rates: List[RateScheduleOut] = Field(default_factory=list)

class TimesheetCreateIn(BaseModel):
    project_id: str
    period_start: date
    period_end: date

class TimeEntryCreateIn(BaseModel):
    work_date: date
    discipline: str
    hours: float = Field(gt=0, le=24)
    billable: bool
    notes: str

class TimesheetOut(BaseModel):
    id: str
    employee_id: str
    employee_name: Optional[str] = None
    project_id: str
    period_start: date
    period_end: date
    status: str
    rejection_reason: Optional[str] = None
    total_hours: float = 0.0
    total_billable_hours: float = 0.0


class TimeEntryOut(BaseModel):
    id: str
    timesheet_id: str
    work_date: date
    discipline: str
    hours: float
    billable: bool
    notes: str


class TimesheetDetailOut(TimesheetOut):
    entries: List[TimeEntryOut] = Field(default_factory=list)

class ApprovalDecisionIn(BaseModel):
    reason: Optional[str] = None

class InvoiceDraftOut(BaseModel):
    invoice_id: str
    project_id: str
    invoice_month: date
    status: str
    subtotal: float
    adjustments_total: float
    total: float
    lines: list[dict]

class AdjustmentIn(BaseModel):
    description: str
    amount: float

class DashboardOut(BaseModel):
    month: date
    projects: list[dict]
    utilization: list[dict]

# AI schemas
class AINotesIn(BaseModel):
    raw_notes: str
    discipline: Optional[str] = None
    project_name: Optional[str] = None

class AINotesOut(BaseModel):
    improved_notes: str

class AIBillableIn(BaseModel):
    notes: str
    discipline: Optional[str] = None
    contract_type: Optional[str] = None

class AIBillableOut(BaseModel):
    billable: bool
    confidence: float
    reason: str

class AIExplainMetricsIn(BaseModel):
    title: str
    metrics: dict

class AIExplainMetricsOut(BaseModel):
    summary: str
    risk_label: str
    recommended_actions: list[str]
