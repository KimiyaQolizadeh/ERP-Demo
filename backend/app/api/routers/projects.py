from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.schemas import (
    ProjectCreateIn,
    ProjectDetailOut,
    ProjectOut,
    ProjectUpdateIn,
    RateScheduleIn,
    RateScheduleOut,
)
from app.services import projects as svc
from app.services import project_health as health_svc

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectHealthQueryIn(BaseModel):
    bucket_days: int = 14
    lookback_buckets: int = 12
    start_date: date | None = None
    end_date: date | None = None
    approved_only: bool = True


def _to_project_out(project) -> ProjectOut:
    return ProjectOut(
        id=str(project.id),
        project_name=project.project_name,
        client_name=project.client_name,
        division=project.division,
        discipline=project.discipline,
        pm_user_id=str(project.pm_user_id),
        start_date=project.start_date,
        end_date=project.end_date,
        contract_type=project.contract_type,
        approved_budget=float(project.approved_budget),
        status=project.status,
        not_awarded_reason=project.not_awarded_reason,
    )


def _to_rate_out(rate) -> RateScheduleOut:
    return RateScheduleOut(
        id=str(rate.id),
        project_id=str(rate.project_id),
        rate_key=rate.rate_key,
        rate=float(rate.rate),
    )


def _to_project_detail_out(project, rates) -> ProjectDetailOut:
    base = _to_project_out(project)
    return ProjectDetailOut(**base.model_dump(), rates=[_to_rate_out(r) for r in rates])


@router.get("", response_model=list[ProjectOut])
def list_projects(
    status: str | None = None,
    pm_user_id: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = svc.list_projects(db, user, status=status, pm_user_id=pm_user_id)
    return [_to_project_out(p) for p in rows]


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = svc.get_project(db, user, project_id)
    rates = svc.get_project_rates(db, user, project_id)
    return _to_project_detail_out(p, rates)


@router.get("/{project_id}/health")
def get_project_health(
    project_id: str,
    bucket_days: int = 14,
    lookback_buckets: int = 12,
    start_date: date | None = None,
    end_date: date | None = None,
    approved_only: bool = True,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return health_svc.compute_project_health(
        db,
        project_id,
        user_obj=user,
        bucket_days=bucket_days,
        lookback_buckets=lookback_buckets,
        start_date=start_date,
        end_date=end_date,
        approved_only=approved_only,
    )


@router.post("/{project_id}/risk-explanation")
def get_project_risk_explanation(
    project_id: str,
    payload: ProjectHealthQueryIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return health_svc.build_project_risk_explanation(
        db,
        project_id,
        user_obj=user,
        bucket_days=payload.bucket_days,
        lookback_buckets=payload.lookback_buckets,
        start_date=payload.start_date,
        end_date=payload.end_date,
        approved_only=payload.approved_only,
    )


@router.post("", response_model=ProjectDetailOut)
def create_project(payload: ProjectCreateIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = svc.create_project(db, user, payload)
    rates = svc.get_project_rates(db, user, str(p.id))
    return _to_project_detail_out(p, rates)


@router.patch("/{project_id}", response_model=ProjectDetailOut)
def update_project(
    project_id: str,
    payload: ProjectUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    p = svc.update_project(db, user, project_id, payload)
    rates = svc.get_project_rates(db, user, project_id)
    return _to_project_detail_out(p, rates)


@router.get("/{project_id}/rates", response_model=list[RateScheduleOut])
def get_rates(project_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = svc.get_project_rates(db, user, project_id)
    return [_to_rate_out(r) for r in rows]


@router.put("/{project_id}/rates", response_model=list[RateScheduleOut])
def replace_rates(
    project_id: str,
    payload: list[RateScheduleIn],
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    rows = svc.replace_project_rates(db, user, project_id, [r.model_dump() for r in payload])
    return [_to_rate_out(r) for r in rows]
