# backend/app/services/invoicing.py
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.tables import Project, Timesheet, TimeEntry, Invoice, InvoiceLine, RateSchedule, InvoiceAdjustment
from app.services import authz
from app.utils.dates import month_start, next_month_start
from app.utils.money import safe_mul, round_money


def _aggregate_hours_by_discipline(eligible_rows: list[tuple[TimeEntry, Timesheet]]) -> dict[str, float]:
    agg: dict[str, float] = {}
    for entry, ts in eligible_rows:
        # Defense in depth: invoice math must only consider approved, billable,
        # uninvoiced entries even if upstream query constraints change.
        if str(ts.status or "") != "APPROVED":
            continue
        if not bool(entry.billable):
            continue
        if entry.invoiced_line_id is not None:
            continue
        key = str(entry.discipline)
        agg[key] = agg.get(key, 0.0) + float(entry.hours)
    return agg


def _hourly_amount(agg_hours: dict[str, float], rates: dict[str, float]) -> tuple[float, list[dict]]:
    subtotal = 0.0
    lines: list[dict] = []
    for key, hours in agg_hours.items():
        rate = float(rates.get(key, 0.0))
        amount = float(safe_mul(hours, rate))
        subtotal += amount
        lines.append({"rate_key": key, "hours": hours, "rate": rate, "amount": amount})
    return subtotal, lines


def _lump_sum_amount(earned_value: float, approved_budget: float, billed_to_date: float) -> float:
    remaining_contract_value = max(float(approved_budget) - float(billed_to_date), 0.0)
    return min(max(float(earned_value), 0.0), remaining_contract_value)


def _get_invoice_and_project(db: Session, invoice_id: str) -> tuple[Invoice, Project]:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    project = db.query(Project).filter(Project.id == invoice.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return invoice, project


def _require_invoice_project_access(user, project: Project) -> None:
    if not authz.can_draft_invoice(user, project):
        raise HTTPException(status_code=403, detail="Not allowed to access invoice for this project")


def draft_invoice(db: Session, user, project_id: str, month: date):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status not in ("AWARDED", "COMPLETED"):
        raise HTTPException(status_code=400, detail="Project not invoiceable unless Awarded/Completed")

    if not authz.can_draft_invoice(user, project):
        raise HTTPException(status_code=403, detail="Not allowed to draft invoice")

    inv_month = month_start(month)
    next_month = next_month_start(inv_month)

    existing = db.query(Invoice).filter(Invoice.project_id == project_id, Invoice.invoice_month == inv_month).first()
    if existing:
        return existing

    invoice = Invoice(project_id=project_id, invoice_month=inv_month, status="DRAFT")
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    eligible = (
        db.query(TimeEntry, Timesheet)
        .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
        .filter(Timesheet.project_id == project_id)
        .filter(Timesheet.status == "APPROVED")
        .filter(TimeEntry.billable == True)  # noqa: E712
        .filter(TimeEntry.invoiced_line_id.is_(None))
        .filter(TimeEntry.work_date >= inv_month)
        .filter(TimeEntry.work_date < next_month)
        .all()
    )

    rates = {r.rate_key: float(r.rate) for r in db.query(RateSchedule).filter(RateSchedule.project_id == project_id).all()}
    agg = _aggregate_hours_by_discipline(eligible)
    subtotal = 0.0

    if project.contract_type == "LUMP_SUM":
        earned_value, _hourly_lines = _hourly_amount(agg, rates)
        billed_to_date = float(
            db.query(func.coalesce(func.sum(Invoice.subtotal), 0))
            .filter(Invoice.project_id == project_id)
            .filter(Invoice.id != invoice.id)
            .scalar()
        )
        subtotal = _lump_sum_amount(
            earned_value=earned_value,
            approved_budget=float(project.approved_budget),
            billed_to_date=billed_to_date,
        )
        hours_total = float(sum(agg.values()))
        if hours_total > 0 and subtotal > 0:
            effective_rate = subtotal / hours_total
            line = InvoiceLine(
                invoice_id=invoice.id,
                rate_key="LUMP_SUM_PROGRESS",
                hours=hours_total,
                rate=effective_rate,
                amount=subtotal,
            )
            db.add(line)
            db.commit()
            db.refresh(line)
            for entry, _ts in eligible:
                entry.invoiced_line_id = line.id
            db.commit()
    else:
        subtotal, line_payloads = _hourly_amount(agg, rates)
        for row in line_payloads:
            line = InvoiceLine(
                invoice_id=invoice.id,
                rate_key=row["rate_key"],
                hours=row["hours"],
                rate=row["rate"],
                amount=row["amount"],
            )
            db.add(line)
            db.commit()
            db.refresh(line)
            for entry, _ts in eligible:
                if entry.discipline == row["rate_key"]:
                    entry.invoiced_line_id = line.id
            db.commit()

    invoice.subtotal = float(round_money(subtotal))
    invoice.adjustments_total = 0.0
    invoice.total = float(round_money(invoice.subtotal))
    db.commit()
    db.refresh(invoice)
    return invoice

def add_adjustment(db: Session, user, invoice_id: str, description: str, amount: float):
    invoice, project = _get_invoice_and_project(db, invoice_id)
    _require_invoice_project_access(user, project)
    if invoice.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Only draft invoices can be adjusted")

    adj = InvoiceAdjustment(invoice_id=invoice_id, description=description, amount=amount)
    db.add(adj)
    db.commit()

    adjustments_total = float(
        db.query(func.coalesce(func.sum(InvoiceAdjustment.amount), 0))
        .filter(InvoiceAdjustment.invoice_id == invoice_id)
        .scalar()
    )

    invoice.adjustments_total = float(round_money(adjustments_total))
    invoice.total = float(round_money(float(invoice.subtotal) + float(invoice.adjustments_total)))
    db.commit()
    db.refresh(invoice)
    return invoice

def approve_invoice(db: Session, user, invoice_id: str):
    if not authz.can_approve_invoice(user):
        raise HTTPException(status_code=403, detail="Only finance can approve invoice")

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Only draft invoices can be approved")

    invoice.status = "APPROVED"
    invoice.approved_at = datetime.utcnow()
    invoice.approved_by_finance = user.id
    db.commit()
    db.refresh(invoice)
    return invoice

def export_invoice(db: Session, user, invoice_id: str) -> dict:
    invoice, project = _get_invoice_and_project(db, invoice_id)
    _require_invoice_project_access(user, project)
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice_id).all()
    adjs = db.query(InvoiceAdjustment).filter(InvoiceAdjustment.invoice_id == invoice_id).all()

    return {
        "invoice_id": str(invoice.id),
        "project_id": str(invoice.project_id),
        "contract_type": project.contract_type if project else None,
        "invoice_month": str(invoice.invoice_month),
        "status": invoice.status,
        "subtotal": float(invoice.subtotal),
        "adjustments_total": float(invoice.adjustments_total),
        "total": float(invoice.total),
        "lines": [{"rate_key": l.rate_key, "hours": float(l.hours), "rate": float(l.rate), "amount": float(l.amount)} for l in lines],
        "adjustments": [{"description": a.description, "amount": float(a.amount)} for a in adjs],
    }
