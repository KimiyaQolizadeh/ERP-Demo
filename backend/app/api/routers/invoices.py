from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.schemas import InvoiceDraftOut, AdjustmentIn
from app.services import invoicing as svc
from app.models.tables import InvoiceLine

router = APIRouter(prefix="/invoices", tags=["invoices"])

@router.post("/draft", response_model=InvoiceDraftOut)
def draft(project_id: str, month: date, db: Session = Depends(get_db), user=Depends(get_current_user)):
    inv = svc.draft_invoice(db, user, project_id, month)
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == inv.id).all()
    return InvoiceDraftOut(
        invoice_id=str(inv.id),
        project_id=str(inv.project_id),
        invoice_month=inv.invoice_month,
        status=inv.status,
        subtotal=float(inv.subtotal),
        adjustments_total=float(inv.adjustments_total),
        total=float(inv.total),
        lines=[{"rate_key": l.rate_key, "hours": float(l.hours), "rate": float(l.rate), "amount": float(l.amount)} for l in lines],
    )

@router.patch("/{invoice_id}/adjustments", response_model=InvoiceDraftOut)
def add_adjustment(invoice_id: str, payload: AdjustmentIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    inv = svc.add_adjustment(db, user, invoice_id, payload.description, payload.amount)
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == inv.id).all()
    return InvoiceDraftOut(
        invoice_id=str(inv.id),
        project_id=str(inv.project_id),
        invoice_month=inv.invoice_month,
        status=inv.status,
        subtotal=float(inv.subtotal),
        adjustments_total=float(inv.adjustments_total),
        total=float(inv.total),
        lines=[{"rate_key": l.rate_key, "hours": float(l.hours), "rate": float(l.rate), "amount": float(l.amount)} for l in lines],
    )

@router.post("/{invoice_id}/approve")
def approve(invoice_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    inv = svc.approve_invoice(db, user, invoice_id)
    return {"invoice_id": str(inv.id), "status": inv.status}

@router.get("/{invoice_id}/export")
def export(invoice_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return svc.export_invoice(db, user, invoice_id)