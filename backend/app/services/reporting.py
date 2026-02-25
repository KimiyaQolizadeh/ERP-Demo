# backend/app/services/reporting.py
from datetime import date
import math
from sqlalchemy.orm import Session

from app.models.tables import Project, RateSchedule, Timesheet, TimeEntry, User
from app.services import authz
from app.utils.dates import month_start, next_month_start
from app.utils.money import safe_mul, round_money


def _rates_for_project(db: Session, project_id: str) -> dict[str, float]:
    rates = db.query(RateSchedule).filter(RateSchedule.project_id == project_id).all()
    return {r.rate_key: float(r.rate) for r in rates}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _month_shift(value: date, months: int) -> date:
    year = value.year + ((value.month - 1 + months) // 12)
    month = ((value.month - 1 + months) % 12) + 1
    return date(year, month, 1)


def _invoice_readiness_totals(rows: list[tuple[TimeEntry, Timesheet]]) -> tuple[float, float, float]:
    submitted_billable = 0.0
    approved_billable = 0.0
    for entry, ts in rows:
        hours = float(entry.hours or 0.0)
        status = str(ts.status or "")
        if status in ("SUBMITTED", "APPROVED"):
            submitted_billable += hours
        if status == "APPROVED":
            approved_billable += hours
    readiness = (approved_billable / submitted_billable) if submitted_billable > 0 else 0.0
    return submitted_billable, approved_billable, readiness


def _scoped_projects(db: Session, user=None) -> list[Project]:
    q = db.query(Project)
    if user is None:
        return q.all()
    if authz.is_finance(user):
        return q.all()
    if authz.is_pm(user):
        return q.filter(Project.pm_user_id == user.id).all()
    return (
        q.join(Timesheet, Timesheet.project_id == Project.id)
        .filter(Timesheet.employee_id == user.id)
        .distinct()
        .all()
    )


def _project_metric_for_month(db: Session, month: date, metric: str, user=None) -> list[dict]:
    ms = month_start(month)
    me = next_month_start(ms)
    projects = _scoped_projects(db, user)
    out: list[dict] = []
    for p in projects:
        rates = _rates_for_project(db, str(p.id))
        rows = (
            db.query(TimeEntry, Timesheet)
            .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
            .filter(Timesheet.project_id == p.id)
            .filter(Timesheet.status == "APPROVED")
            .filter(TimeEntry.work_date >= ms)
            .filter(TimeEntry.work_date < me)
            .all()
        )
        spend = 0.0
        for e, _ts in rows:
            if e.billable:
                spend += float(safe_mul(float(e.hours), rates.get(e.discipline, 0.0)))
        if metric == "burn_rate":
            days = max((me - ms).days, 1)
            value = float(round_money(spend / days))
        else:
            value = float(round_money(spend))
        out.append(
            {
                "project_id": str(p.id),
                "project_name": p.project_name,
                "value": value,
            }
        )
    return out


def dashboard(db: Session, month: date, user=None):
    """
    Dashboard returns project health + utilization.
    Now includes real burn-rate forecast based on:
      burn_rate_per_day = spend_to_date / days_elapsed
      forecast_total = burn_rate_per_day * total_days
    spend_to_date is computed from APPROVED timesheets up to end of month (me).
    """
    ms = month_start(month)
    me = next_month_start(ms)

    projects = _scoped_projects(db, user)
    out_projects = []

    for p in projects:
        rates = _rates_for_project(db, str(p.id))

        # Entries up to end of month (me)
        rows = (
            db.query(TimeEntry, Timesheet)
            .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
            .filter(Timesheet.project_id == p.id)
            .filter(Timesheet.status == "APPROVED")
            .filter(TimeEntry.work_date < me)
            .all()
        )

        billable_hours = 0.0
        nonbillable_hours = 0.0
        spend = 0.0

        for e, _ts in rows:
            h = float(e.hours)
            if e.billable:
                billable_hours += h
                spend += float(safe_mul(h, rates.get(e.discipline, 0.0)))
            else:
                nonbillable_hours += h

        budget = float(p.approved_budget)
        percent_budget = (spend / budget * 100.0) if budget > 0 else 0.0
        remaining = budget - spend

        # ---- Burn rate + forecast ----
        # Use project start/end dates
        # days_elapsed: from start_date to min(me, today or end_date)
        # For simplicity in take-home, use "me" as "current date marker" for the month.
        start = p.start_date
        end = p.end_date
        total_days = max((end - start).days, 1)

        current_marker = min(me, end)  # marker inside project timeframe
        days_elapsed = max((current_marker - start).days, 1)

        percent_time_elapsed = (days_elapsed / total_days) * 100.0

        burn_rate_per_day = spend / days_elapsed  # $/day
        forecast_total = burn_rate_per_day * total_days
        forecast_vs_budget_pct = (forecast_total / budget * 100.0) if budget > 0 else 0.0

        # Nonbillable ratio (hours-based)
        total_hours = billable_hours + nonbillable_hours
        nonbillable_ratio_pct = (nonbillable_hours / total_hours * 100.0) if total_hours > 0 else 0.0

        out_projects.append({
            "project_id": str(p.id),
            "project_name": p.project_name,
            "client_name": p.client_name,
            "division": p.division,
            "discipline": p.discipline,
            "contract_type": p.contract_type,
            "status": p.status,

            "start_date": str(p.start_date),
            "end_date": str(p.end_date),

            "budget": float(round_money(budget)),
            "spend_to_date": float(round_money(spend)),
            "billable_hours": round(billable_hours, 2),
            "nonbillable_hours": round(nonbillable_hours, 2),

            "percent_budget_consumed": round(percent_budget, 1),
            "remaining_budget": float(round_money(remaining)),

            "percent_time_elapsed": round(percent_time_elapsed, 1),
            "burn_rate_per_day": float(round_money(burn_rate_per_day)),
            "forecast_total": float(round_money(forecast_total)),
            "forecast_vs_budget_pct": round(forecast_vs_budget_pct, 1),

            "nonbillable_ratio_pct": round(nonbillable_ratio_pct, 1),
        })

    # utilization by employee (month window)
    utilization = []
    project_ids = [p.id for p in projects]
    if user is not None and authz.is_employee(user) and not authz.is_finance(user):
        employees = [user]
    else:
        scoped_user_rows = (
            db.query(Timesheet.employee_id)
            .filter(Timesheet.project_id.in_(project_ids))
            .distinct()
            .all()
            if project_ids
            else []
        )
        scoped_user_ids = [uid for (uid,) in scoped_user_rows if uid is not None]
        employees = db.query(User).filter(User.id.in_(scoped_user_ids)).all() if scoped_user_ids else []
    for u in employees:
        rows = (
            db.query(TimeEntry, Timesheet)
            .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
            .filter(Timesheet.employee_id == u.id)
            .filter(Timesheet.project_id.in_(project_ids))
            .filter(TimeEntry.work_date >= ms)
            .filter(TimeEntry.work_date < me)
            .all()
        )
        total = sum(float(e.hours) for e, _ in rows)
        bill = sum(float(e.hours) for e, _ in rows if e.billable)
        util = (bill / total) if total > 0 else 0.0
        utilization.append({
            "user_id": str(u.id),
            "name": u.name,
            "role": u.role,
            "utilization_pct": round(util * 100, 1)
        })

    return {"month": str(ms), "projects": out_projects, "utilization": utilization}


def invoice_readiness(db: Session, month: date, user=None):
    ms = month_start(month)
    me = next_month_start(ms)

    projects = _scoped_projects(db, user)
    out = []

    for p in projects:
        rows = (
            db.query(TimeEntry, Timesheet)
            .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
            .filter(Timesheet.project_id == p.id)
            .filter(TimeEntry.billable == True)  # noqa: E712
            .filter(TimeEntry.work_date >= ms, TimeEntry.work_date < me)
            .all()
        )

        submitted_billable, approved_billable, readiness = _invoice_readiness_totals(rows)
        out.append({
            "project_id": str(p.id),
            "project_name": p.project_name,
            "submitted_billable_hours": round(submitted_billable, 2),
            "approved_billable_hours": round(approved_billable, 2),
            "readiness_pct": round(readiness * 100, 1),
        })

    return {"month": str(ms), "projects": out}


def anomalies(db: Session, month: date, metric: str, user=None):
    if metric not in {"spend_to_date", "burn_rate"}:
        raise ValueError("metric must be spend_to_date or burn_rate")

    current_rows = _project_metric_for_month(db, month, metric, user=user)
    prev_1 = _project_metric_for_month(db, _month_shift(month, -1), metric, user=user)
    prev_2 = _project_metric_for_month(db, _month_shift(month, -2), metric, user=user)
    prev_3 = _project_metric_for_month(db, _month_shift(month, -3), metric, user=user)

    history_map: dict[str, list[float]] = {}
    for batch in (prev_1, prev_2, prev_3):
        for row in batch:
            history_map.setdefault(row["project_id"], []).append(float(row["value"]))

    anomalies_out: list[dict] = []
    for row in current_rows:
        project_id = row["project_id"]
        project_name = row["project_name"]
        current_value = float(row["value"])
        baseline_vals = [float(v) for v in history_map.get(project_id, []) if v is not None]
        if not baseline_vals:
            continue
        baseline_avg = sum(baseline_vals) / len(baseline_vals)
        variance = sum((v - baseline_avg) ** 2 for v in baseline_vals) / max(len(baseline_vals), 1)
        baseline_std = math.sqrt(variance)
        delta_pct = ((current_value - baseline_avg) / baseline_avg * 100.0) if baseline_avg > 0 else None
        z_score = ((current_value - baseline_avg) / baseline_std) if baseline_std > 0 else None

        flagged = False
        if delta_pct is not None and abs(delta_pct) >= 25.0:
            flagged = True
        if z_score is not None and abs(z_score) >= 1.5:
            flagged = True
        if not flagged:
            continue

        anomalies_out.append(
            {
                "project_id": project_id,
                "project_name": project_name,
                "metric": metric,
                "month": str(month_start(month)),
                "current_value": round(current_value, 2),
                "baseline_avg_last_3_months": round(baseline_avg, 2),
                "delta_pct": round(delta_pct, 2) if delta_pct is not None else None,
                "z_score": round(z_score, 3) if z_score is not None else None,
                "severity": "high"
                if (abs(delta_pct or 0.0) >= 40.0 or abs(z_score or 0.0) >= 2.5)
                else "medium",
            }
        )

    anomalies_out.sort(
        key=lambda item: (
            abs(float(item.get("delta_pct") or 0.0)),
            abs(float(item.get("z_score") or 0.0)),
        ),
        reverse=True,
    )

    return {
        "month": str(month_start(month)),
        "metric": metric,
        "anomalies": anomalies_out,
    }
