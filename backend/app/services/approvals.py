from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.tables import Project, TimeEntry, Timesheet
from app.services import authz


def _get_timesheet_and_project(db: Session, timesheet_id: str) -> tuple[Timesheet, Project]:
    row = (
        db.query(Timesheet, Project)
        .join(Project, Project.id == Timesheet.project_id)
        .filter(Timesheet.id == timesheet_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    return row


def list_pending_for_pm(db: Session, user) -> list[Timesheet]:
    if not authz.is_pm(user):
        raise HTTPException(status_code=403, detail="Only PM can view pending approvals")

    rows = (
        db.query(Timesheet)
        .join(Project, Project.id == Timesheet.project_id)
        .filter(Project.pm_user_id == user.id)
        .filter(Timesheet.status == "SUBMITTED")
        .order_by(Timesheet.submitted_at.desc(), Timesheet.period_end.desc())
        .all()
    )
    return list(rows)


def list_pending_for_pm_with_hours(db: Session, user) -> list[dict]:
    rows = list_pending_for_pm(db, user)
    if not rows:
        return []

    timesheet_ids = [ts.id for ts in rows]
    aggregates = (
        db.query(
            TimeEntry.timesheet_id.label("timesheet_id"),
            func.coalesce(func.sum(TimeEntry.hours), 0).label("total_hours"),
            func.coalesce(
                func.sum(
                    case(
                        (TimeEntry.billable.is_(True), TimeEntry.hours),
                        else_=0,
                    )
                ),
                0,
            ).label("total_billable_hours"),
        )
        .filter(TimeEntry.timesheet_id.in_(timesheet_ids))
        .group_by(TimeEntry.timesheet_id)
        .all()
    )
    aggregate_by_id = {
        str(row.timesheet_id): {
            "total_hours": float(row.total_hours or 0.0),
            "total_billable_hours": float(row.total_billable_hours or 0.0),
        }
        for row in aggregates
    }

    out: list[dict] = []
    for ts in rows:
        totals = aggregate_by_id.get(
            str(ts.id), {"total_hours": 0.0, "total_billable_hours": 0.0}
        )
        out.append({"timesheet": ts, **totals})
    return out


def approve_timesheet(db: Session, user, timesheet_id: str) -> Timesheet:
    ts, project = _get_timesheet_and_project(db, timesheet_id)
    if not authz.can_approve_timesheet(user, project):
        raise HTTPException(status_code=403, detail="Only project PM can approve submitted timesheets")
    if ts.status != "SUBMITTED":
        raise HTTPException(status_code=400, detail="Only submitted timesheets can be approved")

    ts.status = "APPROVED"
    ts.decided_at = datetime.utcnow()
    ts.decided_by_pm = user.id
    ts.rejection_reason = None
    db.commit()
    db.refresh(ts)
    return ts


def reject_timesheet(db: Session, user, timesheet_id: str, reason: str | None) -> Timesheet:
    ts, project = _get_timesheet_and_project(db, timesheet_id)
    if not authz.can_approve_timesheet(user, project):
        raise HTTPException(status_code=403, detail="Only project PM can reject submitted timesheets")
    if ts.status != "SUBMITTED":
        raise HTTPException(status_code=400, detail="Only submitted timesheets can be rejected")

    ts.status = "REJECTED"
    ts.decided_at = datetime.utcnow()
    ts.decided_by_pm = user.id
    ts.rejection_reason = reason or "Rejected by project manager"
    db.commit()
    db.refresh(ts)
    return ts
