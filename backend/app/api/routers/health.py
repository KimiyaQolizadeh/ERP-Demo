from fastapi import APIRouter
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import SessionLocal

router = APIRouter()

@router.get("/health")
def health():
    db: Session = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    finally:
        db.close()