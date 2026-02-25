# backend/app/services/ai/risk.py
from __future__ import annotations
from pydantic import BaseModel, Field

from app.services.ai.client import ai_enabled, call_structured

class RiskExplainOut(BaseModel):
    risk_label: str = Field(description="LOW/MEDIUM/HIGH")
    summary: str
    recommended_actions: list[str] = Field(default_factory=list)

def risk_label(metrics: dict) -> tuple[str, list[str]]:
    budget = float(metrics.get("budget", 0) or 0)
    forecast = float(metrics.get("forecast_total", 0) or 0)
    consumed = float(metrics.get("percent_budget_consumed", 0) or 0)
    readiness = float(metrics.get("invoice_readiness_pct", 0) or 0)
    nonbill = float(metrics.get("nonbillable_ratio_pct", 0) or 0)

    score = 0
    reasons = []
    if budget > 0 and forecast > budget:
        score += 3; reasons.append("Forecast exceeds budget.")
    if consumed > 80:
        score += 2; reasons.append("Budget consumption is above 80%.")
    if readiness < 60:
        score += 1; reasons.append("Invoice readiness is low (pending approvals).")
    if nonbill > 30:
        score += 1; reasons.append("Non-billable ratio is high.")

    if score >= 4: return "HIGH", reasons
    if score >= 2: return "MEDIUM", reasons
    return "LOW", reasons

def explain_risk(title: str, metrics: dict) -> tuple[RiskExplainOut, dict]:
    label, reasons = risk_label(metrics)
    base = RiskExplainOut(
        risk_label=label,
        summary=f"{title}: Risk={label}. " + (" ".join(reasons) if reasons else "No major risk factors detected."),
        recommended_actions=[
            "Review pending approvals",
            "Reduce non-billable time",
            "Draft invoice this month"
        ] if label in ("MEDIUM","HIGH") else []
    )

    if not ai_enabled():
        return base, {"used_ai": False, "raw": ""}

    system = (
        "You are an ERP project controls assistant.\n"
        "Explain risk based ONLY on provided metrics and reasons.\n"
        "Return ONLY JSON: {risk_label, summary, recommended_actions}."
    )
    user = f"""
Project: {title}
Metrics: {metrics}
RuleReasons: {reasons}
RiskLabel: {label}

Return JSON:
{{"risk_label":"{label}","summary":"...","recommended_actions":["..."]}}
"""
    out, raw = call_structured(RiskExplainOut, system, user)
    if out:
        return out, {"used_ai": True, "raw": raw}
    return base, {"used_ai": False, "raw": raw}