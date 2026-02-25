from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.tables import Project, Timesheet, TimeEntry
from app.services import authz

def create_timesheet(db: Session, user, project_id, period_start, period_end) -> Timesheet:
    if user.role not in ("EMPLOYEE", "ADMIN"):
        raise HTTPException(status_code=403, detail="Only employees can create timesheets")
    ts = Timesheet(
        employee_id=user.id,
        employee_name=user.name,
        project_id=project_id,
        period_start=period_start,
        period_end=period_end,
        status="DRAFT",
    )
    db.add(ts)
    db.commit()
    db.refresh(ts)
    return ts

def add_entry(db: Session, user, timesheet_id, entry_in) -> TimeEntry:
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    if not authz.can_edit_timesheet(user, ts):
        raise HTTPException(status_code=403, detail="Not allowed to edit timesheet")
    e = TimeEntry(
        timesheet_id=ts.id,
        work_date=entry_in.work_date,
        discipline=entry_in.discipline,
        hours=entry_in.hours,
        billable=entry_in.billable,
        notes=entry_in.notes,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e

def submit_timesheet(db: Session, user, timesheet_id) -> Timesheet:
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    if not authz.can_submit_timesheet(user, ts):
        raise HTTPException(status_code=403, detail="Not allowed to submit")
    if ts.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Only draft timesheets can be submitted")
    ts.status = "SUBMITTED"
    ts.submitted_at = datetime.utcnow()
    db.commit()
    db.refresh(ts)
    return ts

def list_timesheets(db: Session, user, status: str | None = None):
    q = db.query(Timesheet)
    if user.role == "EMPLOYEE":
        q = q.filter(Timesheet.employee_id == user.id)
    if status:
        q = q.filter(Timesheet.status == status)
    return (
        q.outerjoin(TimeEntry, TimeEntry.timesheet_id == Timesheet.id)
        .with_entities(Timesheet, func.coalesce(func.sum(TimeEntry.hours), 0).label("total_hours"))
        .group_by(Timesheet.id)
        .order_by(Timesheet.period_end.desc())
        .limit(200)
        .all()
    )

def get_timesheet(db: Session, user, timesheet_id: str) -> tuple[Timesheet, float]:
    ts, project = (
        db.query(Timesheet, Project)
        .join(Project, Project.id == Timesheet.project_id)
        .filter(Timesheet.id == timesheet_id)
        .first()
        or (None, None)
    )
    if not ts or not project:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    if not authz.can_view_timesheet(user, ts, project):
        raise HTTPException(status_code=403, detail="Not allowed to view timesheet")
    total_hours = (
        db.query(func.coalesce(func.sum(TimeEntry.hours), 0))
        .filter(TimeEntry.timesheet_id == ts.id)
        .scalar()
    )
    return ts, float(total_hours or 0.0)


def list_entries(db: Session, user, timesheet_id: str) -> list[TimeEntry]:
    ts, project = (
        db.query(Timesheet, Project)
        .join(Project, Project.id == Timesheet.project_id)
        .filter(Timesheet.id == timesheet_id)
        .first()
        or (None, None)
    )
    if not ts or not project:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    if not authz.can_view_timesheet(user, ts, project):
        raise HTTPException(status_code=403, detail="Not allowed to view timesheet")
    return (
        db.query(TimeEntry)
        .filter(TimeEntry.timesheet_id == ts.id)
        .order_by(TimeEntry.work_date.asc(), TimeEntry.id.asc())
        .all()
    )


def reopen_rejected_timesheet(db: Session, user, timesheet_id: str) -> Timesheet:
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    if not (authz.is_admin(user) or ts.employee_id == user.id):
        raise HTTPException(
            status_code=403, detail="Only owner or admin can reopen rejected timesheet"
        )
    if ts.status != "REJECTED":
        raise HTTPException(
            status_code=400, detail="Only rejected timesheets can be reopened"
        )
    ts.status = "DRAFT"
    ts.rejection_reason = None
    ts.decided_at = None
    ts.decided_by_pm = None
    db.commit()
    db.refresh(ts)
    return ts
