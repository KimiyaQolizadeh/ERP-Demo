from app.db.session import SessionLocal
from app.models.tables import User
from app.services.approvals import list_pending_for_pm


def run() -> None:
    db = SessionLocal()
    try:
        pm_user = db.query(User).filter(User.role == "PM").first()
        if not pm_user:
            raise RuntimeError("No PM user found. Run seed first: python -m app.db.seed")

        rows = list_pending_for_pm(db, pm_user)
        assert isinstance(rows, list), "list_pending_for_pm must return a list"
        print(f"OK: PM {pm_user.id} pending approvals count = {len(rows)}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
