Project Overview
You are building a simplified Project Management module for an internal ERP system used by
a professional services firm (e.g., EFI Engineering).
This module must connect:
Timesheets → Project Budgets → Invoicing → Reporting
into a single integrated workflow.
The system should support project managers in understanding:
● project financial health
● utilization
● progress against budget
● invoicing readiness
Functional Requirements

1. Timesheets
   Create functionality that allows employees to submit time entries which include:
   ● Employee Name
   ● Project
   ● Discipline or Department
   ● Hours Worked
   ● Billable vs Non-Billable
   ● Notes describing work completed
   Timesheets must:
   ● be submitted for approval
   ● support approval/rejection by a Project Manager
   ● become eligible for invoicing only after approval
2. Projects
   Each project must support:
   Project Setup
   ● Project Name
   ● Client Name
   ● Division (ICI, Cx, SD)
   ● Discipline
   ● Assigned Project Manager
   ● Project Start / End Date
   Commercial Structure
   ● Contract Type
   ○ Hourly
   ○ Lump Sum
   ● Billing Rate Schedule (by role or discipline)
   ● Approved Budget
   Workflow Status
   Projects must support lifecycle states:
   ● Proposal
   ● Awarded
   ● Completed
   ● Cancelled
   ● Not Awarded
   If "Not Awarded", capture reason.
3. Invoicing
   Enable invoice generation based on:
   ● Approved Timesheets
   ● Project Billing Structure
   Invoices should:
   ● aggregate approved billable hours
   ● calculate billable value using rate schedule
   ● be generated monthly per project
   ● allow manual adjustment before approval
   Bonus:
   Export or JSON representation of invoice.
   Reporting Requirements
   Provide at least one dashboard or report showing:
   ● Project Budget vs Spend
   ● Billable vs Non-Billable Hours
   ● Percent Budget Consumed
   ● Estimated Remaining Budget
   Bonus:
   ● Forecast to completion
   ● Utilization by employee
   ● Profit estimate
   Automation / AI Requirement
   Introduce at least one AI-assisted or automated feature, such as:
   ● Generating timesheet notes from a short prompt
   ● Voice/text input that creates a timesheet entry
   ● Auto-classification of billable vs non-billable
   ● Automatic invoice draft generation
   ● Burn rate forecasting
   ● Project risk flagging
   You may use any third-party AI tools or APIs.
