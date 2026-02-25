from datetime import date
from fastapi import APIRouter, Depends
from typing import Literal
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user
from app.services import reporting as svc

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/dashboard")
def dashboard(month: date, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return svc.dashboard(db, month, user=user)

@router.get("/invoice-readiness")
def readiness(month: date, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return svc.invoice_readiness(db, month, user=user)


@router.get("/anomalies")
def anomalies(
    month: date,
    metric: Literal["spend_to_date", "burn_rate"] = "spend_to_date",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return svc.anomalies(db, month=month, metric=metric, user=user)
