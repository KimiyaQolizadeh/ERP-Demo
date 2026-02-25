from __future__ import annotations

import math
from typing import Any

from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import get_openai_api_key, get_openai_embed_model
from app.models.tables import TimeEntry, Timesheet, VectorDocument


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _embed(texts: list[str]) -> list[list[float]]:
    key = get_openai_api_key()
    if not key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY not configured")

    client = OpenAI(api_key=key)
    resp = client.embeddings.create(
        model=get_openai_embed_model(),
        input=texts,
    )
    return [list(item.embedding) for item in resp.data]


def _time_entry_search_text(entry: TimeEntry, ts: Timesheet) -> str:
    return (
        f"{entry.work_date} | project={ts.project_id} | discipline={entry.discipline} | "
        f"hours={float(entry.hours)} | billable={entry.billable} | notes={entry.notes}"
    )


def index_time_entry_note(db: Session, entry_id: str) -> VectorDocument:
    row = (
        db.query(TimeEntry, Timesheet)
        .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
        .filter(TimeEntry.id == entry_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Time entry not found")

    entry, ts = row
    text = _time_entry_search_text(entry, ts)
    attrs = {
        "project_id": str(ts.project_id),
        "employee_id": str(ts.employee_id),
        "month": str(entry.work_date)[:7],
        "billable": bool(entry.billable),
        "timesheet_status": ts.status,
    }
    emb = _embed([text])[0]

    existing = (
        db.query(VectorDocument)
        .filter(VectorDocument.source_type == "time_entry_note")
        .filter(VectorDocument.source_id == entry.id)
        .first()
    )
    if existing:
        existing.text = text
        existing.attrs = attrs
        existing.embedding = emb
        db.commit()
        db.refresh(existing)
        return existing

    doc = VectorDocument(
        source_type="time_entry_note",
        source_id=entry.id,
        text=text,
        attrs=attrs,
        embedding=emb,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def semantic_search(
    db: Session,
    query: str,
    top_k: int = 5,
    source_type: str | None = None,
    project_id: str | None = None,
    month: str | None = None,
) -> list[dict[str, Any]]:
    query_emb = _embed([query])[0]

    docs = db.query(VectorDocument).all()
    if source_type:
        docs = [d for d in docs if d.source_type == source_type]

    if project_id:
        docs = [d for d in docs if str((d.attrs or {}).get("project_id", "")) == str(project_id)]

    if month:
        docs = [d for d in docs if str((d.attrs or {}).get("month", "")) == str(month)]

    scored: list[tuple[float, VectorDocument]] = []
    for doc in docs:
        if not isinstance(doc.embedding, list):
            continue
        score = _cosine(query_emb, [float(v) for v in doc.embedding])
        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[: max(1, min(top_k, 20))]

    out: list[dict[str, Any]] = []
    for score, doc in selected:
        result: dict[str, Any] = {
            "doc_id": str(doc.id),
            "source_type": doc.source_type,
            "source_id": str(doc.source_id) if doc.source_id else None,
            "score": float(score),
            "attrs": doc.attrs or {},
            "text": doc.text,
        }
        # Postgres is still source of truth: fetch canonical row by ID.
        if doc.source_type == "time_entry_note" and doc.source_id:
            entry = db.query(TimeEntry).filter(TimeEntry.id == doc.source_id).first()
            if entry:
                result["source_row"] = {
                    "time_entry_id": str(entry.id),
                    "work_date": str(entry.work_date),
                    "discipline": entry.discipline,
                    "hours": float(entry.hours),
                    "billable": bool(entry.billable),
                    "notes": entry.notes,
                }
        out.append(result)
    return out
