from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.schemas import ApprovalDecisionIn, TimesheetOut
from app.models.tables import Project
from app.services import approvals as svc

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _project_name(db: Session, project_id) -> str | None:
    row = db.query(Project.project_name).filter(Project.id == project_id).first()
    if not row:
        return None
    return str(row[0])

@router.get("/pending", response_model=list[TimesheetOut])
def pending(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = svc.list_pending_for_pm_with_hours(db, user)
    return [
        TimesheetOut(
            id=str(row["timesheet"].id),
            employee_id=str(row["timesheet"].employee_id),
            employee_name=row["employee_name"],
            project_id=str(row["timesheet"].project_id),
            project_name=row["project_name"],
            period_start=row["timesheet"].period_start,
            period_end=row["timesheet"].period_end,
            status=row["timesheet"].status,
            rejection_reason=row["timesheet"].rejection_reason,
            total_hours=float(row["total_hours"]),
            total_billable_hours=float(row["total_billable_hours"]),
        )
        for row in rows
    ]

@router.post("/{timesheet_id}/approve", response_model=TimesheetOut)
def approve(timesheet_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ts = svc.approve_timesheet(db, user, timesheet_id)
    return TimesheetOut(
        id=str(ts.id),
        employee_id=str(ts.employee_id),
        employee_name=ts.employee_name,
        project_id=str(ts.project_id),
        project_name=_project_name(db, ts.project_id),
        period_start=ts.period_start,
        period_end=ts.period_end,
        status=ts.status,
        rejection_reason=ts.rejection_reason,
    )

@router.post("/{timesheet_id}/reject", response_model=TimesheetOut)
def reject(timesheet_id: str, payload: ApprovalDecisionIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ts = svc.reject_timesheet(db, user, timesheet_id, payload.reason)
    return TimesheetOut(
        id=str(ts.id),
        employee_id=str(ts.employee_id),
        employee_name=ts.employee_name,
        project_id=str(ts.project_id),
        project_name=_project_name(db, ts.project_id),
        period_start=ts.period_start,
        period_end=ts.period_end,
        status=ts.status,
        rejection_reason=ts.rejection_reason,
    )
