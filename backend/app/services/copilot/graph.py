from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, TypedDict

from fastapi import HTTPException
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.tables import Project, Timesheet, User, UserPreference
from app.services import approvals as approvals_svc
from app.services import invoicing as invoicing_svc
from app.services import project_health as project_health_svc
from app.services import reporting as reporting_svc
from app.services import search as search_svc
from app.services.ai import retrieval as retrieval_svc

logger = logging.getLogger("app.copilot")


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return default


COPILOT_PRIMARY_MODEL = _env_first("COPILOT_MODEL", "LLM_MODEL", "OPENAI_MODEL", default="gpt-5.2")
COPILOT_FALLBACK_MODEL = _env_first(
    "COPILOT_FALLBACK_MODEL",
    "LLM_FALLBACK_MODEL",
    "OPENAI_FALLBACK_MODEL",
    default="o4-mini",
)
COPILOT_BASE_URL = _env_first("LLM_BASE_URL", "OPENAI_BASE_URL", default="")
try:
    COPILOT_SCOPE_THRESHOLD = float(_env_first("COPILOT_SCOPE_THRESHOLD", default="0.10"))
except Exception:
    COPILOT_SCOPE_THRESHOLD = 0.10
ALLOWED_INTENTS = {
    "portfolio_overview",
    "project_health",
    "draft_invoice",
    "utilization",
    "anomalies",
    "invoice_readiness",
    "pending_approvals",
    "text_search",
}
DATASET_CATALOG: dict[str, str] = {
    "portfolio_overview": "reports.dashboard project metrics",
    "project_health": "project-level health and forecast",
    "invoice_readiness": "invoice readiness by project",
    "pending_approvals": "pending submitted timesheets",
    "utilization": "employee utilization",
    "anomalies": "anomalies vs baseline",
    "draft_invoice": "draft invoice totals",
    "text_search": "semantic retrieval over indexed text",
}
ALLOWED_DATASETS = set(DATASET_CATALOG.keys())
ROLE_VALUES = {"EMPLOYEE", "PM", "FINANCE", "ADMIN"}
MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
FOLLOW_UP_TOKENS = re.compile(r"\b(continue|same|again|compare|that|this|it|those|these)\b")
_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "for",
    "in",
    "on",
    "at",
    "with",
    "show",
    "tell",
    "me",
    "about",
    "from",
    "last",
    "month",
    "this",
    "current",
    "project",
    "employee",
    "user",
    "what",
    "which",
    "how",
    "is",
    "are",
}
SCOPE_KEYWORDS = (
    "project",
    "portfolio",
    "employee",
    "timesheet",
    "approval",
    "invoice",
    "billing",
    "budget",
    "burn",
    "forecast",
    "risk",
    "profit",
    "revenue",
    "cost",
    "utilization",
    "readiness",
    "anomaly",
    "spend",
    "margin",
    "hours",
)

DEFAULT_USER_PREFERENCES = {
    "default_month": "",
    "last_project_name": "",
    "last_user_name": "",
    "last_intent": "",
    "last_datasets": [],
    "last_filters": {},
}


class IntentOut(BaseModel):
    intent: Literal[
        "portfolio_overview",
        "project_health",
        "draft_invoice",
        "utilization",
        "anomalies",
        "invoice_readiness",
        "pending_approvals",
        "text_search",
    ]
    datasets: list[str] = Field(default_factory=list)
    project_name: str | None = None
    user_name: str | None = None
    month: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class SummaryOut(BaseModel):
    reply: str
    evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = 0.55


@dataclass
class ResolvedContext:
    month_iso: str
    role: str
    project_name: str | None = None
    project_id: str | None = None
    user_name: str | None = None
    user_id: str | None = None
    filters: dict[str, Any] | None = None
    accessible_projects: set[str] | None = None
    accessible_users: set[str] | None = None


class CopilotState(TypedDict, total=False):
    db: Session
    user_obj: Any
    message: str
    history: list[dict[str, str]]
    prefs: dict[str, Any]
    prefs_row: UserPreference
    month_iso: str
    intent: IntentOut
    resolved: ResolvedContext
    tool_result: dict[str, Any]
    summary: SummaryOut
    tool_trace: list[dict[str, Any]]
    memory_updates: dict[str, Any]


_COMPILED_GRAPH = None


def _role(user_obj: Any) -> str:
    role = str(getattr(user_obj, "role", "EMPLOYEE") or "EMPLOYEE").upper()
    return role if role in ROLE_VALUES else "EMPLOYEE"


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _month_shift(value: date, months: int) -> date:
    year = value.year + ((value.month - 1 + months) // 12)
    month = ((value.month - 1 + months) % 12) + 1
    return date(year, month, 1)


def _normalize_month(raw: str | None, fallback_iso: str | None = None) -> str:
    today = _month_start(date.today())
    fallback = fallback_iso or today.isoformat()
    if not raw:
        return fallback
    text = str(raw).strip().lower()
    if text in {"", "this month", "current month"}:
        return today.isoformat()
    if text == "last month":
        return _month_shift(today, -1).isoformat()
    try:
        return _month_start(date.fromisoformat(text)).isoformat()
    except Exception:
        pass
    if re.match(r"^\d{4}-\d{2}$", text):
        try:
            return date.fromisoformat(f"{text}-01").isoformat()
        except Exception:
            return fallback
    m = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+(\d{4}))?$", text)
    if m:
        month = MONTH_NAMES[m.group(1)]
        year = int(m.group(2)) if m.group(2) else today.year
        out = date(year, month, 1)
        if not m.group(2) and out > today:
            out = date(year - 1, month, 1)
        return out.isoformat()
    return fallback


def _extract_response_text(resp: Any) -> str:
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    chunks: list[str] = []
    for item in getattr(resp, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(str(value))
    return "\n".join(chunks).strip()


def _json_or_none(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except Exception:
            return None
    return None


def _openai_json(messages: list[dict[str, str]]) -> dict[str, Any] | None:
    api_key = _env_first("LLM_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": 20.0, "max_retries": 2}
        if COPILOT_BASE_URL:
            kwargs["base_url"] = COPILOT_BASE_URL
        client = OpenAI(**kwargs)
        models = [str(COPILOT_PRIMARY_MODEL).strip()]
        fallback = str(COPILOT_FALLBACK_MODEL).strip()
        if fallback and fallback not in models:
            models.append(fallback)

        for model in models:
            raw = "{}"
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=messages,
                )
                raw = resp.choices[0].message.content or "{}"
                parsed = _json_or_none(raw)
                if parsed:
                    return parsed
            except Exception:
                try:
                    resp = client.responses.create(model=model, input=messages, temperature=0)
                    raw = _extract_response_text(resp) or "{}"
                    parsed = _json_or_none(raw)
                    if parsed:
                        return parsed
                except Exception:
                    continue
        return None
    except Exception:
        logger.exception("chat assistant openai call failed")
        return None


def _append_trace(state: CopilotState, trace: dict[str, Any]) -> list[dict[str, Any]]:
    current = list(state.get("tool_trace", []))
    current.append(trace)
    return current


def _coerce_filters(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (raw or {}).items():
        if key in {"readiness_lt", "forecast_gt", "budget_consumed_gt"}:
            try:
                out[key] = float(value)
            except Exception:
                continue
        elif key == "anomaly_metric":
            metric = str(value or "").strip().lower()
            if metric in {"spend_to_date", "burn_rate"}:
                out[key] = metric
    return out


def _default_datasets(intent: str) -> list[str]:
    mapping = {
        "portfolio_overview": ["portfolio_overview"],
        "project_health": ["project_health"],
        "draft_invoice": ["draft_invoice", "invoice_readiness"],
        "utilization": ["utilization"],
        "anomalies": ["anomalies"],
        "invoice_readiness": ["invoice_readiness"],
        "pending_approvals": ["pending_approvals"],
        "text_search": ["text_search"],
    }
    return list(mapping.get(intent, ["portfolio_overview"]))


def _load_user_preferences(db: Session, user_id: Any) -> tuple[dict[str, Any], UserPreference]:
    row = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not row:
        row = UserPreference(user_id=user_id, prefs={"user_preferences": dict(DEFAULT_USER_PREFERENCES)})
        db.add(row)
        db.commit()
        db.refresh(row)
    prefs = row.prefs if isinstance(row.prefs, dict) else {}
    if "user_preferences" not in prefs or not isinstance(prefs.get("user_preferences"), dict):
        prefs = dict(prefs)
        prefs["user_preferences"] = dict(DEFAULT_USER_PREFERENCES)
        row.prefs = prefs
        db.commit()
        db.refresh(row)
    return prefs, row

def _fallback_intent(message: str, month_iso: str, prefs: dict[str, Any]) -> IntentOut:
    lower = message.lower()
    mem = prefs.get("user_preferences", {}) or {}
    follow_up = bool(FOLLOW_UP_TOKENS.search(lower))
    intent = "portfolio_overview"
    if "pending" in lower or "approval" in lower:
        intent = "pending_approvals"
    elif "draft invoice" in lower or ("draft" in lower and "invoice" in lower):
        intent = "draft_invoice"
    elif "readiness" in lower:
        intent = "invoice_readiness"
    elif "utilization" in lower or "utilisation" in lower:
        intent = "utilization"
    elif "employee" in lower or "worked" in lower or "billable" in lower or "hours" in lower:
        intent = "utilization"
    elif "anomal" in lower or "more than normal" in lower:
        intent = "anomalies"
    elif "note" in lower or "policy" in lower or "text" in lower:
        intent = "text_search"
    elif "forecast" in lower or "budget" in lower or "profit" in lower or "risk" in lower:
        intent = "project_health"
    elif "revenue" in lower or "cost" in lower or "margin" in lower:
        intent = "project_health"
    elif "invoice" in lower:
        intent = "invoice_readiness"
    elif re.search(r"\b(continue|what about|same)\b", lower):
        remembered = str(mem.get("last_intent") or "").strip()
        if remembered in ALLOWED_INTENTS:
            intent = remembered

    project_name = None
    pm = re.search(r"project\s+([a-z0-9 _-]{2,})", lower)
    if pm:
        project_name = pm.group(1).strip().title()
    elif follow_up and str(mem.get("last_project_name") or "").strip():
        project_name = str(mem.get("last_project_name")).strip()

    user_name = None
    um = re.search(r"(employee|user)\s+([a-z0-9 _-]{2,})", lower)
    if um:
        user_name = um.group(2).strip().title()
    elif follow_up and str(mem.get("last_user_name") or "").strip() and intent == "utilization":
        user_name = str(mem.get("last_user_name")).strip()

    filters: dict[str, Any] = {}
    num = re.search(r"(\d{1,3})\s*%?", lower)
    if "readiness" in lower and num:
        filters["readiness_lt"] = float(num.group(1))
    if "forecast" in lower and num:
        filters["forecast_gt"] = float(num.group(1))
    if "budget" in lower and num:
        filters["budget_consumed_gt"] = float(num.group(1))
    if "burn" in lower:
        filters["anomaly_metric"] = "burn_rate"
    if not filters and follow_up and isinstance(mem.get("last_filters"), dict):
        filters = dict(mem.get("last_filters") or {})

    datasets = _default_datasets(intent)
    if re.search(r"\b(continue|same)\b", lower) and isinstance(mem.get("last_datasets"), list):
        remembered_datasets = [str(x) for x in mem.get("last_datasets", []) if str(x) in ALLOWED_DATASETS]
        if remembered_datasets:
            datasets = remembered_datasets

    month_hint: str | None = None
    if "last month" in lower:
        month_hint = "last month"
    elif "this month" in lower or "current month" in lower:
        month_hint = "this month"
    else:
        iso_month = re.search(r"\b(\d{4}-\d{2})(?:-\d{2})?\b", lower)
        if iso_month:
            month_hint = iso_month.group(1)
        else:
            month_word = re.search(
                r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+\d{4})?\b",
                lower,
            )
            if month_word:
                month_hint = month_word.group(0)

    resolved_month = _normalize_month(month_hint, fallback_iso=month_iso) if month_hint else None
    return IntentOut(
        intent=intent,  # type: ignore[arg-type]
        datasets=datasets,
        project_name=project_name,
        user_name=user_name,
        month=resolved_month,
        filters=_coerce_filters(filters),
    )


def _intent_router(
    message: str,
    history: list[dict[str, str]],
    month_iso: str,
    prefs: dict[str, Any],
    role: str,
) -> tuple[IntentOut, dict[str, Any]]:
    mem = prefs.get("user_preferences", {}) if isinstance(prefs.get("user_preferences"), dict) else {}
    prompt = [
        {
            "role": "system",
            "content": (
                "Return strict JSON only with keys: intent, datasets, project_name, user_name, month, filters.\n"
                f"Allowed intents: {', '.join(sorted(ALLOWED_INTENTS))}.\n"
                f"Allowed datasets: {', '.join(sorted(ALLOWED_DATASETS))}.\n"
                "Pick datasets from schema by user question. No IDs."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "message": message,
                    "history": history[-10:],
                    "user_role": role,
                    "default_month": month_iso,
                    "memory_defaults": {
                        "last_project_name": mem.get("last_project_name"),
                        "last_user_name": mem.get("last_user_name"),
                        "last_intent": mem.get("last_intent"),
                        "last_datasets": mem.get("last_datasets"),
                        "last_filters": mem.get("last_filters"),
                    },
                    "dataset_catalog": DATASET_CATALOG,
                }
            ),
        },
    ]
    raw = _openai_json(prompt)
    if raw:
        try:
            intent = IntentOut(**raw)
            if intent.intent not in ALLOWED_INTENTS:
                raise ValueError("invalid intent")
            intent.datasets = [d for d in intent.datasets if d in ALLOWED_DATASETS] or _default_datasets(intent.intent)
            intent.filters = _coerce_filters(intent.filters)
            return intent, {"node": "intent_router", "status": "ok", "intent": intent.model_dump()}
        except Exception:
            logger.exception("intent parser failed")
    fallback = _fallback_intent(message, month_iso, prefs)
    return fallback, {"node": "intent_router", "status": "fallback", "intent": fallback.model_dump()}


def _accessible_project_ids(db: Session, user_obj: Any, role: str) -> set[str]:
    if role in {"ADMIN", "FINANCE"}:
        return {str(pid) for (pid,) in db.query(Project.id).all()}
    if role == "PM":
        rows = db.query(Project.id).filter(Project.pm_user_id == user_obj.id).all()
        return {str(pid) for (pid,) in rows}
    rows = db.query(Timesheet.project_id).filter(Timesheet.employee_id == user_obj.id).distinct().all()
    return {str(pid) for (pid,) in rows if pid is not None}


def _accessible_user_ids(db: Session, user_obj: Any, role: str, project_ids: set[str]) -> set[str]:
    if role == "EMPLOYEE":
        return {str(user_obj.id)}
    if role in {"ADMIN", "FINANCE"}:
        return {str(uid) for (uid,) in db.query(User.id).all()}
    rows = db.query(Timesheet.employee_id, Timesheet.project_id).all()
    return {str(uid) for uid, pid in rows if uid is not None and str(pid) in project_ids}


def _candidate_queries_from_message(message: str, max_items: int = 20) -> list[str]:
    tokens = [t for t in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}", str(message or "")) if t]
    cleaned = [t for t in tokens if t.lower() not in _STOPWORDS]
    if not cleaned:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for size in (3, 2, 1):
        if len(cleaned) < size:
            continue
        for i in range(0, len(cleaned) - size + 1):
            phrase = " ".join(cleaned[i : i + size]).strip()
            key = phrase.lower()
            if len(key) < 3 or key in seen:
                continue
            seen.add(key)
            out.append(phrase)
            if len(out) >= max_items:
                return out
    return out


def _resolve_project_from_message(
    db: Session, user_obj: Any, message: str, project_scope: set[str]
) -> tuple[str | None, str | None]:
    for query in _candidate_queries_from_message(message):
        rows = search_svc.search_projects(db, user_obj, q=query, limit=5)
        rows = [row for row in rows if str(row.get("id")) in project_scope]
        if rows:
            top = rows[0]
            return str(top.get("project_name") or query), str(top.get("id"))
    return None, None


def _resolve_user_from_message(
    db: Session, user_obj: Any, message: str, user_scope: set[str]
) -> tuple[str | None, str | None]:
    for query in _candidate_queries_from_message(message):
        rows = search_svc.search_users(db, user_obj, q=query, limit=5)
        rows = [row for row in rows if str(row.get("id")) in user_scope]
        if rows:
            top = rows[0]
            return str(top.get("name") or query), str(top.get("id"))
    return None, None


def _message_has_scoped_entities(db: Session, user_obj: Any, message: str) -> bool:
    role = _role(user_obj)
    project_scope = _accessible_project_ids(db, user_obj, role)
    user_scope = _accessible_user_ids(db, user_obj, role, project_scope)
    for query in _candidate_queries_from_message(message, max_items=8):
        project_rows = search_svc.search_projects(db, user_obj, q=query, limit=1)
        if any(str(row.get("id")) in project_scope for row in project_rows):
            return True
        if role != "EMPLOYEE":
            user_rows = search_svc.search_users(db, user_obj, q=query, limit=1)
            if any(str(row.get("id")) in user_scope for row in user_rows):
                return True
    return False


def _scope_signal_score(
    db: Session,
    user_obj: Any,
    message: str,
    history: list[dict[str, str]],
) -> float:
    text = str(message or "").strip().lower()
    if not text:
        return 0.0
    score = 0.0
    if FOLLOW_UP_TOKENS.search(text) and history:
        score += 0.35

    hit_keywords = {token for token in SCOPE_KEYWORDS if token in text}
    score += min(0.45, 0.09 * len(hit_keywords))

    if _message_has_scoped_entities(db, user_obj, text):
        score += 0.45

    if re.search(r"\b\d{4}-\d{2}(?:-\d{2})?\b", text) or re.search(r"\b\d+(?:\.\d+)?%?\b", text):
        score += 0.08

    return max(0.0, min(1.0, score))


def _is_supported_question(
    db: Session,
    user_obj: Any,
    message: str,
    history: list[dict[str, str]],
) -> bool:
    return _scope_signal_score(db, user_obj, message, history) >= COPILOT_SCOPE_THRESHOLD


def _resolver(
    db: Session,
    user_obj: Any,
    message: str,
    intent: IntentOut,
    month_iso: str,
    prefs: dict[str, Any],
) -> tuple[ResolvedContext, dict[str, Any]]:
    role = _role(user_obj)
    mem = prefs.get("user_preferences", {}) or {}
    current_month = _month_start(date.today()).isoformat()
    follow_up = bool(FOLLOW_UP_TOKENS.search(str(message or "").lower()))
    if intent.month:
        resolved_month = _normalize_month(intent.month, fallback_iso=current_month)
    elif follow_up and str(mem.get("default_month") or "").strip():
        resolved_month = _normalize_month(str(mem.get("default_month")), fallback_iso=current_month)
    else:
        resolved_month = current_month
    projects_scope = _accessible_project_ids(db, user_obj, role)
    users_scope = _accessible_user_ids(db, user_obj, role, projects_scope)

    explicit_project_name = str(intent.project_name or "").strip() or None
    remembered_project_name = str(mem.get("last_project_name") or "").strip() or None
    project_name = explicit_project_name
    if not project_name and intent.intent == "draft_invoice":
        project_name = remembered_project_name
    requested_project_name = project_name
    project_matches = search_svc.search_projects(db, user_obj, q=project_name or "", limit=10) if project_name else []
    project_matches = [row for row in project_matches if str(row.get("id")) in projects_scope]
    project_id = str(project_matches[0]["id"]) if project_matches else None
    resolved_project_name = str(project_matches[0]["project_name"]) if project_matches else project_name
    if not project_id and not explicit_project_name and intent.intent in {"project_health", "draft_invoice", "utilization"}:
        inferred_name, inferred_id = _resolve_project_from_message(
            db, user_obj, message, projects_scope
        )
        if inferred_id:
            resolved_project_name = inferred_name
            project_id = inferred_id
    if not project_id:
        resolved_project_name = None

    requested_user_name = None
    if role == "EMPLOYEE":
        user_id = str(user_obj.id)
        resolved_user_name = str(getattr(user_obj, "name", ""))
    else:
        explicit_user_name = str(intent.user_name or "").strip() or None
        remembered_user_name = str(mem.get("last_user_name") or "").strip() or None
        user_name = explicit_user_name
        if not user_name and intent.intent == "utilization":
            user_name = remembered_user_name
        requested_user_name = user_name
        user_matches = search_svc.search_users(db, user_obj, q=user_name or "", limit=10) if user_name else []
        user_matches = [row for row in user_matches if str(row.get("id")) in users_scope]
        user_id = str(user_matches[0]["id"]) if user_matches else None
        resolved_user_name = str(user_matches[0]["name"]) if user_matches else user_name
        if not user_id and not explicit_user_name and intent.intent == "utilization":
            inferred_user_name, inferred_user_id = _resolve_user_from_message(
                db, user_obj, message, users_scope
            )
            if inferred_user_id:
                resolved_user_name = inferred_user_name
                user_id = inferred_user_id
        if not user_id:
            resolved_user_name = None

    ctx = ResolvedContext(
        month_iso=resolved_month,
        role=role,
        project_name=resolved_project_name,
        project_id=project_id,
        user_name=resolved_user_name,
        user_id=user_id,
        filters=_coerce_filters(intent.filters),
        accessible_projects=projects_scope,
        accessible_users=users_scope,
    )
    trace = {
        "node": "resolver",
        "status": "ok",
        "role": role,
        "month": resolved_month,
        "project_name_requested": requested_project_name,
        "project_name": resolved_project_name,
        "project_id_found": bool(project_id),
        "user_name_requested": requested_user_name,
        "user_name": resolved_user_name,
        "user_id_found": bool(user_id),
    }
    return ctx, trace


def _apply_project_filters(rows: list[dict[str, Any]], ctx: ResolvedContext) -> list[dict[str, Any]]:
    out = [row for row in rows if str(row.get("project_id") or row.get("id") or "") in (ctx.accessible_projects or set())]
    if ctx.project_name:
        out = [row for row in out if ctx.project_name.lower() in str(row.get("project_name", "")).lower()]
    f = ctx.filters or {}
    if f.get("budget_consumed_gt") is not None:
        out = [row for row in out if float(row.get("percent_budget_consumed", 0.0)) > float(f["budget_consumed_gt"])]
    if f.get("forecast_gt") is not None:
        out = [row for row in out if float(row.get("forecast_vs_budget_pct", 0.0)) > float(f["forecast_gt"])]
    return out


def _apply_utilization_filters(rows: list[dict[str, Any]], ctx: ResolvedContext, user_obj: Any) -> list[dict[str, Any]]:
    out = list(rows)
    if ctx.role == "EMPLOYEE":
        out = [row for row in out if str(row.get("user_id") or row.get("employee_id")) == str(user_obj.id)]
    elif ctx.role == "PM":
        out = [
            row
            for row in out
            if str(row.get("user_id") or row.get("employee_id")) in (ctx.accessible_users or set())
        ]
    if ctx.user_name:
        out = [
            row
            for row in out
            if ctx.user_name.lower() in str(row.get("name") or row.get("employee_name") or "").lower()
        ]
    if ctx.user_id:
        out = [row for row in out if str(row.get("user_id") or row.get("employee_id")) == str(ctx.user_id)]
    return out

def _tool_call(
    db: Session,
    user_obj: Any,
    message: str,
    intent: IntentOut,
    ctx: ResolvedContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    datasets = [d for d in (intent.datasets or _default_datasets(intent.intent)) if d in ALLOWED_DATASETS]
    if not datasets:
        datasets = ["portfolio_overview"]

    month_obj = date.fromisoformat(ctx.month_iso)
    results: dict[str, Any] = {}
    errors: dict[str, Any] = {}

    for dataset in datasets:
        try:
            if dataset == "portfolio_overview":
                dash = reporting_svc.dashboard(db, month_obj, user=user_obj)
                results[dataset] = {
                    "month": dash.get("month"),
                    "projects": _apply_project_filters(list(dash.get("projects", []) or []), ctx),
                    "utilization": _apply_utilization_filters(list(dash.get("utilization", []) or []), ctx, user_obj),
                }
            elif dataset == "project_health":
                if ctx.project_id:
                    if str(ctx.project_id) not in (ctx.accessible_projects or set()):
                        raise HTTPException(status_code=403, detail="Project is outside your role scope")
                    results[dataset] = {
                        "projects": [
                            project_health_svc.compute_project_health(
                                db,
                                ctx.project_id,
                                user_obj=user_obj,
                                approved_only=True,
                            )
                        ]
                    }
                else:
                    dash = reporting_svc.dashboard(db, month_obj, user=user_obj)
                    scoped = _apply_project_filters(list(dash.get("projects", []) or []), ctx)
                    scoped.sort(key=lambda row: float(row.get("forecast_vs_budget_pct", 0.0)), reverse=True)
                    top_ids = [str(row.get("project_id")) for row in scoped[:3] if row.get("project_id")]
                    projects = [
                        project_health_svc.compute_project_health(
                            db,
                            pid,
                            user_obj=user_obj,
                            approved_only=True,
                        )
                        for pid in top_ids
                    ]
                    results[dataset] = {"projects": projects}
            elif dataset == "invoice_readiness":
                out = reporting_svc.invoice_readiness(db, month_obj, user=user_obj)
                rows = _apply_project_filters(list(out.get("projects", []) or []), ctx)
                readiness_lt = (ctx.filters or {}).get("readiness_lt")
                if readiness_lt is not None:
                    rows = [row for row in rows if float(row.get("readiness_pct", 0.0)) < float(readiness_lt)]
                results[dataset] = {"month": out.get("month"), "projects": rows}
            elif dataset == "pending_approvals":
                rows = approvals_svc.list_pending_for_pm(db, user_obj)
                project_ids = {ts.project_id for ts in rows if getattr(ts, "project_id", None) is not None}
                employee_ids = {ts.employee_id for ts in rows if getattr(ts, "employee_id", None) is not None}
                project_name_by_id: dict[str, str] = {}
                employee_name_by_id: dict[str, str] = {}
                if project_ids:
                    project_name_by_id = {
                        str(pid): str(pname)
                        for pid, pname in db.query(Project.id, Project.project_name).filter(Project.id.in_(project_ids)).all()
                    }
                if employee_ids:
                    employee_name_by_id = {
                        str(uid): str(uname)
                        for uid, uname in db.query(User.id, User.name).filter(User.id.in_(employee_ids)).all()
                    }
                results[dataset] = {
                    "pending_timesheets": [
                        {
                            "timesheet_ref": str(ts.id)[:8],
                            "employee_name": str(ts.employee_name or employee_name_by_id.get(str(ts.employee_id)) or "Employee"),
                            "project_name": str(project_name_by_id.get(str(ts.project_id)) or "Project"),
                            "period_start": str(ts.period_start),
                            "period_end": str(ts.period_end),
                            "status": ts.status,
                        }
                        for ts in rows
                    ]
                }
            elif dataset == "utilization":
                if ctx.project_id:
                    if str(ctx.project_id) not in (ctx.accessible_projects or set()):
                        raise HTTPException(status_code=403, detail="Project is outside your role scope")
                    health = project_health_svc.compute_project_health(
                        db,
                        ctx.project_id,
                        user_obj=user_obj,
                        approved_only=True,
                    )
                    rows = _apply_utilization_filters(list(health.get("employee_utilization", []) or []), ctx, user_obj)
                    results[dataset] = {"project_name": health.get("project_name"), "employee_utilization": rows}
                else:
                    dash = reporting_svc.dashboard(db, month_obj, user=user_obj)
                    rows = _apply_utilization_filters(list(dash.get("utilization", []) or []), ctx, user_obj)
                    results[dataset] = {"month": dash.get("month"), "utilization": rows}
            elif dataset == "anomalies":
                metric = str((ctx.filters or {}).get("anomaly_metric") or "spend_to_date")
                if metric not in {"spend_to_date", "burn_rate"}:
                    metric = "spend_to_date"
                out = reporting_svc.anomalies(db, month_obj, metric, user=user_obj)
                rows = _apply_project_filters(list(out.get("anomalies", []) or []), ctx)
                results[dataset] = {"month": out.get("month"), "metric": out.get("metric"), "anomalies": rows}
            elif dataset == "draft_invoice":
                if not ctx.project_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Draft invoice requires a project in your accessible scope.",
                    )
                if str(ctx.project_id) not in (ctx.accessible_projects or set()):
                    raise HTTPException(status_code=403, detail="Project is outside your role scope")
                inv = invoicing_svc.draft_invoice(db, user_obj, ctx.project_id, month_obj)
                results[dataset] = {
                    "project_name": ctx.project_name,
                    "invoice_month": str(inv.invoice_month),
                    "status": inv.status,
                    "subtotal": float(inv.subtotal),
                    "adjustments_total": float(inv.adjustments_total),
                    "total": float(inv.total),
                }
            elif dataset == "text_search":
                docs = retrieval_svc.semantic_search(
                    db,
                    query=message,
                    top_k=5,
                    source_type=None,
                    project_id=ctx.project_id,
                    month=ctx.month_iso[:7],
                )
                filtered = []
                for item in docs:
                    attrs = item.get("attrs", {}) if isinstance(item.get("attrs"), dict) else {}
                    pid = str(attrs.get("project_id") or "")
                    eid = str(attrs.get("employee_id") or "")
                    if pid and pid not in (ctx.accessible_projects or set()):
                        continue
                    if ctx.role == "EMPLOYEE" and eid and eid != str(user_obj.id):
                        continue
                    filtered.append(item)
                results[dataset] = {
                    "query": message,
                    "project_name": ctx.project_name,
                    "month": ctx.month_iso[:7],
                    "matches": [
                        {
                            "score": float(item.get("score", 0.0)),
                            "source_type": item.get("source_type"),
                            "text": str(item.get("text", ""))[:220],
                        }
                        for item in filtered
                    ],
                }
        except HTTPException as exc:
            errors[dataset] = str(exc.detail)
        except Exception as exc:
            logger.exception("dataset failed: %s", dataset)
            errors[dataset] = str(exc)

    payload = {
        "intent": intent.intent,
        "ok": bool(results),
        "datasets": results,
        "errors": errors,
        "context": {
            "role": ctx.role,
            "month": ctx.month_iso,
            "project_name": ctx.project_name,
            "user_name": ctx.user_name,
        },
    }
    trace = {
        "node": "tool_call",
        "status": "ok" if results else "error",
        "intent": intent.intent,
        "datasets": datasets,
        "result_preview": json.dumps(payload, default=str)[:700],
    }
    return payload, trace


def _compact(value: Any) -> Any:
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, list):
        out = [_compact(item) for item in value[:8]]
        if len(value) > 8:
            out.append(f"... ({len(value) - 8} more)")
        return out
    if isinstance(value, dict):
        return {str(k): _compact(v) for k, v in value.items()}
    return value


def _role_tone(role: str) -> str:
    mapping = {
        "PM": "Use PM tone: action-oriented, risk and schedule focused.",
        "FINANCE": "Use Finance tone: budget variance, readiness, and cashflow focused.",
        "ADMIN": "Use Admin tone: governance and portfolio control focused.",
        "EMPLOYEE": "Use Employee tone: personal scope and practical next steps.",
    }
    return mapping.get(role, "Use concise professional ERP tone.")


def _fmt_money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except Exception:
        return "N/A"


def _fmt_pct(value: Any, scale: float = 1.0) -> str:
    try:
        return f"{float(value) * scale:.1f}%"
    except Exception:
        return "N/A"


_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_ISO_MONTH_RE = re.compile(r"\b(\d{4})-(\d{2})(?!-\d{2})\b")


def _fmt_natural_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "N/A"
    try:
        dt = date.fromisoformat(raw[:10])
        return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    except Exception:
        pass
    m = re.match(r"^(\d{4})-(\d{2})$", raw)
    if m:
        try:
            month_dt = date(int(m.group(1)), int(m.group(2)), 1)
            return f"{month_dt.strftime('%B')} {month_dt.year}"
        except Exception:
            return raw
    return raw


def _naturalize_dates_in_text(text: str) -> str:
    if not text:
        return text

    def _date_sub(match: re.Match[str]) -> str:
        return _fmt_natural_date(match.group(0))

    def _month_sub(match: re.Match[str]) -> str:
        return _fmt_natural_date(match.group(0))

    out = _ISO_DATE_RE.sub(_date_sub, str(text))
    out = _ISO_MONTH_RE.sub(_month_sub, out)
    return out


def _friendly_project_name(row: dict[str, Any]) -> str:
    name = str(row.get("project_name") or "").strip()
    return name if name else "Project"


def _friendly_employee_name(row: dict[str, Any]) -> str:
    name = str(row.get("employee_name") or row.get("name") or row.get("user_name") or "").strip()
    return name if name else "Employee"


def _as_list_str(value: Any) -> list[str]:
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _project_health_lines(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows = list(payload.get("projects", []) or [])
    lines: list[str] = []
    evidence: list[str] = [f"Project health rows: {len(rows)}"]
    for row in rows[:3]:
        name = _friendly_project_name(row)
        risk_score = row.get("risk_score")
        cost_to_date = row.get("cost_to_date")
        budget = row.get("budget")
        forecast = row.get("forecast_total_cost_at_end")
        exceed = row.get("forecast_budget_exceed_date")
        line = (
            f"- {name}: risk {_fmt_pct(risk_score)} | spent {_fmt_money(cost_to_date)} / "
            f"budget {_fmt_money(budget)} | forecast {_fmt_money(forecast)}"
        )
        if exceed:
            line += f" | projected budget reach {_fmt_natural_date(exceed)}"
        lines.append(line)
    return lines, evidence


def _portfolio_lines(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows = list(payload.get("projects", []) or [])
    lines: list[str] = []
    evidence: list[str] = [f"Portfolio projects in scope: {len(rows)}", f"Month: {_fmt_natural_date(payload.get('month'))}"]
    ranked = sorted(rows, key=lambda row: float(row.get("forecast_vs_budget_pct", 0.0)), reverse=True)
    for row in ranked[:3]:
        name = _friendly_project_name(row)
        line = (
            f"- {name}: spent {_fmt_money(row.get('spend_to_date'))}, budget {_fmt_money(row.get('budget'))}, "
            f"forecast vs budget {_fmt_pct(row.get('forecast_vs_budget_pct'))}"
        )
        lines.append(line)
    return lines, evidence


def _readiness_lines(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows = list(payload.get("projects", []) or [])
    lines = [
        f"- {_friendly_project_name(row)}: readiness {_fmt_pct(row.get('readiness_pct'))}"
        for row in rows[:5]
    ]
    evidence = [f"Invoice readiness rows: {len(rows)}", f"Month: {_fmt_natural_date(payload.get('month'))}"]
    return lines, evidence


def _utilization_lines(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows = payload.get("employee_utilization")
    if rows is None:
        rows = payload.get("utilization", [])
    rows = list(rows or [])
    lines: list[str] = []
    for row in rows[:5]:
        name = _friendly_employee_name(row)
        util = row.get("utilization_logged")
        if util is None:
            util = float(row.get("utilization_pct", 0.0)) / 100.0
        billable_hours = row.get("billable_hours")
        total_hours = row.get("total_hours")
        line = f"- {name}: utilization {_fmt_pct(util, 100.0)}"
        if billable_hours is not None or total_hours is not None:
            line += f" | billable {billable_hours or 0}h / total {total_hours or 0}h"
        lines.append(line)
    evidence = [f"Utilization rows: {len(rows)}"]
    return lines, evidence


def _anomaly_lines(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows = list(payload.get("anomalies", []) or [])
    lines = [
        (
            f"- {_friendly_project_name(row)}: delta {_fmt_pct(row.get('delta_pct'))}, "
            f"z-score {row.get('z_score')}"
        )
        for row in rows[:5]
    ]
    evidence = [f"Anomaly rows: {len(rows)}", f"Metric: {payload.get('metric')}", f"Month: {_fmt_natural_date(payload.get('month'))}"]
    return lines, evidence


def _pending_lines(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows = list(payload.get("pending_timesheets", []) or [])
    lines = [
        (
            f"- {str(row.get('project_name') or 'Project')}: "
            f"{str(row.get('employee_name') or 'Employee')} pending approval "
            f"for {_fmt_natural_date(row.get('period_start'))} to {_fmt_natural_date(row.get('period_end'))}"
        )
        for row in rows[:5]
    ]
    evidence = [f"Pending approvals: {len(rows)}"]
    return lines, evidence


def _draft_invoice_lines(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    lines = [
        (
            f"- {str(payload.get('project_name') or 'Project')}: invoice month {_fmt_natural_date(payload.get('invoice_month'))}, "
            f"subtotal {_fmt_money(payload.get('subtotal'))}, total {_fmt_money(payload.get('total'))}"
        )
    ]
    evidence = [f"Draft invoice status: {payload.get('status')}"]
    return lines, evidence


def _text_search_lines(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows = list(payload.get("matches", []) or [])
    lines = [
        f"- score {float(row.get('score', 0.0)):.2f}: {str(row.get('text') or '').strip()}"
        for row in rows[:5]
    ]
    evidence = [f"Text matches: {len(rows)}", f"Month filter: {_fmt_natural_date(payload.get('month'))}"]
    return lines, evidence


def _coerce_summary_payload(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    reply = (
        raw.get("reply")
        or raw.get("summary")
        or raw.get("message")
        or raw.get("answer")
        or raw.get("text")
    )
    if not reply:
        return None
    evidence = raw.get("evidence")
    if evidence is None:
        evidence = raw.get("key_points")
    actions = raw.get("recommended_actions")
    if actions is None:
        actions = raw.get("actions")
    if actions is None:
        actions = raw.get("next_steps")
    confidence = raw.get("confidence", 0.55)
    try:
        conf = float(confidence)
        if conf > 1.0:
            conf = conf / 100.0
    except Exception:
        conf = 0.55
    return {
        "reply": str(reply).strip(),
        "evidence": _as_list_str(evidence),
        "recommended_actions": _as_list_str(actions),
        "confidence": conf,
    }


_VALUE_TOKEN_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?|\b\d{4}-\d{2}-\d{2}\b")


def _extract_value_tokens(text: str) -> set[str]:
    return {token.strip().lower() for token in _VALUE_TOKEN_RE.findall(str(text or "")) if str(token).strip()}


def _is_grounded_reply(candidate: str, ground_truth: str) -> bool:
    text = str(candidate or "").strip()
    if len(text) < 40:
        return False
    banned = {
        "i retrieved the required erp data",
        "data sources used",
        "confidence:",
        "recommended next steps",
    }
    lowered = text.lower()
    if any(item in lowered for item in banned):
        return False
    truth_tokens = _extract_value_tokens(ground_truth)
    if not truth_tokens:
        return True
    cand_tokens = _extract_value_tokens(text)
    if not cand_tokens:
        return False
    overlap = truth_tokens.intersection(cand_tokens)
    required = 1
    return len(overlap) >= required


def _fallback_summary(tool_result: dict[str, Any], role: str) -> SummaryOut:
    if not tool_result.get("ok"):
        detail = "; ".join(f"{k}: {v}" for k, v in (tool_result.get("errors") or {}).items()) or "No rows returned for current role scope and filters."
        return SummaryOut(
            reply=(
                "I checked your current scope, and this request returned zero rows.\n"
                f"Role: {role}\n"
                f"Details: {detail}"
            ),
            evidence=[],
            recommended_actions=[],
            confidence=0.3,
        )

    datasets = tool_result.get("datasets") or {}
    dataset_names = sorted(datasets.keys())
    lines: list[str] = []
    evidence: list[str] = [f"Role context: {role}"]

    for name in dataset_names:
        payload = datasets.get(name) or {}
        if name == "project_health":
            detail_lines, detail_evidence = _project_health_lines(payload)
        elif name == "portfolio_overview":
            detail_lines, detail_evidence = _portfolio_lines(payload)
        elif name == "invoice_readiness":
            detail_lines, detail_evidence = _readiness_lines(payload)
        elif name == "utilization":
            detail_lines, detail_evidence = _utilization_lines(payload)
        elif name == "anomalies":
            detail_lines, detail_evidence = _anomaly_lines(payload)
        elif name == "pending_approvals":
            detail_lines, detail_evidence = _pending_lines(payload)
        elif name == "draft_invoice":
            detail_lines, detail_evidence = _draft_invoice_lines(payload)
        elif name == "text_search":
            detail_lines, detail_evidence = _text_search_lines(payload)
        else:
            detail_lines, detail_evidence = [], []
        lines.extend(detail_lines)
        evidence.extend(detail_evidence)

    if not lines:
        lines.append("- Result set is empty for current role scope and filters.")

    return SummaryOut(
        reply=(
            f"Based on your {role} access, here is what I found:\n"
            + "\n".join(lines)
        ),
        evidence=list(dict.fromkeys(evidence)),
        recommended_actions=[],
        confidence=0.72,
    )


def _summarizer(
    message: str,
    history: list[dict[str, str]],
    role: str,
    tool_result: dict[str, Any],
) -> tuple[SummaryOut, dict[str, Any]]:
    deterministic = _fallback_summary(tool_result, role)
    if not tool_result.get("ok"):
        return deterministic, {"node": "summarizer", "status": "fallback"}

    prompt = [
        {
            "role": "system",
            "content": (
                "Return strict JSON only with key: reply.\n"
                "Reply must be plain text, human-readable, and concise.\n"
                "Keep the same facts and numeric values from ground_truth. Do not invent numbers.\n"
                "Use human-friendly names for projects and employees.\n"
                "Do not mention raw UUIDs or internal IDs.\n"
                "No markdown tables.\n"
                f"{_role_tone(role)}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "message": message,
                    "history_tail": history[-8:],
                    "role": role,
                    "tool_result": _compact(tool_result),
                    "ground_truth": deterministic.reply,
                },
                default=str,
            ),
        },
    ]
    raw = _openai_json(prompt)
    if raw:
        try:
            payload = _coerce_summary_payload(raw) or raw
            summary = SummaryOut(**payload)
            summary.confidence = max(0.0, min(1.0, float(summary.confidence)))
            if _is_grounded_reply(summary.reply, deterministic.reply):
                summary.reply = _naturalize_dates_in_text(summary.reply)
                return summary, {"node": "summarizer", "status": "ok"}
            logger.warning("summarizer output rejected as ungrounded")
        except Exception:
            logger.exception("summary parser failed")
    deterministic.reply = _naturalize_dates_in_text(deterministic.reply)
    return deterministic, {"node": "summarizer", "status": "fallback"}


def _apply_memory_updates(
    db: Session,
    prefs_row: UserPreference,
    prefs: dict[str, Any],
    intent: IntentOut,
    resolved: ResolvedContext,
) -> dict[str, Any]:
    user_prefs = dict(prefs.get("user_preferences") or {})
    updates: dict[str, Any] = {}

    if resolved.month_iso and user_prefs.get("default_month") != resolved.month_iso:
        user_prefs["default_month"] = resolved.month_iso
        updates["default_month"] = resolved.month_iso
    if resolved.project_name and user_prefs.get("last_project_name") != resolved.project_name:
        user_prefs["last_project_name"] = resolved.project_name
        updates["last_project_name"] = resolved.project_name
    if resolved.user_name and user_prefs.get("last_user_name") != resolved.user_name:
        user_prefs["last_user_name"] = resolved.user_name
        updates["last_user_name"] = resolved.user_name
    if user_prefs.get("last_intent") != intent.intent:
        user_prefs["last_intent"] = intent.intent
        updates["last_intent"] = intent.intent

    datasets = [item for item in intent.datasets if item in ALLOWED_DATASETS]
    if user_prefs.get("last_datasets") != datasets:
        user_prefs["last_datasets"] = datasets
        updates["last_datasets"] = datasets

    filters = _coerce_filters(intent.filters)
    if user_prefs.get("last_filters") != filters:
        user_prefs["last_filters"] = filters
        updates["last_filters"] = filters

    if not updates:
        return {}

    new_prefs = dict(prefs)
    new_prefs["user_preferences"] = user_prefs
    prefs_row.prefs = new_prefs
    db.commit()
    db.refresh(prefs_row)
    return {"user_preferences": updates}

def _node_intent_router(state: CopilotState) -> dict[str, Any]:
    intent, trace = _intent_router(
        state["message"],
        state.get("history", []),
        state["month_iso"],
        state["prefs"],
        _role(state["user_obj"]),
    )
    return {"intent": intent, "tool_trace": _append_trace(state, trace)}


def _node_resolver(state: CopilotState) -> dict[str, Any]:
    resolved, trace = _resolver(
        state["db"],
        state["user_obj"],
        state["message"],
        state["intent"],
        state["month_iso"],
        state["prefs"],
    )
    return {"resolved": resolved, "tool_trace": _append_trace(state, trace)}


def _node_tool_call(state: CopilotState) -> dict[str, Any]:
    tool_result, trace = _tool_call(
        state["db"],
        state["user_obj"],
        state["message"],
        state["intent"],
        state["resolved"],
    )
    return {"tool_result": tool_result, "tool_trace": _append_trace(state, trace)}


def _node_summarizer(state: CopilotState) -> dict[str, Any]:
    summary, trace = _summarizer(
        state["message"],
        state.get("history", []),
        state["resolved"].role,
        state["tool_result"],
    )
    return {"summary": summary, "tool_trace": _append_trace(state, trace)}


def _node_memory(state: CopilotState) -> dict[str, Any]:
    updates = _apply_memory_updates(
        db=state["db"],
        prefs_row=state["prefs_row"],
        prefs=state["prefs"],
        intent=state["intent"],
        resolved=state["resolved"],
    )
    return {"memory_updates": updates}


def _compile_graph():
    workflow = StateGraph(CopilotState)
    workflow.add_node("intent_router", _node_intent_router)
    workflow.add_node("resolver", _node_resolver)
    workflow.add_node("tool_call", _node_tool_call)
    workflow.add_node("summarizer", _node_summarizer)
    workflow.add_node("memory", _node_memory)
    workflow.set_entry_point("intent_router")
    workflow.add_edge("intent_router", "resolver")
    workflow.add_edge("resolver", "tool_call")
    workflow.add_edge("tool_call", "summarizer")
    workflow.add_edge("summarizer", "memory")
    workflow.add_edge("memory", END)
    return workflow.compile()


def _get_graph():
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = _compile_graph()
    return _COMPILED_GRAPH


def run_copilot_chat(
    db: Session,
    user_obj: Any,
    message: str,
    history: list[dict[str, Any]] | None = None,
    month: str | None = None,
) -> dict[str, Any]:
    history = history or []
    normalized_history = [
        {"role": "assistant" if row.get("role") == "assistant" else "user", "content": str(row.get("content", ""))}
        for row in history
    ]
    try:
        clean_message = str(message or "").strip()
        if not clean_message:
            return {
                "reply": (
                    "Please ask a project, timesheet, approval, invoice, utilization, or report question."
                ),
                "memory_updates": {},
                "trace": [],
            }
        scope_score = _scope_signal_score(db, user_obj, clean_message, normalized_history)
        prefs, prefs_row = _load_user_preferences(db, user_obj.id)
        month_iso = _normalize_month(month, fallback_iso=_month_start(date.today()).isoformat())

        graph = _get_graph()
        final_state: CopilotState = graph.invoke(
            {
                "db": db,
                "user_obj": user_obj,
                "message": clean_message,
                "history": normalized_history,
                "prefs": prefs,
                "prefs_row": prefs_row,
                "month_iso": month_iso,
                "tool_trace": [],
            }
        )

        summary = final_state.get("summary") or SummaryOut(
            reply="Chat Assistant could not summarize this request.",
            evidence=[],
            recommended_actions=[],
            confidence=0.2,
        )
        trace = list(final_state.get("tool_trace", []))
        trace.insert(
            0,
            {
                "node": "scope_gate",
                "status": "pass" if scope_score >= COPILOT_SCOPE_THRESHOLD else "soft-pass",
                "score": round(float(scope_score), 3),
                "threshold": float(COPILOT_SCOPE_THRESHOLD),
                "note": (
                    "Low-scope query; executed best-effort retrieval within role scope."
                    if scope_score < COPILOT_SCOPE_THRESHOLD
                    else "Scope confidence met threshold."
                ),
            },
        )
        return {
            "reply": summary.reply,
            "memory_updates": dict(final_state.get("memory_updates", {})),
            "trace": trace,
        }
    except Exception as exc:
        logger.exception("chat assistant graph failed for user_id=%s", getattr(user_obj, "id", "unknown"))
        return {
            "reply": "Chat Assistant could not process this request right now.",
            "memory_updates": {},
            "trace": [],
        }
