# backend/app/api/routers/users.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.tables import User
from app.models.schemas import UserOut

router = APIRouter(prefix="/users", tags=["users"])


def _list_users(db: Session) -> list[User]:
    users = db.query(User).order_by(User.role, User.name).all()
    return list(users)


def _to_user_out(users: list[User]) -> list[UserOut]:
    return [
        UserOut(
            id=str(u.id),
            name=u.name,
            role=u.role,
            discipline=u.discipline
        )
        for u in users
    ]


@router.get("/login-options", response_model=list[UserOut])
def list_login_options(db: Session = Depends(get_db)):
    return _to_user_out(_list_users(db))


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _ = user
    return _to_user_out(_list_users(db))
