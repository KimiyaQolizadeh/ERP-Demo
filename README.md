# ERP Project Management Module (AI + Automation Enabled)

## Overview
This repository implements a simplified ERP project controls module that connects:

Timesheets -> Approvals -> Invoicing -> Reporting -> Copilot

The system is designed for demo readiness with deterministic finance calculations and AI-assisted workflows.

## Tech Stack
- Backend: FastAPI + SQLAlchemy 2.0 + Postgres
- Frontend: Streamlit multipage app
- AI: OpenAI API (notes rewrite, parsing, risk explanation, copilot routing/summarization)
- Rule/ML Assist: deterministic billable rules + confidence outputs
- Agentic orchestration: Copilot tool graph (`/copilot/chat`)

## Setup
From repository root:

1. Start database
```bash
docker compose up -d
```

2. Initialize backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.db.init_db
python -m app.db.seed
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

3. Initialize frontend (new terminal)
```bash
cd frontend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Backend docs: `http://127.0.0.1:8000/docs`
Frontend: `http://localhost:8501`

## Functional Coverage

### Timesheets
- Employee creates draft timesheets and entries with:
  - project, discipline, hours, billable flag, notes, work date
- Workflow enforcement:
  - `DRAFT -> SUBMITTED -> APPROVED/REJECTED`
  - only owner edits draft
  - only project PM approves/rejects submitted entries

### Projects
- Full project setup available in API + UI:
  - project name, client, division, discipline, PM, start/end, contract type, approved budget, status
- Lifecycle statuses supported:
  - `PROPOSAL`, `AWARDED`, `COMPLETED`, `CANCELLED`, `NOT_AWARDED`
- `NOT_AWARDED` requires reason (validated in service)
- Rate schedule management per project (role/discipline rates)

### Invoicing
- Monthly project draft invoices
- Eligibility guardrails:
  - approved timesheets only
  - billable entries only
  - uninvoiced entries only (`invoiced_line_id IS NULL`)
  - only `AWARDED` or `COMPLETED` projects
- Supports commercial structures:
  - `HOURLY`: line amounts by `hours * rate_key`
  - `LUMP_SUM`: progress value based on approved work, capped by remaining approved contract value
- Manual adjustments before finance approval
- JSON export endpoint

### Reporting / Dashboard
- Deterministic backend metrics:
  - budget vs spend
  - billable vs non-billable hours
  - percent budget consumed
  - estimated remaining budget
  - forecast to completion
  - utilization by employee
  - invoice readiness
  - risk index bar + AI narrative explanation based on provided metrics

### Automation / AI
- AI note rewrite (no new facts rule)
- Text/voice parsing to timesheet entry suggestions
- Billable classification + probability/confidence and review zone
- AI risk explanation from deterministic inputs only
- Copilot chat with tool traces (approvals, dashboard, readiness, draft invoice)
- AI acceptance/audit logging

## Architecture Decisions
- Thin routers, business logic in `backend/app/services/*`
- Centralized RBAC and workflow checks in services/authz layer
- Deterministic financial math is backend-owned; AI never computes invoice totals
- Streamlit pages use `frontend/client/api.py` wrapper to standardize error handling
- Seed data creates a usable demo story (pending approvals, invoice-ready entries, risk/readiness contrasts)

## Data Model (High-Level)
- `users`
- `projects` + `rate_schedule`
- `timesheets` + `time_entries`
- `invoices` + `invoice_lines` + `invoice_adjustments`
- `audit_log`
- `user_preferences` (copilot defaults/memory)
- `vector_documents` (optional retrieval indexing for AI)

## Trade-offs
- Focused on correctness and demonstrability over production hardening (no migrations framework yet)
- Copilot routing uses constrained tool selection with fallback heuristics for reliability
- LUMP_SUM invoicing uses deterministic progress-value logic capped by remaining contract value
- Auth is header-based (`X-User-Id`) for demo speed instead of full auth stack

## Demo Flow
1. Home: select user identity
2. Projects: create/update project and rate schedule, including lifecycle transitions
3. Timesheets: create draft, add entries, use AI assist, submit
4. Approvals (PM): approve/reject submitted timesheets
5. Invoicing (PM/Finance): generate monthly draft, adjust, approve, export
6. Dashboard: review budget, forecast, readiness, utilization, risk explanation
7. Copilot: ask for pending approvals, health summary, readiness, or invoice draft guidance
