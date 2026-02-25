from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.core.config import BILLABLE_AUTO_ACCEPT, BILLABLE_REVIEW_MAX, BILLABLE_REVIEW_MIN
from app.core.config import get_openai_model
from app.services.ai.client import ai_enabled, call_structured

RULES_PATH = Path(__file__).parent / "rules" / "billable_rules.yaml"


class LLMRefineOut(BaseModel):
    suggested_billable: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


def _load_rules() -> dict[str, list[dict[str, Any]]]:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "billable": list(data.get("billable", [])),
        "non_billable": list(data.get("non_billable", [])),
    }


def _status_from_confidence(confidence: float) -> str:
    if confidence >= BILLABLE_AUTO_ACCEPT:
        return "AUTO"
    if BILLABLE_REVIEW_MIN <= confidence < BILLABLE_REVIEW_MAX:
        return "REVIEW"
    return "NEEDS_SELECTION"


def score_billable_rules(notes: str) -> dict[str, Any]:
    rules = _load_rules()
    text = (notes or "").lower()
    score = 0.0
    matched: list[str] = []

    for rule in rules["billable"]:
        phrase = str(rule.get("phrase", "")).strip().lower()
        if phrase and phrase in text:
            weight = float(rule.get("weight", 0))
            score += weight
            matched.append(f"+{phrase}")

    for rule in rules["non_billable"]:
        phrase = str(rule.get("phrase", "")).strip().lower()
        if phrase and phrase in text:
            weight = float(rule.get("weight", 0))
            score -= weight
            matched.append(f"-{phrase}")

    prob_billable = 1.0 / (1.0 + math.exp(-score))
    suggested_billable = prob_billable >= 0.5
    confidence = abs(prob_billable - 0.5) * 2.0
    confidence = max(0.0, min(1.0, float(confidence)))
    status = _status_from_confidence(confidence)
    return {
        "suggested_billable": bool(suggested_billable),
        "confidence": confidence,
        "status": status,
        "matched": matched,
        "model": "rules_catalog",
    }


def refine_with_llm_if_review(
    notes: str,
    discipline: str | None,
    contract_type: str | None,
    rules_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if rules_result["status"] != "REVIEW" or not ai_enabled():
        return rules_result, {"used_ai": False, "model": "rules_catalog", "raw": ""}

    system = (
        "You classify timesheet notes as billable/non-billable.\n"
        "Return ONLY JSON with keys: suggested_billable, confidence, reason.\n"
        "Do not invent facts. Use confidence in [0,1]."
    )
    user = (
        f"Notes: {notes}\n"
        f"Discipline: {discipline or ''}\n"
        f"ContractType: {contract_type or ''}\n"
        f"RulesResult: {rules_result}\n"
    )
    parsed, raw = call_structured(LLMRefineOut, system, user)
    if not parsed:
        return rules_result, {"used_ai": False, "model": "rules_catalog", "raw": raw}

    refined = {
        "suggested_billable": bool(parsed.suggested_billable),
        "confidence": max(0.0, min(1.0, float(parsed.confidence))),
        "status": _status_from_confidence(float(parsed.confidence)),
        "matched": list(rules_result.get("matched", [])),
        "reason": parsed.reason,
        "model": get_openai_model(),
    }
    return refined, {"used_ai": True, "model": get_openai_model(), "raw": raw}
