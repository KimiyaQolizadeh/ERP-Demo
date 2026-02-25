# backend/app/services/ai/classify.py
from __future__ import annotations
from pydantic import BaseModel, Field

from app.services.ai.client import ai_enabled, call_structured

NON_BILLABLE_KW = ["internal", "training", "admin", "recruit", "pto", "holiday", "proposal", "business development"]
BILLABLE_KW = ["client", "deliverable", "design", "review", "site", "coordination", "meeting", "calculation", "drawing"]

class BillableResult(BaseModel):
    billable: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str

def classify_rules(notes: str) -> BillableResult:
    t = (notes or "").lower()
    if any(k in t for k in NON_BILLABLE_KW):
        return BillableResult(billable=False, confidence=0.85, reason="Matched non-billable keywords")
    if any(k in t for k in BILLABLE_KW):
        return BillableResult(billable=True, confidence=0.80, reason="Matched billable keywords")
    return BillableResult(billable=True, confidence=0.55, reason="Uncertain; default suggestion is billable")

def classify_billable(notes: str, discipline: str | None = None, contract_type: str | None = None) -> tuple[BillableResult, dict]:
    base = classify_rules(notes)
    # Only call LLM if uncertain
    if base.confidence >= 0.75 or not ai_enabled():
        return base, {"used_ai": False, "raw": ""}

    system = (
        "You are classifying timesheet work as Billable or Non-Billable for a professional services firm.\n"
        "Return ONLY JSON with keys: billable (true/false), confidence (0-1), reason (short)."
    )
    user = f"""
Notes: {notes}
Discipline: {discipline or ""}
ContractType: {contract_type or ""}

Return JSON:
{{"billable": true, "confidence": 0.7, "reason": "..."}}"""
    out, raw = call_structured(BillableResult, system, user)
    if out:
        return out, {"used_ai": True, "raw": raw}
    return base, {"used_ai": False, "raw": raw}