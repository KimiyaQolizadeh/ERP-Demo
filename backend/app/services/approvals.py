from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.tables import Project, TimeEntry, Timesheet, User
from app.services import authz


def _summarize_owner_notes(note_texts: list[str], max_len: int = 600) -> str | None:
    unique_notes: list[str] = []
    for raw in note_texts:
        note = str(raw or "").strip()
        if note and note not in unique_notes:
            unique_notes.append(note)
    if not unique_notes:
        return None
    owner_notes = " | ".join(unique_notes)
    if len(owner_notes) > max_len:
        if max_len <= 3:
            return "." * max_len
        return f"{owner_notes[: max_len - 3]}..."
    return owner_notes


def owner_notes_for_timesheet(db: Session, timesheet_id: str) -> str | None:
    rows = (
        db.query(TimeEntry.notes)
        .filter(TimeEntry.timesheet_id == timesheet_id)
        .order_by(TimeEntry.work_date.asc(), TimeEntry.id.asc())
        .all()
    )
    return _summarize_owner_notes([str(row[0] or "") for row in rows])


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

    project_ids = {ts.project_id for ts in rows if getattr(ts, "project_id", None) is not None}
    employee_ids = {ts.employee_id for ts in rows if getattr(ts, "employee_id", None) is not None}
    project_name_by_id: dict[str, str] = {}
    employee_name_by_id: dict[str, str] = {}
    if project_ids:
        project_name_by_id = {
            str(pid): str(pname)
            for pid, pname in db.query(Project.id, Project.project_name).filter(Project.id.in_(project_ids)).all()
        }
    if employee_ids:
        employee_name_by_id = {
            str(uid): str(uname)
            for uid, uname in db.query(User.id, User.name).filter(User.id.in_(employee_ids)).all()
        }

    timesheet_ids = [ts.id for ts in rows]
    note_rows = (
        db.query(TimeEntry.timesheet_id, TimeEntry.notes)
        .filter(TimeEntry.timesheet_id.in_(timesheet_ids))
        .order_by(TimeEntry.timesheet_id.asc(), TimeEntry.work_date.asc(), TimeEntry.id.asc())
        .all()
    )
    notes_by_id: dict[str, list[str]] = {}
    for note_row in note_rows:
        timesheet_id = str(note_row.timesheet_id)
        notes = notes_by_id.setdefault(timesheet_id, [])
        notes.append(str(note_row.notes or ""))

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
    names_backfilled = False
    for ts in rows:
        resolved_employee_name = str(
            ts.employee_name or employee_name_by_id.get(str(ts.employee_id)) or "Unknown employee"
        )
        resolved_project_name = str(project_name_by_id.get(str(ts.project_id)) or "Unknown project")
        if not ts.employee_name and resolved_employee_name != "Unknown employee":
            ts.employee_name = resolved_employee_name
            names_backfilled = True
        totals = aggregate_by_id.get(
            str(ts.id), {"total_hours": 0.0, "total_billable_hours": 0.0}
        )
        owner_notes = _summarize_owner_notes(notes_by_id.get(str(ts.id), []))
        out.append(
            {
                "timesheet": ts,
                "employee_name": resolved_employee_name,
                "project_name": resolved_project_name,
                "owner_notes": owner_notes or None,
                **totals,
            }
        )
    if names_backfilled:
        db.commit()
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
