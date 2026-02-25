from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.services import search as svc

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/projects")
def search_projects(
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return svc.search_projects(db, user, q=q, limit=limit)


@router.get("/users")
def search_users(
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    return svc.search_users(db, user, q=q, limit=limit)
