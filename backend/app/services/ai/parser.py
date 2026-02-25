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

MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

NUMBER_WORDS = {
    "zero": 0.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "eleven": 11.0,
    "twelve": 12.0,
    "thirteen": 13.0,
    "fourteen": 14.0,
    "fifteen": 15.0,
    "sixteen": 16.0,
    "seventeen": 17.0,
    "eighteen": 18.0,
    "nineteen": 19.0,
    "twenty": 20.0,
    "thirty": 30.0,
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

def _word_number_value(text: str) -> float | None:
    tokens = [tok for tok in re.split(r"[\s-]+", text.lower()) if tok]
    if not tokens:
        return None
    total = 0.0
    found = False
    for tok in tokens:
        if tok in {"and", "a", "an"}:
            continue
        if tok in {"half", "quarter"}:
            total += 0.5 if tok == "half" else 0.25
            found = True
            continue
        if tok not in NUMBER_WORDS:
            return None
        total += NUMBER_WORDS[tok]
        found = True
    return total if found else None


def _resolve_hours(segment: str) -> float:
    lower = segment.lower()
    direct = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\b", lower)
    if direct:
        return min(24.0, max(0.25, float(direct.group(1))))
    for text_num in re.finditer(
        r"\b([a-z][a-z\s-]{0,24})\s*(?:hours?|hrs?|hr)\b",
        lower,
    ):
        parsed = _word_number_value(text_num.group(1).strip())
        if parsed is not None:
            return min(24.0, max(0.25, parsed))
    return 1.0


def _extract_note_text(segment: str) -> str:
    for pattern in [
        r"\bnotes?\s*(?:is|are|:)\s*(.+)$",
        r"\bdescription\s*(?:is|:)\s*(.+)$",
    ]:
        m = re.search(pattern, segment, flags=re.IGNORECASE)
        if m:
            note = str(m.group(1) or "").strip(" .,:;\"'")
            if note:
                return note
    return segment.strip()


def _parse_date_expression(text: str, week_start: date) -> date | None:
    candidate = str(text or "").strip()
    if not candidate:
        return None

    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", candidate)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except Exception:
            pass

    month_day = re.search(
        r"\b("
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|"
        r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
        r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b",
        candidate,
        flags=re.IGNORECASE,
    )
    if month_day:
        month_key = month_day.group(1).lower()
        month = MONTH_MAP.get(month_key)
        day_val = int(month_day.group(2))
        year_val = int(month_day.group(3)) if month_day.group(3) else week_start.year
        if month:
            try:
                return date(year_val, month, day_val)
            except Exception:
                pass

    numeric = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", candidate)
    if numeric:
        month = int(numeric.group(1))
        day_val = int(numeric.group(2))
        year_val = int(numeric.group(3)) if numeric.group(3) else week_start.year
        try:
            return date(year_val, month, day_val)
        except Exception:
            pass

    weekday_iso = _resolve_date(candidate, week_start)
    if weekday_iso != week_start.isoformat():
        return date.fromisoformat(weekday_iso)
    return None


def _expand_date_range(start: date, end: date, max_days: int = 14) -> list[str]:
    if end < start:
        try:
            end = date(start.year + 1, end.month, end.day)
        except Exception:
            return [start.isoformat()]
    span = (end - start).days
    if span < 0 or span > max_days:
        return [start.isoformat()]
    return [(start + timedelta(days=offset)).isoformat() for offset in range(span + 1)]


def _resolve_work_dates(segment: str, week_start: date) -> list[str]:
    range_match = re.search(
        r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:[,.;\n]|$)",
        segment,
        flags=re.IGNORECASE,
    )
    if range_match:
        start = _parse_date_expression(range_match.group(1), week_start)
        end = _parse_date_expression(range_match.group(2), week_start)
        if start and end:
            return _expand_date_range(start, end)

    explicit = _parse_date_expression(segment, week_start)
    if explicit:
        return [explicit.isoformat()]

    return [_resolve_date(segment, week_start)]


def _has_total_hours_hint(segment: str) -> bool:
    return bool(
        re.search(r"\btotal\b", segment, flags=re.IGNORECASE)
        or re.search(r"\bacross\b", segment, flags=re.IGNORECASE)
    )


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
        work_dates = _resolve_work_dates(segment, week_start)
        resolved_hours = _resolve_hours(segment)
        if len(work_dates) > 1 and _has_total_hours_hint(segment):
            resolved_hours = max(0.25, round(resolved_hours / len(work_dates), 2))
        note_text = _extract_note_text(segment)
        entries.append(
            ParsedEntry(
                work_date=work_dates[0],
                hours=resolved_hours,
                discipline=_resolve_discipline(segment, disciplines),
                billable=_resolve_billable(segment),
                confidence=0.75 if note_text != segment.strip() else 0.68,
                notes=note_text,
            )
        )
        if len(work_dates) > 1:
            for work_date in work_dates[1:]:
                entries.append(
                    ParsedEntry(
                        work_date=work_date,
                        hours=resolved_hours,
                        discipline=_resolve_discipline(segment, disciplines),
                        billable=_resolve_billable(segment),
                        confidence=0.75 if note_text != segment.strip() else 0.68,
                        notes=note_text,
                    )
                )
    return ParseResult(entries=entries)


def _is_default_like_result(parsed: ParseResult, transcript: str, week_start: date) -> bool:
    if len(parsed.entries) != 1:
        return False
    entry = parsed.entries[0]
    return (
        abs(float(entry.hours) - 1.0) < 1e-9
        and str(entry.work_date) == week_start.isoformat()
        and str(entry.notes or "").strip().lower() == transcript.strip().lower()
    )


def _has_range_hint(text: str) -> bool:
    return bool(re.search(r"\bfrom\b.+\bto\b", text, flags=re.IGNORECASE))


def parse_timesheet_transcript(
    transcript: str,
    week_start: date,
    disciplines: list[str],
    project_name: str,
) -> ParseResult:
    clean = transcript.strip()
    if not clean:
        return ParseResult(entries=[])
    fallback = _fallback_parse(clean, week_start, disciplines)
    if not ai_enabled():
        return fallback

    system = (
        "You convert transcript text into ERP timesheet entries.\n"
        "Rules:\n"
        "- Understand explicit date ranges like 'from February 20 to February 22' and output one entry per date.\n"
        "- Parse spoken hour values (e.g., 'six hours').\n"
        "- If user says 'note is ...', use only that notes text.\n"
        "- Resolve weekday words against week_start.\n"
        "- Use one of allowed disciplines only.\n"
        "- Notes must not add new facts.\n"
        "- Return JSON with entries[] containing work_date,hours,discipline,billable,confidence,notes."
    )
    user = (
        f"week_start: {week_start.isoformat()}\n"
        f"allowed_disciplines: {disciplines}\n"
        f"project_name: {project_name}\n"
        f"transcript: {clean}\n"
    )
    parsed, _raw = call_structured(ParseResult, system, user)
    if parsed:
        if _is_default_like_result(parsed, clean, week_start) and fallback.entries:
            return fallback
        if _has_range_hint(clean) and len(fallback.entries) > 1 and len(parsed.entries) == 1:
            return fallback
        return parsed
    return fallback
