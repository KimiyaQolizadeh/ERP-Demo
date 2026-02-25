from __future__ import annotations

import re
from datetime import date, timedelta

from pydantic import BaseModel, Field

from app.services.ai.client import ai_enabled, call_structured

WEEKDAY_MAP = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


class ParsedEntry(BaseModel):
    work_date: str = Field(..., description="YYYY-MM-DD")
    hours: float = Field(..., ge=0.25, le=24)
    discipline: str
    billable: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str


class ParseResult(BaseModel):
    entries: list[ParsedEntry]


def _resolve_date(segment: str, week_start: date) -> str:
    s = segment.lower()
    for token, offset in WEEKDAY_MAP.items():
        if re.search(rf"\b{re.escape(token)}\b", s):
            return (week_start + timedelta(days=offset)).isoformat()
    return week_start.isoformat()


def _resolve_hours(segment: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*h", segment.lower())
    if m:
        hours = float(m.group(1))
        return min(24.0, max(0.25, hours))
    return 1.0


def _resolve_discipline(segment: str, disciplines: list[str]) -> str:
    lower = segment.lower()
    for d in disciplines:
        if d.lower() in lower:
            return d
    return disciplines[0] if disciplines else "General"


def _resolve_billable(segment: str) -> bool:
    lower = segment.lower()
    if any(k in lower for k in ["internal", "training", "admin", "pto", "holiday"]):
        return False
    return True


def _fallback_parse(text: str, week_start: date, disciplines: list[str]) -> ParseResult:
    raw_segments = [s.strip() for s in re.split(r"[;\n]+", text or "") if s.strip()]
    entries: list[ParsedEntry] = []
    for segment in raw_segments:
        entries.append(
            ParsedEntry(
                work_date=_resolve_date(segment, week_start),
                hours=_resolve_hours(segment),
                discipline=_resolve_discipline(segment, disciplines),
                billable=_resolve_billable(segment),
                confidence=0.6,
                notes=segment,
            )
        )
    return ParseResult(entries=entries)


def parse_timesheet_transcript(
    transcript: str,
    week_start: date,
    disciplines: list[str],
    project_name: str,
) -> ParseResult:
    if not transcript.strip():
        return ParseResult(entries=[])
    if not ai_enabled():
        return _fallback_parse(transcript, week_start, disciplines)

    system = (
        "You convert transcript text into ERP timesheet entries.\n"
        "Rules:\n"
        "- Resolve weekday words against week_start.\n"
        "- Use one of allowed disciplines only.\n"
        "- Notes must not add new facts.\n"
        "- Return JSON with entries[] containing work_date,hours,discipline,billable,confidence,notes."
    )
    user = (
        f"week_start: {week_start.isoformat()}\n"
        f"allowed_disciplines: {disciplines}\n"
        f"project_name: {project_name}\n"
        f"transcript: {transcript}\n"
    )
    parsed, _raw = call_structured(ParseResult, system, user)
    if parsed:
        return parsed
    return _fallback_parse(transcript, week_start, disciplines)
