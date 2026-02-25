from app.db.session import engine
from app.db.base import Base
from sqlalchemy import text
from app.models import tables  # noqa: F401  (ensures models are imported)

def main():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE timesheets ADD COLUMN IF NOT EXISTS employee_name VARCHAR(200)"))
        conn.execute(
            text(
                """
                UPDATE timesheets t
                SET employee_name = u.name
                FROM users u
                WHERE t.employee_id = u.id
                  AND (t.employee_name IS NULL OR btrim(t.employee_name) = '')
                """
            )
        )
    print("DB tables created.")

if __name__ == "__main__":
    main()
