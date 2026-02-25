from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.tables import Project, Timesheet, User
from app.services import authz


def _rank_text(query: str, candidate: str) -> tuple[int, int]:
    q = (query or "").strip().lower()
    c = (candidate or "").strip().lower()
    if not q or not c:
        return (2, len(c))
    if c.startswith(q):
        return (0, len(c))
    if q in c:
        return (1, len(c))
    return (2, len(c))


def _scoped_project_rows(db: Session, user) -> list[Project]:
    q = db.query(Project)
    if authz.is_finance(user):
        return q.all()
    if authz.is_pm(user):
        return q.filter(Project.pm_user_id == user.id).all()
    return (
        q.join(Timesheet, Timesheet.project_id == Project.id)
        .filter(Timesheet.employee_id == user.id)
        .distinct()
        .all()
    )


def _scoped_user_rows(db: Session, user) -> list[User]:
    if authz.is_finance(user):
        return db.query(User).all()
    if authz.is_pm(user):
        managed_project_rows = (
            db.query(Project.id).filter(Project.pm_user_id == user.id).all()
        )
        managed_project_ids = [pid for (pid,) in managed_project_rows if pid is not None]
        if not managed_project_ids:
            return []
        employee_rows = (
            db.query(Timesheet.employee_id)
            .filter(Timesheet.project_id.in_(managed_project_ids))
            .distinct()
            .all()
        )
        employee_ids = [uid for (uid,) in employee_rows if uid is not None]
        if str(user.id) not in {str(uid) for uid in employee_ids}:
            employee_ids.append(user.id)
        return db.query(User).filter(User.id.in_(employee_ids)).all() if employee_ids else []
    return db.query(User).filter(User.id == user.id).all()


def search_projects(db: Session, user, q: str, limit: int = 20) -> list[dict]:
    query = (q or "").strip()
    rows = _scoped_project_rows(db, user)
    matches: list[tuple[tuple[int, int], dict]] = []
    for row in rows:
        name = str(row.project_name or "")
        rank = _rank_text(query, name)
        if query and rank[0] >= 2:
            continue
        matches.append(
            (
                rank,
                {
                    "id": str(row.id),
                    "project_name": name,
                    "status": str(row.status),
                    "client_name": str(row.client_name or ""),
                },
            )
        )
    matches.sort(key=lambda item: (item[0][0], item[0][1], item[1]["project_name"].lower()))
    return [item[1] for item in matches[: max(1, int(limit))]]


def search_users(db: Session, user, q: str, limit: int = 20) -> list[dict]:
    query = (q or "").strip()
    rows = _scoped_user_rows(db, user)
    matches: list[tuple[tuple[int, int], dict]] = []
    for row in rows:
        name = str(row.name or "")
        rank = _rank_text(query, name)
        if query and rank[0] >= 2:
            continue
        matches.append(
            (
                rank,
                {
                    "id": str(row.id),
                    "name": name,
                    "role": str(row.role),
                    "discipline": str(row.discipline or ""),
                },
            )
        )
    matches.sort(key=lambda item: (item[0][0], item[0][1], item[1]["name"].lower()))
    return [item[1] for item in matches[: max(1, int(limit))]]
