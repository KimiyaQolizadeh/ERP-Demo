from __future__ import annotations
from pydantic import BaseModel, Field

from app.services.ai.client import ai_enabled, call_structured

class NotesOut(BaseModel):
    improved_notes: str = Field(min_length=5)

def improve_notes(raw: str, discipline: str | None = None, project_name: str | None = None) -> tuple[NotesOut, dict]:
    raw_clean = " ".join((raw or "").split()).strip()
    if not raw_clean:
        return NotesOut(improved_notes="Worked on assigned project tasks."), {"used_ai": False, "raw": ""}

    # If no AI, do a light cleanup
    if not ai_enabled():
        return NotesOut(improved_notes=raw_clean[:1].upper() + raw_clean[1:]), {"used_ai": False, "raw": ""}

    system = (
        "You rewrite timesheet notes for invoicing/audit.\n"
        "Rules:\n"
        "- Rewrite ONLY; do not add new facts.\n"
        "- Keep 1-2 sentences.\n"
        "- Return ONLY JSON: {\"improved_notes\": \"...\"}"
    )
    user = f"""
Raw notes: {raw_clean}
Discipline: {discipline or ""}
Project: {project_name or ""}

Return JSON:
{{"improved_notes":"..."}}"""

    out, raw_resp = call_structured(NotesOut, system, user)
    if out:
        return out, {"used_ai": True, "raw": raw_resp}
    return NotesOut(improved_notes=raw_clean[:1].upper() + raw_clean[1:]), {"used_ai": False, "raw": raw_resp}