import random
import datetime as dt
from faker import Faker
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.tables import (
    AuditLog,
    Invoice,
    InvoiceAdjustment,
    InvoiceLine,
    Project,
    RateSchedule,
    TimeEntry,
    Timesheet,
    User,
    UserPreference,
    VectorDocument,
)
from app.models.enums import UserRole, ProjectStatus, ContractType, TimesheetStatus

fake = Faker()
DISCIPLINES = ["Mechanical", "Electrical", "Civil"]
DIVISIONS = ["ICI", "Cx", "SD"]

def month_start(d: dt.date) -> dt.date:
    return dt.date(d.year, d.month, 1)

def seed():
    random.seed(42)
    today = dt.date.today()
    db: Session = SessionLocal()
    db.execute(text("ALTER TABLE timesheets ADD COLUMN IF NOT EXISTS employee_name VARCHAR(200)"))
    db.commit()

    # Clear existing
    db.query(AuditLog).delete()
    db.query(UserPreference).delete()
    db.query(VectorDocument).delete()
    db.query(InvoiceAdjustment).delete()
    db.query(InvoiceLine).delete()
    db.query(Invoice).delete()
    db.query(TimeEntry).delete()
    db.query(Timesheet).delete()
    db.query(RateSchedule).delete()
    db.query(Project).delete()
    db.query(User).delete()
    db.commit()

    # Users
    pms = [User(name=fake.name(), role=UserRole.PM.value, discipline="PM") for _ in range(2)]
    finance = User(name=fake.name(), role=UserRole.FINANCE.value, discipline="Finance")
    admin = User(name=fake.name(), role=UserRole.ADMIN.value, discipline="Admin")
    employees = [User(name=fake.name(), role=UserRole.EMPLOYEE.value, discipline=random.choice(DISCIPLINES)) for _ in range(6)]
    db.add_all(pms + [finance, admin] + employees)
    db.commit()

    db.refresh(finance)
    db.refresh(admin)
    for u in pms + employees:
        db.refresh(u)

    # Projects
    projects = []
    start = today - dt.timedelta(days=120)
    end = today + dt.timedelta(days=120)

    status_plan = [
        ProjectStatus.AWARDED.value,
        ProjectStatus.AWARDED.value,
        ProjectStatus.PROPOSAL.value,
        ProjectStatus.NOT_AWARDED.value,
        ProjectStatus.COMPLETED.value,
        ProjectStatus.CANCELLED.value,
        ProjectStatus.AWARDED.value,
        ProjectStatus.PROPOSAL.value,
    ]

    for i in range(8):
        pm = random.choice(pms)
        status = status_plan[i]
        reason = "Lost to competitor" if status == ProjectStatus.NOT_AWARDED.value else None
        budget = random.choice([150000, 200000, 250000, 300000])

        proj = Project(
            project_name=f"Project {chr(65+i)}",
            client_name=fake.company(),
            division=random.choice(DIVISIONS),
            discipline=random.choice(DISCIPLINES + ["PM"]),
            pm_user_id=pm.id,
            start_date=start,
            end_date=end,
            contract_type=random.choice([ContractType.HOURLY.value, ContractType.LUMP_SUM.value]),
            approved_budget=budget,
            status=status,
            not_awarded_reason=reason,
        )
        projects.append(proj)

    db.add_all(projects)
    db.commit()
    for p in projects:
        db.refresh(p)

    # Rate schedules for all projects
    for p in projects:
        for dk, rate in [("Mechanical", 140), ("Electrical", 160), ("Civil", 130), ("PM", 180)]:
            db.add(RateSchedule(project_id=p.id, rate_key=dk, rate=rate))
    db.commit()

    # Create patterns:
    # - risk_project: high burn
    # - readiness_project: many submitted not approved
    awarded_projects = [p for p in projects if p.status == ProjectStatus.AWARDED.value]
    risk_project = awarded_projects[0] if awarded_projects else projects[0]
    readiness_project = awarded_projects[1] if len(awarded_projects) > 1 else projects[1]

    # Timesheets + entries (8 weeks)
    for emp in employees:
        for w in range(8):
            period_end = today - dt.timedelta(days=7*w)
            period_start = period_end - dt.timedelta(days=6)

            # allocate more work to risk project
            project = risk_project if random.random() < 0.35 else random.choice(projects)

            status = random.choices(
                [TimesheetStatus.DRAFT.value, TimesheetStatus.SUBMITTED.value, TimesheetStatus.APPROVED.value, TimesheetStatus.REJECTED.value],
                weights=[0.1, 0.25, 0.55, 0.10],
            )[0]

            # readiness project: skew towards submitted (not approved)
            if project.id == readiness_project.id and random.random() < 0.6:
                status = TimesheetStatus.SUBMITTED.value

            ts = Timesheet(
                employee_id=emp.id,
                employee_name=emp.name,
                project_id=project.id,
                period_start=period_start,
                period_end=period_end,
                status=status,
                submitted_at=dt.datetime.now(dt.UTC) if status in (TimesheetStatus.SUBMITTED.value, TimesheetStatus.APPROVED.value, TimesheetStatus.REJECTED.value) else None,
                decided_at=dt.datetime.now(dt.UTC) if status in (TimesheetStatus.APPROVED.value, TimesheetStatus.REJECTED.value) else None,
                decided_by_pm=project.pm_user_id if status in (TimesheetStatus.APPROVED.value, TimesheetStatus.REJECTED.value) else None,
                rejection_reason="Missing detail" if status == TimesheetStatus.REJECTED.value else None,
            )
            db.add(ts)
            db.commit()
            db.refresh(ts)

            entries_n = random.randint(4, 6)
            for _ in range(entries_n):
                work_date = period_start + dt.timedelta(days=random.randint(0, 6))
                # risk project has heavier hours
                hours = random.choice([6, 8, 8]) if project.id == risk_project.id else random.choice([2, 4, 6, 8])
                discipline = emp.discipline if emp.discipline in DISCIPLINES else random.choice(DISCIPLINES)
                billable = random.random() < (0.85 if project.status == ProjectStatus.AWARDED.value else 0.6)
                notes = "Client coordination and design review" if billable else "Internal admin and training"
                db.add(TimeEntry(
                    timesheet_id=ts.id,
                    work_date=work_date,
                    discipline=discipline,
                    hours=hours,
                    billable=billable,
                    notes=notes,
                ))
            db.commit()

    print("Seed complete.")
    print(f"Users: {db.query(User).count()}, Projects: {db.query(Project).count()}, Timesheets: {db.query(Timesheet).count()}, Entries: {db.query(TimeEntry).count()}")
    db.close()

if __name__ == "__main__":
    seed()
