from app.models.tables import User, Project, Timesheet, Invoice

def is_admin(u: User) -> bool:
    return u.role == "ADMIN"

def is_finance(u: User) -> bool:
    return u.role == "FINANCE" or is_admin(u)

def is_pm(u: User) -> bool:
    return u.role == "PM" or is_admin(u)

def is_employee(u: User) -> bool:
    return u.role == "EMPLOYEE" or is_admin(u)


def can_view_project(u: User, project: Project, linked_to_project: bool = False) -> bool:
    if is_admin(u) or is_finance(u):
        return True
    if is_pm(u) and project.pm_user_id == u.id:
        return True
    return linked_to_project

def can_view_timesheet(u: User, ts: Timesheet, project: Project) -> bool:
    if is_admin(u) or is_finance(u):
        return True
    if is_pm(u) and project.pm_user_id == u.id:
        return True
    return ts.employee_id == u.id

def can_edit_timesheet(u: User, ts: Timesheet) -> bool:
    if is_admin(u):
        return True
    return u.role == "EMPLOYEE" and ts.employee_id == u.id and ts.status == "DRAFT"

def can_submit_timesheet(u: User, ts: Timesheet) -> bool:
    return can_edit_timesheet(u, ts)

def can_approve_timesheet(u: User, project: Project) -> bool:
    return is_pm(u) and project.pm_user_id == u.id

def can_draft_invoice(u: User, project: Project) -> bool:
    return (is_pm(u) and project.pm_user_id == u.id) or is_finance(u)

def can_approve_invoice(u: User) -> bool:
    return is_finance(u)
