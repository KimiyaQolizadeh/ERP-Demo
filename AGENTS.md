# AGENTS.md — Project Control Copilot (ERP PM Module)

You are Codex working inside this repository. Your job is to implement features safely, keep the system runnable, and produce manager-impressive UI + AI features.

## Project goal
Build an AI + automation enabled Project Management module for an internal ERP system:
Timesheets → Approvals → Invoicing → Reporting/Dashboard, plus AI-assisted workflows and an agentic “Copilot”.

This is a take-home assignment. Optimize for:
- correctness (ERP workflow rules)
- clarity (clean architecture + readable code)
- demo readiness (seed data + UI)
- AI features that are safe and explainable (no hallucinated totals)

## Tech stack (current)
- Backend: Python FastAPI, SQLAlchemy 2.0, Postgres (Docker)
- Frontend: Streamlit (multi-page)
- AI: OpenAI API for language tasks + explanations
- ML: scikit-learn for billable probability prediction (synthetic dataset + rules catalog)
- Agentic: LangGraph (graph orchestration). If LangChain deps cause issues, use LangGraph + OpenAI client directly.

## Non-negotiable ERP rules (must enforce)
1) Timesheet workflow:
   - Draft → Submitted → Approved/Rejected
   - Only the employee (owner) can edit Draft.
   - Only PM of the project can approve/reject Submitted.
2) Invoicing:
   - Only approved timesheet entries that are billable and not already invoiced can be invoiced.
   - Do NOT double invoice: use `time_entries.invoiced_line_id IS NULL` guard.
   - Only invoice projects with status Awarded or Completed.
3) Reporting:
   - Spend and totals are deterministic calculations (DB + backend math).
   - AI must never “invent” financial numbers.

## AI safety rules (must follow)
- AI outputs are suggestions, not truth.
- Always provide confidence/probability where relevant (billable probability).
- Always allow user override in UI.
- Keep deterministic computations (totals, burn rate, forecast numbers) in backend code.
- Use LLM for:
  - parsing free text into structured entries
  - note rewrite (rewrite only, no new facts)
  - explaining metrics/risk/anomalies (based on provided numbers)
- Never let LLM compute invoice totals or update approvals/invoice status directly.

## Repository structure (must respect)
- backend/app/api/routers/: thin HTTP layer, imports `router` symbol
- backend/app/services/: business logic + RBAC checks
- backend/app/models/: SQLAlchemy tables + Pydantic schemas
- backend/app/db/: session, init_db, seed
- backend/app/services/ai/: AI and ML utilities
- backend/app/services/copilot/: LangGraph/OpenAI tool orchestration (copilot)
- frontend/pages/: Streamlit pages
- frontend/client/api.py: robust API client wrapper with error handling

Do not put business logic into routers or Streamlit pages.

## Coding conventions
- Prefer small, testable functions.
- Use consistent naming:
  - routers export `router = APIRouter(...)`
  - service functions in `services/*`
  - avoid circular imports
- Always handle backend errors:
  - return JSON errors from API
  - frontend must catch and show errors (never crash on `.json()` decode)

## Seed data requirements (must maintain)
Seed must produce a demo story:
- 10 users: employees + PMs + finance + admin
- 8 projects with mixed statuses (Awarded, Proposal, Not Awarded with reason, Completed)
- Rate schedules per project
- 8 weeks of timesheets & entries
- Many Submitted (pending approvals) and many Approved (invoice-ready)
- At least one “at risk” project (forecast > budget) and one “low invoice readiness” project

## Key UX requirements (manager-friendly)
Dashboard must show:
- Budget consumed bar (green→yellow→red)
- Forecast vs budget bar (burn rate forecast)
- Invoice readiness bar
- Risk bar + label + “Explain risk” (AI)
- Utilization table
Timesheets page must show:
- Billable probability (%) + threshold slider + “Review zone”
- Button: Improve notes (AI)
- Button: Parse free text → preview entries → apply to draft timesheet (with confirmation)
Copilot page must:
- Provide chat interface
- Call tools (pending approvals, dashboard, readiness, draft invoice)
- Show trace/what tools were called
- Use memory (chat history passed from frontend; store minimal defaults optional)

## Commands you can run (Windows-friendly)
From repo root:
- Start DB: `docker compose up -d`

Backend:
- `cd backend`
- Create tables: `python -m app.db.init_db`
- Seed data: `python -m app.db.seed`
- Run API: `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

Frontend:
- `cd frontend`
- Run UI: `streamlit run streamlit_app.py`

## Definition of Done for any change
Every change must:
1) Keep backend importable (`python -c "import app.main"`)
2) Keep API runnable
3) Keep seed runnable
4) Keep UI pages loadable without crashes
5) Add or update minimal checks/tests when changing core workflow rules

## How to work (Codex task pattern)
When implementing a feature:
1) Identify files to edit (minimize churn).
2) Implement backend service + router.
3) Update frontend API client wrapper if endpoint added/changed.
4) Update Streamlit page UX.
5) Run seed + verify endpoints in `/docs`.
6) Provide a short summary of what changed and how to demo it.

## Common pitfalls to avoid
- Returning non-JSON errors (causes Streamlit JSONDecodeError)
- Missing `router` symbol in router files
- Using AI to compute totals
- Skipping RBAC checks in service layer
- Breaking Windows path imports (ensure `__init__.py` files exist in packages)

## What to build next (priority)
P0:
- Fix any import/runtime issues
- Stable dashboard with real burn rate forecast + risk bars
- Stable timesheet AI assist (probability + parse text + apply entries)
- Copilot integrated (LangGraph/OpenAI tools) via `/copilot/chat`

P1:
- Invoice narrative + anomaly highlights (AI explains based on computed comparisons)
- Better traces/logging (audit_log entries for AI suggestions & acceptance)

P2:
- Add tests (RBAC, no double invoicing, invoice totals, forecast calc sanity)
