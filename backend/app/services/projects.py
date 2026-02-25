from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.tables import Project, RateSchedule, Timesheet, User
from app.services import authz

ALLOWED_DIVISIONS = {"ICI", "Cx", "SD"}
ALLOWED_STATUSES = {"PROPOSAL", "AWARDED", "COMPLETED", "CANCELLED", "NOT_AWARDED"}
ALLOWED_CONTRACT_TYPES = {"HOURLY", "LUMP_SUM"}
DEFAULT_RATE_SCHEDULE = {
    "Mechanical": 140.0,
    "Electrical": 160.0,
    "Civil": 130.0,
    "PM": 180.0,
}


def _required_text(value: str, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return cleaned


def _validate_division(division: str) -> str:
    value = str(division or "").strip()
    if value not in ALLOWED_DIVISIONS:
        raise HTTPException(status_code=400, detail=f"division must be one of {sorted(ALLOWED_DIVISIONS)}")
    return value


def _validate_status(status: str) -> str:
    value = str(status or "").strip().upper()
    if value not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")
    return value


def _validate_contract_type(contract_type: str) -> str:
    value = str(contract_type or "").strip().upper()
    if value not in ALLOWED_CONTRACT_TYPES:
        raise HTTPException(status_code=400, detail=f"contract_type must be one of {sorted(ALLOWED_CONTRACT_TYPES)}")
    return value


def _validate_project_window(start_date, end_date) -> None:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")


def _normalize_not_awarded_reason(status: str, reason: str | None) -> str | None:
    if status != "NOT_AWARDED":
        return None
    cleaned = str(reason or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="not_awarded_reason is required when status is NOT_AWARDED")
    return cleaned


def _validate_rate_inputs(rates: list[dict]) -> list[dict]:
    if not rates:
        rates = [{"rate_key": key, "rate": value} for key, value in DEFAULT_RATE_SCHEDULE.items()]
    cleaned: list[dict] = []
    seen: set[str] = set()
    for item in rates:
        key = str(item.get("rate_key", "")).strip()
        if not key:
            raise HTTPException(status_code=400, detail="rate_key cannot be empty")
        key_norm = key.lower()
        if key_norm in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate rate_key: {key}")
        seen.add(key_norm)
        try:
            rate = float(item.get("rate", 0))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid rate for rate_key={key}")
        if rate <= 0:
            raise HTTPException(status_code=400, detail=f"rate must be > 0 for rate_key={key}")
        cleaned.append({"rate_key": key, "rate": rate})
    return cleaned


def _ensure_pm_user(db: Session, pm_user_id: str) -> User:
    user = db.query(User).filter(User.id == pm_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Assigned PM user not found")
    if user.role not in {"PM", "ADMIN"}:
        raise HTTPException(status_code=400, detail="Assigned PM user must have PM role")
    return user


def _ensure_project(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _can_manage_project(user, project: Project) -> bool:
    return authz.is_admin(user) or (authz.is_pm(user) and str(project.pm_user_id) == str(user.id))


def _is_employee_linked_to_project(db: Session, user_id: str, project_id: str) -> bool:
    linked = (
        db.query(Timesheet.id)
        .filter(Timesheet.employee_id == user_id)
        .filter(Timesheet.project_id == project_id)
        .first()
    )
    return linked is not None


def list_projects(db: Session, user, status: str | None = None, pm_user_id: str | None = None) -> list[Project]:
    q = db.query(Project)
    if authz.is_pm(user) and not authz.is_finance(user):
        q = q.filter(Project.pm_user_id == user.id)
    elif authz.is_employee(user) and not authz.is_finance(user):
        q = (
            q.join(Timesheet, Timesheet.project_id == Project.id)
            .filter(Timesheet.employee_id == user.id)
            .distinct()
        )
    if status:
        q = q.filter(Project.status == _validate_status(status))
    if pm_user_id:
        q = q.filter(Project.pm_user_id == pm_user_id)
    return q.order_by(Project.project_name.asc()).all()


def get_project(db: Session, user, project_id: str) -> Project:
    project = _ensure_project(db, project_id)
    linked = _is_employee_linked_to_project(db, str(user.id), project_id)
    if not authz.can_view_project(user, project, linked_to_project=linked):
        raise HTTPException(status_code=403, detail="Project is outside your role scope")
    return project


def get_project_rates(db: Session, user, project_id: str) -> list[RateSchedule]:
    _ = get_project(db, user, project_id)
    rows = db.query(RateSchedule).filter(RateSchedule.project_id == project_id).order_by(RateSchedule.rate_key.asc()).all()
    return list(rows)


def create_project(db: Session, user, payload) -> Project:
    if not authz.is_pm(user):
        raise HTTPException(status_code=403, detail="Only PM or ADMIN can create projects")

    pm_user = _ensure_pm_user(db, payload.pm_user_id)
    status = _validate_status(payload.status)
    contract_type = _validate_contract_type(payload.contract_type)
    division = _validate_division(payload.division)
    _validate_project_window(payload.start_date, payload.end_date)
    reason = _normalize_not_awarded_reason(status, payload.not_awarded_reason)

    project = Project(
        project_name=_required_text(payload.project_name, "project_name"),
        client_name=_required_text(payload.client_name, "client_name"),
        division=division,
        discipline=_required_text(payload.discipline, "discipline"),
        pm_user_id=pm_user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        contract_type=contract_type,
        approved_budget=float(payload.approved_budget),
        status=status,
        not_awarded_reason=reason,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    rates = _validate_rate_inputs([r.model_dump() for r in payload.rates])
    for item in rates:
        db.add(
            RateSchedule(
                project_id=project.id,
                rate_key=item["rate_key"],
                rate=item["rate"],
            )
        )
    db.commit()
    return _ensure_project(db, str(project.id))


def update_project(db: Session, user, project_id: str, payload) -> Project:
    project = _ensure_project(db, project_id)
    if not _can_manage_project(user, project):
        raise HTTPException(status_code=403, detail="Only assigned PM or ADMIN can update this project")

    next_project_name = (
        _required_text(payload.project_name, "project_name") if payload.project_name is not None else project.project_name
    )
    next_client_name = (
        _required_text(payload.client_name, "client_name") if payload.client_name is not None else project.client_name
    )
    next_division = _validate_division(payload.division) if payload.division is not None else project.division
    next_discipline = _required_text(payload.discipline, "discipline") if payload.discipline is not None else project.discipline

    next_pm_user_id = payload.pm_user_id if payload.pm_user_id is not None else project.pm_user_id
    if payload.pm_user_id is not None:
        next_pm_user_id = _ensure_pm_user(db, payload.pm_user_id).id

    next_start = payload.start_date if payload.start_date is not None else project.start_date
    next_end = payload.end_date if payload.end_date is not None else project.end_date
    _validate_project_window(next_start, next_end)

    next_contract = (
        _validate_contract_type(payload.contract_type) if payload.contract_type is not None else project.contract_type
    )
    next_budget = float(payload.approved_budget) if payload.approved_budget is not None else float(project.approved_budget)
    next_status = _validate_status(payload.status) if payload.status is not None else project.status

    current_reason = project.not_awarded_reason
    explicit_reason = payload.not_awarded_reason if payload.not_awarded_reason is not None else current_reason
    next_reason = _normalize_not_awarded_reason(next_status, explicit_reason)

    project.project_name = next_project_name
    project.client_name = next_client_name
    project.division = next_division
    project.discipline = next_discipline
    project.pm_user_id = next_pm_user_id
    project.start_date = next_start
    project.end_date = next_end
    project.contract_type = next_contract
    project.approved_budget = next_budget
    project.status = next_status
    project.not_awarded_reason = next_reason

    db.commit()
    db.refresh(project)
    return project


def replace_project_rates(db: Session, user, project_id: str, rates: list[dict]) -> list[RateSchedule]:
    project = _ensure_project(db, project_id)
    if not _can_manage_project(user, project):
        raise HTTPException(status_code=403, detail="Only assigned PM or ADMIN can update rates")

    cleaned = _validate_rate_inputs(rates)
    db.query(RateSchedule).filter(RateSchedule.project_id == project_id).delete()
    for item in cleaned:
        db.add(
            RateSchedule(
                project_id=project.id,
                rate_key=item["rate_key"],
                rate=item["rate"],
            )
        )
    db.commit()
    return get_project_rates(db, user, project_id)
