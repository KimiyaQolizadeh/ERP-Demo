from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.schemas import (
    TimeEntryCreateIn,
    TimeEntryOut,
    TimesheetCreateIn,
    TimesheetDetailOut,
    TimesheetOut,
)
from app.services import timesheets as svc

router = APIRouter(prefix="/timesheets", tags=["timesheets"])


@router.post("", response_model=TimesheetOut)
def create_timesheet(
    payload: TimesheetCreateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    ts = svc.create_timesheet(
        db, user, payload.project_id, payload.period_start, payload.period_end
    )
    return TimesheetOut(
        id=str(ts.id),
        employee_id=str(ts.employee_id),
        employee_name=ts.employee_name,
        project_id=str(ts.project_id),
        period_start=ts.period_start,
        period_end=ts.period_end,
        status=ts.status,
        rejection_reason=ts.rejection_reason,
        total_hours=0.0,
    )


@router.post("/{timesheet_id}/entries")
def add_entry(
    timesheet_id: str,
    payload: TimeEntryCreateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    entry = svc.add_entry(db, user, timesheet_id, payload)
    return {"entry_id": str(entry.id)}


@router.get("/{timesheet_id}/entries", response_model=list[TimeEntryOut])
def list_entries(
    timesheet_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    rows = svc.list_entries(db, user, timesheet_id)
    return [
        TimeEntryOut(
            id=str(entry.id),
            timesheet_id=str(entry.timesheet_id),
            work_date=entry.work_date,
            discipline=entry.discipline,
            hours=float(entry.hours),
            billable=bool(entry.billable),
            notes=entry.notes,
        )
        for entry in rows
    ]


@router.post("/{timesheet_id}/submit", response_model=TimesheetOut)
def submit(
    timesheet_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    ts = svc.submit_timesheet(db, user, timesheet_id)
    return TimesheetOut(
        id=str(ts.id),
        employee_id=str(ts.employee_id),
        employee_name=ts.employee_name,
        project_id=str(ts.project_id),
        period_start=ts.period_start,
        period_end=ts.period_end,
        status=ts.status,
        rejection_reason=ts.rejection_reason,
        total_hours=float(sum(float(entry.hours) for entry in ts.entries) if ts.entries else 0.0),
    )


@router.post("/{timesheet_id}/reopen", response_model=TimesheetOut)
def reopen(
    timesheet_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    ts = svc.reopen_rejected_timesheet(db, user, timesheet_id)
    return TimesheetOut(
        id=str(ts.id),
        employee_id=str(ts.employee_id),
        employee_name=ts.employee_name,
        project_id=str(ts.project_id),
        period_start=ts.period_start,
        period_end=ts.period_end,
        status=ts.status,
        rejection_reason=ts.rejection_reason,
        total_hours=float(sum(float(entry.hours) for entry in ts.entries) if ts.entries else 0.0),
    )


@router.get("/{timesheet_id}", response_model=TimesheetDetailOut)
def get_timesheet(
    timesheet_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    ts, total_hours = svc.get_timesheet(db, user, timesheet_id)
    entries = [
        TimeEntryOut(
            id=str(entry.id),
            timesheet_id=str(entry.timesheet_id),
            work_date=entry.work_date,
            discipline=entry.discipline,
            hours=float(entry.hours),
            billable=bool(entry.billable),
            notes=entry.notes,
        )
        for entry in (ts.entries or [])
    ]
    return TimesheetDetailOut(
        id=str(ts.id),
        employee_id=str(ts.employee_id),
        employee_name=ts.employee_name,
        project_id=str(ts.project_id),
        period_start=ts.period_start,
        period_end=ts.period_end,
        status=ts.status,
        rejection_reason=ts.rejection_reason,
        total_hours=float(total_hours or 0.0),
        entries=entries,
    )


@router.get("", response_model=list[TimesheetOut])
def list_my_timesheets(
    status: str | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    rows = svc.list_timesheets(db, user, status=status)
    return [
        TimesheetOut(
            id=str(ts.id),
            employee_id=str(ts.employee_id),
            employee_name=ts.employee_name,
            project_id=str(ts.project_id),
            period_start=ts.period_start,
            period_end=ts.period_end,
            status=ts.status,
            rejection_reason=ts.rejection_reason,
            total_hours=float(total_hours or 0.0),
        )
        for ts, total_hours in rows
    ]
