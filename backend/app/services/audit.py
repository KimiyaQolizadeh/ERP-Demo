from __future__ import annotations
import json

from sqlalchemy.orm import Session
from app.models.tables import AuditLog


def _json_safe(meta: dict | None) -> dict | None:
    if meta is None:
        return None
    return json.loads(json.dumps(meta, default=str))


def log_event(db: Session, user_id: str | None, action: str, entity_type: str, entity_id: str | None, meta: dict | None):
    row = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=_json_safe(meta),
    )
    db.add(row)
    db.commit()


def list_recent_events(db: Session, limit: int = 50) -> list[AuditLog]:
    safe_limit = max(1, min(int(limit), 200))
    return db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(safe_limit).all()
