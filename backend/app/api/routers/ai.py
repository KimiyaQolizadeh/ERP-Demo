from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import (
    get_env_search_paths,
    get_openai_api_key,
    get_openai_embed_model,
    get_openai_model,
    get_openai_transcribe_model,
)
from app.db.session import get_db
from app.services.ai import notes as notes_svc
from app.services.ai import retrieval as retrieval_svc
from app.services.ai import risk as risk_svc
from app.services.ai import speech as speech_svc
from app.services.ai.billable_rules import refine_with_llm_if_review, score_billable_rules
from app.services.ai.client import ai_enabled
from app.services.ai.parser import parse_timesheet_transcript
from app.services.ai.transcribe import transcribe_wav_bytes
from app.services.audit import log_event

router = APIRouter(prefix="/ai", tags=["ai"])


class ParseTextIn(BaseModel):
    text: str
    week_start: date
    disciplines: list[str] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)


class NotesIn(BaseModel):
    raw_notes: str
    discipline: str | None = None
    project_name: str | None = None


class BillableIn(BaseModel):
    notes: str
    discipline: str | None = None
    contract_type: str | None = None


class RiskIn(BaseModel):
    title: str
    metrics: dict[str, Any]


class AcceptIn(BaseModel):
    action: str
    entity_type: str = "AI"
    entity_id: str | None = None
    accepted: bool = True
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class RetrievalIndexIn(BaseModel):
    entry_id: str


class RetrievalSearchIn(BaseModel):
    query: str
    top_k: int = 5
    source_type: str | None = None
    project_id: str | None = None
    month: str | None = None  # YYYY-MM


class VoiceSynthesizeIn(BaseModel):
    text: str
    voice: str = "alloy"
    response_format: str = "mp3"
    model: str | None = None


@router.get("/status")
def ai_status(probe: bool = False, user=Depends(get_current_user)):
    key = get_openai_api_key()
    env_paths = get_env_search_paths()
    out = {
        "api_key_configured": bool(key),
        "api_key_hint": f"...{key[-4:]}" if len(key) >= 4 else "",
        "model": get_openai_model(),
        "transcribe_model": get_openai_transcribe_model(),
        "env_paths_checked": [{"path": p, "exists": Path(p).exists()} for p in env_paths],
    }

    if probe:
        if not key:
            out["provider_ok"] = False
            out["provider_error"] = "OPENAI_API_KEY is missing"
            return out

        try:
            from openai import OpenAI

            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(
                model=get_openai_model(),
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                temperature=0,
            )
            text = resp.choices[0].message.content or ""
            out["provider_ok"] = True
            out["provider_reply"] = text[:50]
        except Exception as exc:
            out["provider_ok"] = False
            message = str(exc)
            if "unexpected keyword argument 'proxies'" in message:
                message = (
                    f"{message}. Dependency mismatch detected: openai/httpx. "
                    "Use httpx<0.28 with openai 1.40.x, or upgrade openai."
                )
            out["provider_error"] = message

    return out


def _parse_disciplines_form(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass
    return [x.strip() for x in raw.split(",") if x.strip()]


def _project_name_from_context(projects: list[dict]) -> str:
    if not projects:
        return ""
    first = projects[0] or {}
    return str(first.get("project_name", ""))


def _normalize_parse_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        normalized.append(
            {
                "work_date": str(entry.get("work_date", "")),
                "discipline": str(entry.get("discipline", "")),
                "hours": float(entry.get("hours", 0) or 0),
                "billable_suggestion": bool(entry.get("billable", False)),
                "confidence": float(entry.get("confidence", 0) or 0),
                "notes_clean": str(entry.get("notes", "")).strip(),
            }
        )
    return normalized


@router.post("/improve-notes")
def improve_notes(payload: NotesIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    result, meta = notes_svc.improve_notes(
        raw=payload.raw_notes,
        discipline=payload.discipline,
        project_name=payload.project_name,
    )
    response = {"result": result.model_dump(), "meta": meta}
    log_event(
        db,
        str(user.id),
        "AI_NOTES",
        "Timesheet",
        None,
        {
            "input": payload.model_dump(),
            "output": response["result"],
            "model": get_openai_model() if meta.get("used_ai") else "rules_cleanup",
            "confidence": None,
            "accepted": False,
        },
    )
    return response


@router.post("/parse-timesheet-text")
def parse_timesheet_text(payload: ParseTextIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    project_name = _project_name_from_context(payload.projects)
    parsed = parse_timesheet_transcript(
        transcript=payload.text,
        week_start=payload.week_start,
        disciplines=payload.disciplines or ["Mechanical", "Electrical", "Civil", "PM"],
        project_name=project_name,
    )
    entries = _normalize_parse_entries([e.model_dump() for e in parsed.entries])
    parse_model = get_openai_model() if ai_enabled() else "parser_fallback"
    response = {"result": {"entries": entries}, "meta": {"source": "text"}}
    log_event(
        db,
        str(user.id),
        "AI_PARSE",
        "Timesheet",
        None,
        {
            "input": payload.model_dump(),
            "output": response["result"],
            "model": parse_model,
            "confidence": None,
            "accepted": False,
        },
    )
    return response


@router.post("/voice/transcribe")
async def voice_transcribe(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    wav_bytes = await audio.read()
    try:
        transcript = transcribe_wav_bytes(wav_bytes)
        response = {"transcript": transcript}
        log_event(
            db,
            str(user.id),
            "AI_PARSE",
            "Timesheet",
            None,
            {
                "input": {"audio_bytes": len(wav_bytes)},
                "output": response,
                "model": get_openai_transcribe_model(),
                "confidence": None,
                "accepted": False,
            },
        )
        return response
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Voice transcription failed: {exc}")


@router.post("/voice/parse")
async def voice_parse(
    week_start: date = Form(...),
    discipline_choices: str = Form("[]"),
    project_name: str = Form(""),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    wav_bytes = await audio.read()
    try:
        transcript = transcribe_wav_bytes(wav_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Voice transcription failed: {exc}")

    disciplines = _parse_disciplines_form(discipline_choices) or ["Mechanical", "Electrical", "Civil", "PM"]
    parsed = parse_timesheet_transcript(
        transcript=transcript,
        week_start=week_start,
        disciplines=disciplines,
        project_name=project_name,
    )
    entries = _normalize_parse_entries([e.model_dump() for e in parsed.entries])
    parse_model = get_openai_model() if ai_enabled() else "parser_fallback"
    response = {"transcript": transcript, "result": {"entries": entries}, "meta": {"source": "voice"}}
    log_event(
        db,
        str(user.id),
        "AI_PARSE",
        "Timesheet",
        None,
        {
            "input": {
                "week_start": str(week_start),
                "discipline_choices": disciplines,
                "project_name": project_name,
                "audio_bytes": len(wav_bytes),
            },
            "output": response["result"],
            "model": parse_model,
            "confidence": None,
            "accepted": False,
        },
    )
    return response


@router.post("/voice/synthesize")
def voice_synthesize(payload: VoiceSynthesizeIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        audio_bytes, model_used, response_format = speech_svc.synthesize_text_to_speech(
            payload.text,
            voice=payload.voice,
            response_format=payload.response_format,
            model=payload.model,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Voice synthesis failed: {exc}")

    log_event(
        db,
        str(user.id),
        "AI_VOICE_SYNTH",
        "ChatAssistant",
        None,
        {
            "input": {"chars": len(payload.text or ""), "voice": payload.voice, "format": payload.response_format},
            "output": {"bytes": len(audio_bytes)},
            "model": model_used,
            "accepted": False,
        },
    )
    media_type = f"audio/{response_format}"
    return Response(content=audio_bytes, media_type=media_type, headers={"X-AI-Model": model_used})


@router.post("/billable/classify")
def billable_classify_v2(payload: BillableIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    base = score_billable_rules(payload.notes)
    refined, refine_meta = refine_with_llm_if_review(
        notes=payload.notes,
        discipline=payload.discipline,
        contract_type=payload.contract_type,
        rules_result=base,
    )
    out = {
        "suggested_billable": bool(refined["suggested_billable"]),
        "confidence": float(refined["confidence"]),
        "status": str(refined["status"]),
        "matched": list(refined.get("matched", [])),
    }
    log_event(
        db,
        str(user.id),
        "AI_CLASSIFY",
        "TimeEntry",
        None,
        {
            "input": payload.model_dump(),
            "output": out,
            "model": refine_meta.get("model", "rules_catalog"),
            "confidence": out["confidence"],
            "accepted": False,
        },
    )
    return out


@router.post("/classify-billable")
def billable_classify_compat(payload: BillableIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    out = billable_classify_v2(payload, db=db, user=user)
    return {"result": out, "meta": {"compatible": True}}


@router.post("/billable-probability")
def billable_probability_compat(payload: BillableIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    out = billable_classify_v2(payload, db=db, user=user)
    return {
        "billable_probability": out["confidence"],
        "top_signals": out["matched"],
        "status": out["status"],
        "suggested_billable": out["suggested_billable"],
    }


@router.post("/explain-risk")
def explain_risk(payload: RiskIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    result, meta = risk_svc.explain_risk(payload.title, payload.metrics)
    response = {"result": result.model_dump(), "meta": meta}
    log_event(
        db,
        str(user.id),
        "AI_RISK",
        "Project",
        None,
        {
            "input": payload.model_dump(),
            "output": response["result"],
            "model": get_openai_model() if meta.get("used_ai") else "rules_risk",
            "confidence": None,
            "accepted": False,
        },
    )
    return response


@router.post("/accept")
def accept_suggestion(payload: AcceptIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    action = payload.action if payload.action.startswith("AI_ACCEPTED_") else f"AI_ACCEPTED_{payload.action}"
    log_event(
        db,
        str(user.id),
        action,
        payload.entity_type,
        payload.entity_id,
        {
            "input": payload.input,
            "output": payload.output,
            "accepted": bool(payload.accepted),
        },
    )
    return {"ok": True}


@router.post("/retrieval/index-time-entry")
def retrieval_index_time_entry(payload: RetrievalIndexIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    doc = retrieval_svc.index_time_entry_note(db, payload.entry_id)
    out = {
        "doc_id": str(doc.id),
        "source_type": doc.source_type,
        "source_id": str(doc.source_id) if doc.source_id else None,
        "attrs": doc.attrs or {},
    }
    log_event(
        db,
        str(user.id),
        "AI_RETRIEVAL_INDEX",
        "VectorDocument",
        str(doc.id),
        {"input": payload.model_dump(), "output": out, "model": get_openai_embed_model(), "accepted": False},
    )
    return out


@router.post("/retrieval/search")
def retrieval_search(payload: RetrievalSearchIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = retrieval_svc.semantic_search(
        db=db,
        query=payload.query,
        top_k=payload.top_k,
        source_type=payload.source_type,
        project_id=payload.project_id,
        month=payload.month,
    )
    out = {"results": rows}
    log_event(
        db,
        str(user.id),
        "AI_RETRIEVAL_SEARCH",
        "VectorDocument",
        None,
        {"input": payload.model_dump(), "output_count": len(rows), "model": get_openai_embed_model(), "accepted": False},
    )
    return out
