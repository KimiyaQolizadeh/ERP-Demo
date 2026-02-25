import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.services.copilot.graph import run_copilot_chat

router = APIRouter(prefix="/copilot", tags=["copilot"])
logger = logging.getLogger("app.copilot.router")

class CopilotChatIn(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)  # [{"role":"user|assistant","content":"..."}]
    month: str | None = None  # "YYYY-MM-DD"

@router.post("/chat")
def chat(payload: CopilotChatIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        out = run_copilot_chat(
            db=db,
            user_obj=user,
            message=payload.message,
            history=payload.history,
            month=payload.month,
        )
        return {
            "reply": str(out.get("reply", "")),
            "memory_updates": dict(out.get("memory_updates", {})),
            "trace": list(out.get("trace", [])),
        }
    except Exception:
        logger.exception("Chat Assistant /chat route failed for user_id=%s", user.id)
        return {
            "reply": "Chat Assistant could not process this request right now.",
            "memory_updates": {},
            "trace": [],
        }
