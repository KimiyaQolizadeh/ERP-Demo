from app.db.session import engine
from app.db.base import Base
from sqlalchemy import text
from app.models import tables  # noqa: F401  (ensures models are imported)

def main():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE timesheets ADD COLUMN IF NOT EXISTS employee_name VARCHAR(200)"))
    print("DB tables created.")

if __name__ == "__main__":
    main()
