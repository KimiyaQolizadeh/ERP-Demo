from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.services import audit as audit_svc

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
def recent_logs(limit: int = 50, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Only admin can view audit logs")
    rows = audit_svc.list_recent_events(db, limit=limit)
    return [
        {
            "id": str(r.id),
            "ts": r.ts.isoformat() if r.ts else None,
            "user_id": str(r.user_id) if r.user_id else None,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": str(r.entity_id) if r.entity_id else None,
            "meta": r.meta or {},
        }
        for r in rows
    ]
