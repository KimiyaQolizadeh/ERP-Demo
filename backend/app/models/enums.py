from enum import Enum

class UserRole(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    PM = "PM"
    FINANCE = "FINANCE"
    ADMIN = "ADMIN"

class ProjectStatus(str, Enum):
    PROPOSAL = "PROPOSAL"
    AWARDED = "AWARDED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NOT_AWARDED = "NOT_AWARDED"

class ContractType(str, Enum):
    HOURLY = "HOURLY"
    LUMP_SUM = "LUMP_SUM"

class TimesheetStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class InvoiceStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SENT = "SENT"