from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_openai_api_key, get_openai_model
from app.models.tables import Project, RateSchedule, TimeEntry, Timesheet, User
from app.services import authz

DEFAULT_COST_RATE = 65.0
DEFAULT_REVENUE_RATE = 120.0
DEFAULT_FORECAST_POINTS = 6
ALLOWED_BUCKET_DAYS = {7, 14, 28}
ALLOWED_LOOKBACK_BUCKETS = {8, 12, 16}


class DriverOut(BaseModel):
    title: str
    evidence: str
    metric_refs: list[str]


class RecommendedActionOut(BaseModel):
    action: str
    owner: Literal["PM", "Finance", "Ops"]
    why: str


class RiskExplanationOut(BaseModel):
    risk_level: Literal["GREEN", "AMBER", "RED"]
    score: float
    summary: str
    top_drivers: list[DriverOut]
    recommended_actions: list[RecommendedActionOut]
    assumptions: list[str]
    data_quality_flags: list[str]


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except Exception:
            return None
    return None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_percent(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return (numerator / denominator) * 100.0


def _to_iso_z(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


def _ensure_project(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _authorize_project_access(db: Session, project: Project, user_obj: Any) -> None:
    if authz.is_admin(user_obj) or authz.is_finance(user_obj):
        return
    if authz.is_pm(user_obj):
        if str(project.pm_user_id) == str(user_obj.id):
            return
        raise HTTPException(status_code=403, detail="Project is outside your role scope")

    linked = (
        db.query(Timesheet.id)
        .filter(Timesheet.project_id == project.id)
        .filter(Timesheet.employee_id == user_obj.id)
        .first()
    )
    if not linked:
        raise HTTPException(status_code=403, detail="Project is outside your role scope")


def _build_bucket_windows(
    *,
    bucket_days: int,
    lookback_buckets: int,
    today: date,
    start_date: date | None,
    end_date: date | None,
) -> list[tuple[date, date]]:
    if bucket_days not in ALLOWED_BUCKET_DAYS:
        raise HTTPException(status_code=400, detail=f"bucket_days must be one of {sorted(ALLOWED_BUCKET_DAYS)}")
    if lookback_buckets not in ALLOWED_LOOKBACK_BUCKETS:
        raise HTTPException(
            status_code=400,
            detail=f"lookback_buckets must be one of {sorted(ALLOWED_LOOKBACK_BUCKETS)}",
        )

    if start_date and end_date:
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start_date must be <= end_date")
        buckets: list[tuple[date, date]] = []
        cursor = start_date
        while cursor <= end_date:
            bucket_end = min(cursor + timedelta(days=bucket_days - 1), end_date)
            buckets.append((cursor, bucket_end))
            cursor = bucket_end + timedelta(days=1)
        return buckets

    if start_date and not end_date:
        end_date = today
    if end_date and not start_date:
        start_date = end_date - timedelta(days=(bucket_days * lookback_buckets) - 1)

    if not start_date or not end_date:
        end_date = today
        start_date = end_date - timedelta(days=(bucket_days * lookback_buckets) - 1)

    buckets = []
    cursor = start_date
    while cursor <= end_date:
        bucket_end = min(cursor + timedelta(days=bucket_days - 1), end_date)
        buckets.append((cursor, bucket_end))
        cursor = bucket_end + timedelta(days=1)
    return buckets


def _rate_lookup(db: Session, project_id: str) -> dict[str, float]:
    rows = db.query(RateSchedule).filter(RateSchedule.project_id == project_id).all()
    out: dict[str, float] = {}
    for row in rows:
        out[str(row.rate_key).strip()] = float(row.rate)
    return out


def _entry_cost(entry: TimeEntry, rates: dict[str, float], data_quality_flags: set[str]) -> float:
    rate = rates.get(str(entry.discipline))
    if rate is None:
        rate = DEFAULT_COST_RATE
        data_quality_flags.add("default_cost_rate_used")
    return float(entry.hours) * float(rate)


def _entry_revenue(entry: TimeEntry, rates: dict[str, float], data_quality_flags: set[str]) -> float:
    if not bool(entry.billable):
        return 0.0
    rate = rates.get(str(entry.discipline))
    if rate is None:
        rate = DEFAULT_REVENUE_RATE
        data_quality_flags.add("default_revenue_rate_used")
    return float(entry.hours) * float(rate)


def _estimate_forecast(
    *,
    bucket_days: int,
    cumulative_values: list[float],
    bucket_values: list[float],
    last_actual_date: date,
    end_date: date,
) -> tuple[str, float | None, list[tuple[date, float]]]:
    if not cumulative_values:
        return "moving_average", 0.0, []

    last_idx = len(cumulative_values) - 1
    remaining_days = max((end_date - last_actual_date).days, 0)
    remaining_buckets = int(math.ceil(remaining_days / bucket_days)) if remaining_days > 0 else 0
    target_idx = last_idx + remaining_buckets
    last_cumulative = float(cumulative_values[-1])

    series: list[tuple[date, float]] = [(last_actual_date, last_cumulative)]

    def moving_average_forecast() -> tuple[str, float, list[tuple[date, float]]]:
        n_points = min(DEFAULT_FORECAST_POINTS, len(bucket_values))
        avg_bucket = (sum(bucket_values[-n_points:]) / n_points) if n_points > 0 else 0.0
        points = [(last_actual_date, last_cumulative)]
        for step in range(1, remaining_buckets + 1):
            point_date = min(last_actual_date + timedelta(days=step * bucket_days), end_date)
            points.append((point_date, max(last_cumulative, last_cumulative + (avg_bucket * step))))
        if remaining_buckets == 0:
            return "moving_average", last_cumulative, points
        return "moving_average", float(points[-1][1]), points

    n_reg = min(DEFAULT_FORECAST_POINTS, len(cumulative_values))
    if n_reg < 2:
        return moving_average_forecast()

    x = list(range(len(cumulative_values) - n_reg, len(cumulative_values)))
    y = [float(v) for v in cumulative_values[-n_reg:]]

    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    denom = sum((xi - mean_x) ** 2 for xi in x)
    if denom <= 0:
        return moving_average_forecast()

    slope = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / denom
    intercept = mean_y - (slope * mean_x)

    predicted_total = max(last_cumulative, (slope * target_idx) + intercept)
    for step in range(1, remaining_buckets + 1):
        point_date = min(last_actual_date + timedelta(days=step * bucket_days), end_date)
        point_idx = last_idx + step
        predicted_value = max(last_cumulative, (slope * point_idx) + intercept)
        series.append((point_date, float(predicted_value)))

    return "regression", float(predicted_total), series


def _series_increment(series: list[tuple[date, float]]) -> float:
    if len(series) < 2:
        return 0.0
    deltas = [float(series[idx][1] - series[idx - 1][1]) for idx in range(1, len(series))]
    tail = deltas[-3:] if len(deltas) >= 3 else deltas
    if not tail:
        return 0.0
    return max(0.0, sum(tail) / len(tail))


def _extend_cost_forecast_for_budget(
    *,
    cost_forecast_pairs: list[tuple[date, float]],
    bucket_days: int,
    budget: float | None,
    fallback_increment: float = 0.0,
    max_extra_buckets: int = 78,
) -> list[tuple[date, float]]:
    if not cost_forecast_pairs:
        return []
    if budget is None or budget <= 0:
        return list(cost_forecast_pairs)

    extended = list(cost_forecast_pairs)
    increment = _series_increment(extended)
    if increment <= 0:
        increment = max(0.0, float(fallback_increment))
    if increment <= 0:
        return extended

    while len(extended) < (len(cost_forecast_pairs) + max_extra_buckets):
        last_date, last_value = extended[-1]
        if last_value >= budget:
            break
        next_date = last_date + timedelta(days=bucket_days)
        next_value = last_value + increment
        extended.append((next_date, float(next_value)))
    return extended


def _align_revenue_with_cost_dates(
    *,
    cost_pairs: list[tuple[date, float]],
    revenue_pairs: list[tuple[date, float]],
    bucket_days: int,
    fallback_increment: float = 0.0,
) -> list[tuple[date, float]]:
    if not cost_pairs:
        return []
    if not revenue_pairs:
        return [(point_date, 0.0) for point_date, _ in cost_pairs]

    by_date = {point_date: float(value) for point_date, value in revenue_pairs}
    increment = _series_increment(revenue_pairs)
    if increment <= 0:
        increment = max(0.0, float(fallback_increment))
    aligned: list[tuple[date, float]] = []
    current_value = float(revenue_pairs[-1][1])
    last_date = revenue_pairs[-1][0]

    for point_date, _ in cost_pairs:
        if point_date in by_date:
            current_value = by_date[point_date]
            last_date = point_date
            aligned.append((point_date, float(current_value)))
            continue

        if point_date > last_date:
            gap_steps = max((point_date - last_date).days // bucket_days, 1)
            current_value = current_value + (increment * gap_steps)
            last_date = point_date
        aligned.append((point_date, float(max(current_value, 0.0))))
    return aligned


def _projected_budget_exceed_date(
    *,
    budget: float | None,
    actual_series: list[tuple[date, float]],
    forecast_series: list[tuple[date, float]],
) -> date | None:
    if budget is None or budget <= 0:
        return None

    for point_date, cumulative in actual_series:
        if cumulative >= budget:
            return point_date

    points = actual_series[-1:] + forecast_series[1:] if forecast_series else actual_series
    if not points:
        return None

    prev_date, prev_value = points[0]
    if prev_value >= budget:
        return prev_date

    for curr_date, curr_value in points[1:]:
        if curr_value < budget:
            prev_date, prev_value = curr_date, curr_value
            continue
        if curr_value == prev_value:
            return curr_date
        fraction = (budget - prev_value) / (curr_value - prev_value)
        span_days = max((curr_date - prev_date).days, 0)
        crossed = prev_date + timedelta(days=int(round(span_days * fraction)))
        return crossed
    return None


def _risk_level_from_score(score: int) -> str:
    if score >= 60:
        return "RED"
    if score >= 30:
        return "AMBER"
    return "GREEN"


def _build_fallback_explanation(health: dict[str, Any]) -> RiskExplanationOut:
    level = str(health.get("risk_level", "GREEN"))
    score = float(health.get("risk_score", 0))
    drivers = [DriverOut(**driver) for driver in health.get("drivers", [])]
    if not drivers:
        drivers = [
            DriverOut(
                title="No significant risk signals triggered",
                evidence="Current deterministic thresholds did not cross alert limits.",
                metric_refs=["risk_score"],
            )
        ]

    actions: list[RecommendedActionOut] = []
    seen: set[str] = set()

    def push_action(action: str, owner: Literal["PM", "Finance", "Ops"], why: str) -> None:
        key = f"{owner}:{action}"
        if key in seen:
            return
        seen.add(key)
        actions.append(RecommendedActionOut(action=action, owner=owner, why=why))

    signals = health.get("signals", {}) or {}
    if (signals.get("forecast_over_budget_pct") or 0) > 0:
        push_action(
            "Re-baseline forecast and tighten near-term scope",
            "PM",
            "Forecast exceeds budget and needs corrective plan ownership.",
        )
    if (signals.get("approved_uninvoiced_hours") or 0) > 80 or (signals.get("approved_uninvoiced_amount") or 0) > 10000:
        push_action(
            "Prioritize billing package for approved uninvoiced work",
            "Finance",
            "Large approved uninvoiced balance increases cash-flow risk.",
        )
    if (signals.get("oldest_pending_days") or 0) > 7 or (signals.get("pending_timesheets_hours") or 0) > 40:
        push_action(
            "Clear pending approvals backlog",
            "PM",
            "Aging approvals are delaying visibility and invoicing readiness.",
        )
    if (signals.get("nonbillable_ratio_last_4_weeks") or 0) > 0.25:
        push_action(
            "Review non-billable workload allocation",
            "Ops",
            "Sustained non-billable drift erodes budget efficiency.",
        )
    if not actions:
        push_action(
            "Continue weekly controls review",
            "PM",
            "No urgent trigger crossed; maintain monitoring cadence.",
        )

    assumptions = [
        f"Forecast method: {health.get('forecast_method', 'moving_average')}.",
        "Financial totals are deterministic and derived from approved/internal cost logic.",
    ]
    if "missing_end_date_assumed_60d" in (health.get("data_quality_flags") or []):
        assumptions.append("Project end date was assumed as today + 60 days.")

    summary_prefix = {
        "GREEN": "Risk is currently low based on deterministic control signals.",
        "AMBER": "Risk is moderate and needs active monitoring on top signals.",
        "RED": "Risk is elevated and requires immediate mitigation actions.",
    }.get(level, "Risk summary generated from deterministic controls.")

    top_evidence = " ".join(driver.evidence for driver in drivers[:2])
    summary = f"{summary_prefix} {top_evidence}".strip()

    return RiskExplanationOut(
        risk_level=level if level in {"GREEN", "AMBER", "RED"} else "GREEN",
        score=score,
        summary=summary,
        top_drivers=drivers,
        recommended_actions=actions,
        assumptions=assumptions,
        data_quality_flags=[str(x) for x in (health.get("data_quality_flags") or [])],
    )


def _llm_settings() -> tuple[str, str, str | None]:
    api_key = str(os.getenv("LLM_API_KEY", "") or "").strip() or get_openai_api_key()
    model = (
        str(os.getenv("LLM_MODEL", "") or "").strip()
        or str(os.getenv("OPENAI_MODEL", "") or "").strip()
        or get_openai_model()
        or "gpt-5.2"
    )
    base_url = str(os.getenv("LLM_BASE_URL", "") or "").strip() or None
    return api_key, model, base_url


def _call_llm_risk_explanation(payload: dict[str, Any]) -> tuple[RiskExplanationOut | None, str]:
    api_key, model, base_url = _llm_settings()
    if not api_key:
        return None, "missing_api_key"

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=20.0, max_retries=2)

    system_prompt = (
        "You are an ERP project risk analyst.\n"
        "Use ONLY the provided structured data.\n"
        "Do not invent financial values.\n"
        "Return strict JSON only with keys:\n"
        "risk_level, score, summary, top_drivers, recommended_actions, assumptions, data_quality_flags.\n"
        "risk_level must be one of GREEN, AMBER, RED.\n"
        "recommended_actions.owner must be one of PM, Finance, Ops."
    )
    user_prompt = json.dumps(payload, ensure_ascii=True)

    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = resp.choices[0].message.content or ""
    except Exception as exc:
        return None, f"llm_call_failed: {exc}"

    data = _extract_json(raw)
    if not data:
        return None, "invalid_json_response"
    try:
        return RiskExplanationOut(**data), model
    except ValidationError as exc:
        return None, f"schema_validation_failed: {exc}"


def compute_project_health(
    db: Session,
    project_id: str,
    *,
    user_obj: Any | None = None,
    bucket_days: int = 14,
    lookback_buckets: int = 12,
    start_date: date | None = None,
    end_date: date | None = None,
    approved_only: bool = True,
) -> dict[str, Any]:
    project = _ensure_project(db, project_id)
    if user_obj is not None:
        _authorize_project_access(db, project, user_obj)
    today = date.today()
    data_quality_flags: set[str] = set()

    buckets = _build_bucket_windows(
        bucket_days=bucket_days,
        lookback_buckets=lookback_buckets,
        today=today,
        start_date=start_date,
        end_date=end_date,
    )
    if not buckets:
        raise HTTPException(status_code=400, detail="No buckets produced for requested date window")

    range_start = buckets[0][0]
    range_end = buckets[-1][1]
    rates = _rate_lookup(db, project_id)

    entries_query = (
        db.query(TimeEntry, Timesheet)
        .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
        .filter(Timesheet.project_id == project.id)
        .filter(TimeEntry.work_date <= range_end)
    )
    if approved_only:
        entries_query = entries_query.filter(Timesheet.status == "APPROVED")
    entries_rows = entries_query.all()
    approved_entry_exists = (
        db.query(TimeEntry.id)
        .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
        .filter(Timesheet.project_id == project.id)
        .filter(Timesheet.status == "APPROVED")
        .first()
    )
    if not approved_entry_exists:
        data_quality_flags.add("no_approved_entries_found")

    bucket_costs = [0.0 for _ in buckets]
    bucket_revenues = [0.0 for _ in buckets]
    base_cost = 0.0
    base_revenue = 0.0
    util_by_employee: dict[str, dict[str, float]] = {}

    for entry, ts in entries_rows:
        hours = float(entry.hours)
        cost = _entry_cost(entry, rates, data_quality_flags)
        revenue = _entry_revenue(entry, rates, data_quality_flags)
        work_day = entry.work_date
        if work_day < range_start:
            base_cost += cost
            base_revenue += revenue
            continue
        if work_day > range_end:
            continue
        idx = min((work_day - range_start).days // bucket_days, len(bucket_costs) - 1)
        bucket_costs[idx] += cost
        bucket_revenues[idx] += revenue

        employee_id = str(ts.employee_id)
        util_row = util_by_employee.setdefault(employee_id, {"billable_hours": 0.0, "total_hours": 0.0})
        util_row["total_hours"] += hours
        if bool(entry.billable):
            util_row["billable_hours"] += hours

    actual_series: list[dict[str, Any]] = []
    actual_cost_pairs: list[tuple[date, float]] = []
    actual_revenue_pairs: list[tuple[date, float]] = []
    running_cost = base_cost
    running_revenue = base_revenue
    for idx, (bucket_start, bucket_end) in enumerate(buckets):
        _ = bucket_start
        running_cost += bucket_costs[idx]
        running_revenue += bucket_revenues[idx]
        actual_series.append(
            {
                "date": bucket_end.isoformat(),
                "bucket_cost": round(bucket_costs[idx], 2),
                "bucket_revenue": round(bucket_revenues[idx], 2),
                "cumulative_cost": round(running_cost, 2),
                "cumulative_revenue": round(running_revenue, 2),
                "cumulative_profit": round(running_revenue - running_cost, 2),
            }
        )
        actual_cost_pairs.append((bucket_end, float(running_cost)))
        actual_revenue_pairs.append((bucket_end, float(running_revenue)))

    cost_to_date = round(running_cost, 2)

    budget = float(project.approved_budget) if project.approved_budget is not None else None
    if budget is not None and budget <= 0:
        budget = None
        data_quality_flags.add("missing_budget")

    contract_type = str(project.contract_type or "").upper()
    if contract_type == "LUMP_SUM":
        if budget is None:
            revenue_to_date = 0.0
            data_quality_flags.add("missing_budget_for_lump_sum_revenue")
        else:
            revenue_to_date = float(budget)
        for row in actual_series:
            row["cumulative_revenue"] = round(revenue_to_date, 2)
            row["cumulative_profit"] = round(revenue_to_date - float(row["cumulative_cost"]), 2)
            row["bucket_revenue"] = 0.0
        actual_revenue_pairs = [(d, revenue_to_date) for d, _ in actual_cost_pairs]
    else:
        revenue_to_date = round(running_revenue, 2)

    effective_end_date = project.end_date
    if effective_end_date is None:
        effective_end_date = today + timedelta(days=60)
        data_quality_flags.add("missing_end_date_assumed_60d")

    forecast_method, forecast_total_cost_at_end, cost_forecast_pairs = _estimate_forecast(
        bucket_days=bucket_days,
        cumulative_values=[float(row["cumulative_cost"]) for row in actual_series],
        bucket_values=[float(row["bucket_cost"]) for row in actual_series],
        last_actual_date=buckets[-1][1],
        end_date=effective_end_date,
    )
    forecast_total_cost_at_end = round(float(forecast_total_cost_at_end or cost_to_date), 2)

    if contract_type == "LUMP_SUM":
        forecast_total_revenue_at_end = round(revenue_to_date, 2)
        forecast_revenue_pairs = [(point_date, revenue_to_date) for point_date, _ in cost_forecast_pairs]
        revenue_forecast_method = "fixed_lump_sum"
    else:
        revenue_forecast_method, forecast_total_revenue_at_end, forecast_revenue_pairs = _estimate_forecast(
            bucket_days=bucket_days,
            cumulative_values=[float(row["cumulative_revenue"]) for row in actual_series],
            bucket_values=[float(row["bucket_revenue"]) for row in actual_series],
            last_actual_date=buckets[-1][1],
            end_date=effective_end_date,
        )
        forecast_total_revenue_at_end = round(float(forecast_total_revenue_at_end or revenue_to_date), 2)

    cost_tail = [float(v) for v in bucket_costs[-3:] if float(v) > 0]
    revenue_tail = [float(v) for v in bucket_revenues[-3:] if float(v) > 0]
    fallback_cost_increment = (sum(cost_tail) / len(cost_tail)) if cost_tail else 0.0
    fallback_revenue_increment = (sum(revenue_tail) / len(revenue_tail)) if revenue_tail else 0.0

    extended_cost_forecast_pairs = _extend_cost_forecast_for_budget(
        cost_forecast_pairs=cost_forecast_pairs,
        bucket_days=bucket_days,
        budget=budget,
        fallback_increment=fallback_cost_increment,
    )
    aligned_revenue_forecast_pairs = _align_revenue_with_cost_dates(
        cost_pairs=extended_cost_forecast_pairs,
        revenue_pairs=forecast_revenue_pairs,
        bucket_days=bucket_days,
        fallback_increment=fallback_revenue_increment,
    )

    forecast_series: list[dict[str, Any]] = []
    for idx, (point_date, cumulative_cost) in enumerate(extended_cost_forecast_pairs):
        cumulative_revenue = (
            float(aligned_revenue_forecast_pairs[idx][1])
            if idx < len(aligned_revenue_forecast_pairs)
            else float(forecast_total_revenue_at_end)
        )
        forecast_series.append(
            {
                "date": point_date.isoformat(),
                "cumulative_cost": round(cumulative_cost, 2),
                "cumulative_revenue": round(cumulative_revenue, 2),
                "cumulative_profit": round(cumulative_revenue - cumulative_cost, 2),
            }
        )

    forecast_budget_exceed_date = _projected_budget_exceed_date(
        budget=budget,
        actual_series=actual_cost_pairs,
        forecast_series=extended_cost_forecast_pairs,
    )

    pending_timesheets = (
        db.query(Timesheet)
        .filter(Timesheet.project_id == project.id)
        .filter(Timesheet.status == "SUBMITTED")
        .all()
    )
    pending_timesheets_hours = 0.0
    if pending_timesheets:
        pending_ids = [ts.id for ts in pending_timesheets]
        pending_entries = db.query(TimeEntry).filter(TimeEntry.timesheet_id.in_(pending_ids)).all()
        pending_timesheets_hours = sum(float(entry.hours) for entry in pending_entries)
    oldest_pending_days: int | None = None
    if pending_timesheets:
        oldest_pending_date = min((ts.submitted_at.date() if ts.submitted_at else ts.period_end) for ts in pending_timesheets)
        oldest_pending_days = max((today - oldest_pending_date).days, 0)

    uninvoiced_rows = (
        db.query(TimeEntry)
        .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
        .filter(Timesheet.project_id == project.id)
        .filter(Timesheet.status == "APPROVED")
        .filter(TimeEntry.billable.is_(True))
        .filter(TimeEntry.invoiced_line_id.is_(None))
        .all()
    )
    approved_uninvoiced_hours = sum(float(entry.hours) for entry in uninvoiced_rows)
    approved_uninvoiced_amount = sum(_entry_revenue(entry, rates, data_quality_flags) for entry in uninvoiced_rows)

    nonbill_window_start = today - timedelta(days=27)
    ratio_rows_query = (
        db.query(TimeEntry, Timesheet)
        .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
        .filter(Timesheet.project_id == project.id)
        .filter(TimeEntry.work_date >= nonbill_window_start)
        .filter(TimeEntry.work_date <= today)
    )
    if approved_only:
        ratio_rows_query = ratio_rows_query.filter(Timesheet.status == "APPROVED")
    ratio_rows = ratio_rows_query.all()
    ratio_total_hours = sum(float(entry.hours) for entry, _ts in ratio_rows)
    ratio_nonbillable_hours = sum(float(entry.hours) for entry, _ts in ratio_rows if not bool(entry.billable))
    nonbillable_ratio_last_4_weeks = (
        (ratio_nonbillable_hours / ratio_total_hours) if ratio_total_hours > 0 else None
    )

    # Restrict utilization membership to employees tied to this project:
    # 1) worked in the selected window, or
    # 2) assigned via non-draft workflow state on this project.
    worked_employee_q = (
        db.query(Timesheet.employee_id)
        .join(TimeEntry, TimeEntry.timesheet_id == Timesheet.id)
        .filter(Timesheet.project_id == project.id)
        .filter(TimeEntry.work_date >= range_start)
        .filter(TimeEntry.work_date <= range_end)
    )
    if approved_only:
        worked_employee_q = worked_employee_q.filter(Timesheet.status == "APPROVED")
    worked_employee_rows = worked_employee_q.distinct().all()

    assigned_employee_rows = (
        db.query(Timesheet.employee_id)
        .filter(Timesheet.project_id == project.id)
        .filter(Timesheet.period_end >= range_start)
        .filter(Timesheet.period_start <= range_end)
        .filter(Timesheet.status.in_(["SUBMITTED", "APPROVED", "REJECTED"]))
        .distinct()
        .all()
    )

    scoped_employee_ids = {
        str(employee_id)
        for (employee_id,) in (worked_employee_rows + assigned_employee_rows)
        if employee_id is not None
    }
    for employee_id in scoped_employee_ids:
        util_by_employee.setdefault(employee_id, {"billable_hours": 0.0, "total_hours": 0.0})

    employee_utilization: list[dict[str, Any]] = []
    employee_ids = list(util_by_employee.keys())
    employee_name_map: dict[str, str] = {}
    if employee_ids:
        user_rows = db.query(User).filter(User.id.in_(employee_ids)).all()
        employee_name_map = {str(user.id): str(user.name) for user in user_rows}

    for employee_id, util_row in util_by_employee.items():
        billable_hours = float(util_row.get("billable_hours", 0.0))
        total_hours = float(util_row.get("total_hours", 0.0))
        utilization_logged = (billable_hours / total_hours) if total_hours > 0 else 0.0
        employee_utilization.append(
            {
                "employee_id": employee_id,
                "employee_name": employee_name_map.get(employee_id, f"User {employee_id[:8]}"),
                "billable_hours": round(billable_hours, 2),
                "total_hours": round(total_hours, 2),
                "utilization_logged": round(utilization_logged, 4),
                "target_hours": None,
                "utilization_target": None,
            }
        )
    employee_utilization.sort(key=lambda row: float(row.get("utilization_logged", 0.0)), reverse=True)

    burn_rate_accel: float | None = None
    recent_avg = 0.0
    baseline_avg = 0.0
    if len(bucket_costs) >= 2:
        recent_avg = sum(bucket_costs[-2:]) / 2.0
    if len(bucket_costs) >= 6:
        baseline_avg = sum(bucket_costs[-6:-2]) / 4.0
        if baseline_avg > 0:
            burn_rate_accel = (recent_avg - baseline_avg) / baseline_avg

    time_progress: float | None = None
    if project.start_date and effective_end_date:
        total_days = max((effective_end_date - project.start_date).days, 1)
        elapsed_days = max((today - project.start_date).days, 0)
        time_progress = _clamp01(elapsed_days / total_days)

    budget_consumed: float | None = (cost_to_date / budget) if budget and budget > 0 else None
    forecast_over_budget_pct = _safe_percent(
        forecast_total_cost_at_end - budget if budget else 0.0,
        budget or 0.0,
    )
    profit_to_date = round(float(revenue_to_date) - float(cost_to_date), 2)
    forecast_profit_at_end = round(float(forecast_total_revenue_at_end) - float(forecast_total_cost_at_end), 2)

    risk_score = 0
    drivers: list[dict[str, Any]] = []

    if budget and forecast_total_cost_at_end > budget:
        risk_score += 50
        drivers.append(
            {
                "title": "Forecast exceeds approved budget",
                "evidence": (
                    f"Forecast total cost is ${forecast_total_cost_at_end:,.0f} "
                    f"vs budget ${budget:,.0f}."
                ),
                "metric_refs": ["forecast_total_cost_at_end", "budget", "forecast_over_budget_pct"],
            }
        )
    elif budget and forecast_total_cost_at_end >= (0.9 * budget):
        risk_score += 25
        drivers.append(
            {
                "title": "Forecast is close to budget ceiling",
                "evidence": (
                    f"Forecast total cost is ${forecast_total_cost_at_end:,.0f}, "
                    f"approaching budget ${budget:,.0f}."
                ),
                "metric_refs": ["forecast_total_cost_at_end", "budget"],
            }
        )

    if burn_rate_accel is not None and burn_rate_accel > 0.40:
        risk_score += 25
        drivers.append(
            {
                "title": "Burn rate is accelerating sharply",
                "evidence": (
                    f"Recent bucket average ${recent_avg:,.0f} vs baseline ${baseline_avg:,.0f} "
                    f"({burn_rate_accel * 100:.1f}% acceleration)."
                ),
                "metric_refs": ["burn_rate_accel"],
            }
        )
    elif burn_rate_accel is not None and burn_rate_accel > 0.20:
        risk_score += 15
        drivers.append(
            {
                "title": "Burn rate is accelerating",
                "evidence": (
                    f"Recent bucket average ${recent_avg:,.0f} vs baseline ${baseline_avg:,.0f} "
                    f"({burn_rate_accel * 100:.1f}% acceleration)."
                ),
                "metric_refs": ["burn_rate_accel"],
            }
        )

    if budget_consumed is not None and time_progress is not None and budget_consumed > (time_progress + 0.15):
        risk_score += 15
        drivers.append(
            {
                "title": "Budget consumed is ahead of schedule progress",
                "evidence": (
                    f"Budget consumed is {budget_consumed * 100:.1f}% while time progress is "
                    f"{time_progress * 100:.1f}%."
                ),
                "metric_refs": ["budget_consumed", "time_progress"],
            }
        )

    if budget and (approved_uninvoiced_amount > max(0.10 * budget, 10000) or approved_uninvoiced_hours > 80):
        risk_score += 10
        drivers.append(
            {
                "title": "Approved work is waiting to be invoiced",
                "evidence": (
                    f"Approved uninvoiced amount is ${approved_uninvoiced_amount:,.0f} "
                    f"({approved_uninvoiced_hours:.1f}h)."
                ),
                "metric_refs": ["approved_uninvoiced_amount", "approved_uninvoiced_hours"],
            }
        )
    elif approved_uninvoiced_hours > 80:
        risk_score += 10
        drivers.append(
            {
                "title": "Approved uninvoiced hours are elevated",
                "evidence": f"Approved uninvoiced hours are {approved_uninvoiced_hours:.1f}h.",
                "metric_refs": ["approved_uninvoiced_hours"],
            }
        )

    if (oldest_pending_days or 0) > 7 or pending_timesheets_hours > 40:
        risk_score += 10
        drivers.append(
            {
                "title": "Pending approvals are aging",
                "evidence": (
                    f"Pending timesheets total {pending_timesheets_hours:.1f}h "
                    f"with oldest pending age {oldest_pending_days or 0} days."
                ),
                "metric_refs": ["pending_timesheets_hours", "oldest_pending_days"],
            }
        )

    if nonbillable_ratio_last_4_weeks is not None and nonbillable_ratio_last_4_weeks > 0.25:
        risk_score += 10
        drivers.append(
            {
                "title": "Non-billable share drift is high",
                "evidence": f"Non-billable ratio is {nonbillable_ratio_last_4_weeks * 100:.1f}% in the last 4 weeks.",
                "metric_refs": ["nonbillable_ratio_last_4_weeks"],
            }
        )

    risk_score = min(risk_score, 100)
    risk_level = _risk_level_from_score(risk_score)

    signals = {
        "forecast_over_budget_pct": round(forecast_over_budget_pct, 2) if forecast_over_budget_pct is not None else None,
        "burn_rate_accel": round(burn_rate_accel, 4) if burn_rate_accel is not None else None,
        "time_progress": round(time_progress, 4) if time_progress is not None else None,
        "budget_consumed": round(budget_consumed, 4) if budget_consumed is not None else None,
        "revenue_to_date": round(float(revenue_to_date), 2),
        "profit_to_date": round(float(profit_to_date), 2),
        "forecast_profit_at_end": round(float(forecast_profit_at_end), 2),
        "approved_uninvoiced_amount": round(approved_uninvoiced_amount, 2),
        "approved_uninvoiced_hours": round(approved_uninvoiced_hours, 2),
        "pending_timesheets_hours": round(pending_timesheets_hours, 2),
        "oldest_pending_days": oldest_pending_days,
        "nonbillable_ratio_last_4_weeks": (
            round(nonbillable_ratio_last_4_weeks, 4) if nonbillable_ratio_last_4_weeks is not None else None
        ),
    }

    return {
        "project_id": str(project.id),
        "project_name": project.project_name,
        "status": project.status,
        "contract_type": project.contract_type,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "project_end_date": project.end_date.isoformat() if project.end_date else None,
        "effective_end_date": effective_end_date.isoformat() if effective_end_date else None,
        "budget": round(budget, 2) if budget is not None else None,
        "cost_to_date": round(cost_to_date, 2),
        "revenue_to_date": round(float(revenue_to_date), 2),
        "profit_to_date": round(float(profit_to_date), 2),
        "forecast_total_cost_at_end": round(forecast_total_cost_at_end, 2),
        "forecast_total_revenue_at_end": round(float(forecast_total_revenue_at_end), 2),
        "forecast_profit_at_end": round(float(forecast_profit_at_end), 2),
        "forecast_budget_exceed_date": forecast_budget_exceed_date.isoformat() if forecast_budget_exceed_date else None,
        "forecast_method": forecast_method,
        "revenue_forecast_method": revenue_forecast_method,
        "risk_score": int(risk_score),
        "risk_level": risk_level,
        "signals": signals,
        "series": {"actual": actual_series, "forecast": forecast_series},
        "employee_utilization": employee_utilization,
        "drivers": drivers,
        "data_quality_flags": sorted(data_quality_flags),
        "updated_at": _to_iso_z(datetime.now(timezone.utc)),
    }


def build_project_risk_explanation(
    db: Session,
    project_id: str,
    *,
    user_obj: Any | None = None,
    bucket_days: int = 14,
    lookback_buckets: int = 12,
    start_date: date | None = None,
    end_date: date | None = None,
    approved_only: bool = True,
) -> dict[str, Any]:
    project = _ensure_project(db, project_id)
    health = compute_project_health(
        db,
        project_id,
        user_obj=user_obj,
        bucket_days=bucket_days,
        lookback_buckets=lookback_buckets,
        start_date=start_date,
        end_date=end_date,
        approved_only=approved_only,
    )

    llm_payload = {
        "project": {
            "id": str(project.id),
            "name": project.project_name,
            "division": project.division,
            "discipline": project.discipline,
            "contract_type": project.contract_type,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "budget": health.get("budget"),
        },
        "metrics": {
            "cost_to_date": health.get("cost_to_date"),
            "revenue_to_date": health.get("revenue_to_date"),
            "profit_to_date": health.get("profit_to_date"),
            "forecast_total_cost_at_end": health.get("forecast_total_cost_at_end"),
            "forecast_total_revenue_at_end": health.get("forecast_total_revenue_at_end"),
            "forecast_profit_at_end": health.get("forecast_profit_at_end"),
            "forecast_budget_exceed_date": health.get("forecast_budget_exceed_date"),
            "risk_score": health.get("risk_score"),
            "risk_level": health.get("risk_level"),
            **(health.get("signals") or {}),
        },
        "drivers": health.get("drivers") or [],
        "data_quality_flags": health.get("data_quality_flags") or [],
    }

    fallback = _build_fallback_explanation(health)
    generated_at = _to_iso_z(datetime.now(timezone.utc))
    llm_result, llm_meta = _call_llm_risk_explanation(llm_payload)
    used_fallback = llm_result is None
    output = llm_result or fallback

    return {
        "project_id": str(project.id),
        "result": output.model_dump(),
        "meta": {
            "model": llm_meta if not used_fallback else "fallback_rules",
            "timestamp": generated_at,
            "used_fallback": used_fallback,
            "fallback_reason": llm_meta if used_fallback else "",
        },
    }
