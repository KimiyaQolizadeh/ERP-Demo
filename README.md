# ERP Project Control Copilot (Interview Demo)

AI + automation enabled project management module for an internal ERP workflow:

`Timesheets -> Approvals -> Invoicing -> Reporting -> Copilot`

This repository is optimized for demo readiness, deterministic finance calculations, and explainable AI assistance.

## Reviewer Quickstart (30 seconds)
1. Open this repo in VS Code.
2. Press `Ctrl + Shift + B` and run `Dev: Run All`.
3. Open `http://localhost:8501`.
4. Select a PM user and demo `Reports` + `Chat Assistant`.

## Table of Contents
- [1. What This Project Demonstrates](#1-what-this-project-demonstrates)
- [2. End-to-End Setup (Windows, Step by Step)](#2-end-to-end-setup-windows-step-by-step)
- [3. How to Run (VS Code Tasks, One Command, or Manual)](#3-how-to-run-vs-code-tasks-one-command-or-manual)
- [4. Verify Everything Is Running](#4-verify-everything-is-running)
- [5. Architecture Decisions](#5-architecture-decisions)
- [6. System Components and Workflow Diagrams](#6-system-components-and-workflow-diagrams)
- [7. Data Model](#7-data-model)
- [8. Automation and AI Approach](#8-automation-and-ai-approach)
- [9. ERP Rules and Guardrails Enforced](#9-erp-rules-and-guardrails-enforced)
- [10. Trade-Offs Due to Time Constraints](#10-trade-offs-due-to-time-constraints)
- [11. Testing and Validation Commands](#11-testing-and-validation-commands)
- [12. Interview Demo Script (Suggested)](#12-interview-demo-script-suggested)
- [13. Troubleshooting](#13-troubleshooting)

## 1. What This Project Demonstrates

### Functional scope
- Timesheet creation and submission workflow
- PM approvals and rejection with auditability
- Deterministic monthly draft invoicing from approved billable hours
- Portfolio and per-project reporting (budget consumption, forecast, utilization, risk)
- AI-assisted features (note rewrite, voice/text parsing, risk explanations, chat copilot)

### Tech stack
- Backend: `FastAPI`, `SQLAlchemy 2.0`, `Postgres 16`
- Frontend: `Streamlit` multipage UI
- AI/LLM: `OpenAI API`
- Agentic orchestration: `LangGraph`
- Tests: `pytest`

### Why this design is interview-friendly
- Core ERP calculations are deterministic and implemented in backend services.
- AI is constrained to suggestion and explanation use cases.
- RBAC and workflow rules are centralized in service layer checks.
- Seed data creates a complete demo story (pending approvals, invoice-ready entries, risk contrast).

## 2. End-to-End Setup (Windows, Step by Step)

This section starts from a fresh machine.

### Step 0: Install required software
Install these in order:

1. `Git`
2. `Python 3.12` (important: `run-dev.ps1` checks for `py -3.12`)
3. `Docker Desktop` (with Docker Compose)
4. `Visual Studio Code`

Optional but useful:
5. `Postman` (API testing)
6. `DBeaver` or `pgAdmin` (DB inspection)

Windows `winget` examples:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id Docker.DockerDesktop -e
winget install --id Microsoft.VisualStudioCode -e
```

### Step 1: Clone and open the repo

```powershell
git clone <your-repo-url> ERP-Demo
cd ERP-Demo
code .
```

### Step 2: Create `.env` in repo root
Create `ERP-Demo/.env` with:

```env
POSTGRES_DSN=postgresql+psycopg://erp:erp@localhost:5432/erp
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000

# Optional AI
OPENAI_API_KEY=<your_openai_key>
OPENAI_MODEL=gpt-4.1
```

Notes:
- App still runs without `OPENAI_API_KEY`; AI endpoints fall back where supported.
- Do not commit real API keys.

### Step 3: Verify prerequisites in terminal

```powershell
git --version
py -3.12 --version
docker --version
docker compose version
code --version
```

### Step 4: Start Docker Desktop
Open Docker Desktop and wait until engine status is healthy.

## 3. How to Run (VS Code Tasks, One Command, or Manual)

You have three valid run paths. Path A is best for interview demos.

### Path A (Recommended): VS Code Tasks
This repo includes `.vscode/tasks.json` with a default task: `Dev: Run All`.

#### Keyboard shortcut to run tasks file
- Press `Ctrl + Shift + B`
- VS Code will run the default build task from `tasks.json`
- If prompted, select `Dev: Run All`

What `Dev: Run All` does (via `run-dev.ps1`):
1. Checks Python `3.12`
2. Checks Docker daemon
3. Starts Postgres container (`docker compose up -d`)
4. Creates backend/frontend virtual environments if missing
5. Installs dependencies
6. Initializes DB tables
7. Seeds demo data
8. Starts backend on `http://127.0.0.1:8000`
9. Waits for `/health`
10. Starts frontend on `http://localhost:8501`

Other tasks available:
- `Dev: Run All + HTTPS`
- `Dev: HTTPS Tunnel Only`

### Path B: One command from terminal

```powershell
.\run-dev.cmd
```

Useful flags:

```powershell
.\run-dev.cmd -SkipInstall
.\run-dev.cmd -SkipSeed
.\run-dev.cmd -ForceInstall
.\run-dev.cmd -ExposeHttps
```

### Path C: Fully manual startup (exact order)

#### 1. Start DB

```powershell
docker compose up -d
```

#### 2. Backend setup and run

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m app.db.init_db
python -m app.db.seed
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

#### 3. Frontend setup and run (new terminal)

```powershell
cd frontend
py -3.12 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:BACKEND_URL='http://127.0.0.1:8000'
streamlit run streamlit_app.py
```

## 4. Verify Everything Is Running

Open:
- API docs: `http://127.0.0.1:8000/docs`
- API health: `http://127.0.0.1:8000/health`
- Frontend: `http://localhost:8501`

In UI:
1. Select a seeded user from sidebar.
2. Open `Timesheets`, `Approvals`, `Invoicing`, `Reports`, and `Chat Assistant` pages.

Expected seeded storyline:
- 10 users (PM, finance, admin, employees)
- 8 projects with mixed statuses
- 8 weeks of timesheets and entries
- Pending approvals and approved invoice-ready work
- At least one project trending higher risk

## 5. Architecture Decisions

### Decision 1: Thin routers, service-centric business logic
- Routers in `backend/app/api/routers/*` only map HTTP to service calls.
- Workflow and RBAC logic live in `backend/app/services/*`.
- Benefit: easier testing, lower coupling, clear rule ownership.

### Decision 2: Deterministic finance math in backend only
- Invoicing totals, spend, burn, forecast, and readiness are computed in Python/DB logic.
- LLM is not allowed to compute invoice totals or mutate financial status.
- Benefit: avoids hallucinated numbers and preserves auditability.

### Decision 3: Centralized RBAC and workflow checks
- `authz.py` controls role checks.
- Timesheet and invoice transitions are validated in services.
- Benefit: consistent enforcement across API and UI.

### Decision 4: Streamlit API wrapper for robust error handling
- `frontend/client/api.py` normalizes errors and handles non-JSON failures safely.
- Benefit: UI stability and clearer troubleshooting during demos.

### Decision 5: LangGraph copilot with fallback behavior
- Copilot graph includes intent routing, resolver, tool call, summarizer, memory update.
- Fallback summaries are deterministic if LLM response is invalid/ungrounded.
- Benefit: reliable demo behavior even when model responses vary.

### Decision 6: Migration-light schema management for speed
- Uses `Base.metadata.create_all()` and startup compatibility alter for specific column.
- Benefit: fast setup for take-home scope.
- Cost: not production-grade migration discipline (see trade-offs).

## 6. System Components and Workflow Diagrams

### Component diagram

```mermaid
flowchart LR
    U[User in Browser] --> S[Streamlit Frontend]
    S -->|REST + X-User-Id| A[FastAPI Backend]
    A --> SV[Service Layer
    timesheets, approvals, invoicing,
    reporting, project_health, copilot]
    SV --> DB[(PostgreSQL)]
    SV --> AI[OpenAI API]
    SV --> LG[LangGraph Orchestration]
    LG --> AI
```

### Core workflow sequence

```mermaid
sequenceDiagram
    participant E as Employee
    participant UI as Streamlit UI
    participant API as FastAPI
    participant PM as Project Manager
    participant FIN as Finance
    participant DB as Postgres

    E->>UI: Create draft timesheet + entries
    UI->>API: POST /timesheets + /entries
    API->>DB: Save DRAFT data

    E->>UI: Submit timesheet
    UI->>API: POST /timesheets/{id}/submit
    API->>DB: status DRAFT -> SUBMITTED

    PM->>UI: Review pending approvals
    UI->>API: GET /approvals/pending
    PM->>UI: Approve/reject
    UI->>API: POST /approvals/{id}/approve or reject
    API->>DB: status SUBMITTED -> APPROVED/REJECTED

    PM->>UI: Draft invoice for month
    UI->>API: POST /invoices/draft
    API->>DB: Select APPROVED + billable + uninvoiced entries
    API->>DB: Create invoice + lines, set invoiced_line_id

    FIN->>UI: Approve invoice
    UI->>API: POST /invoices/{id}/approve
    API->>DB: status DRAFT -> APPROVED
```

## 7. Data Model

### High-level entities
- `users`: user identity, role, discipline
- `projects`: project setup, commercial model, status, PM
- `rate_schedule`: billing rate by project + discipline/rate_key
- `timesheets`: period-level workflow state
- `time_entries`: day-level hours, billable flag, notes, AI suggestion fields
- `invoices`: monthly invoice header and totals
- `invoice_lines`: aggregated billed lines
- `invoice_adjustments`: manual finance adjustments
- `audit_log`: traceable events (including AI suggestions/acceptance)
- `user_preferences`: copilot memory defaults
- `vector_documents`: lightweight retrieval index (JSONB embedding)

### ER diagram (simplified)

```mermaid
erDiagram
    USERS ||--o{ PROJECTS : manages
    USERS ||--o{ TIMESHEETS : owns

    PROJECTS ||--o{ RATE_SCHEDULE : has
    PROJECTS ||--o{ TIMESHEETS : receives
    PROJECTS ||--o{ INVOICES : billed_as

    TIMESHEETS ||--o{ TIME_ENTRIES : contains

    INVOICES ||--o{ INVOICE_LINES : has
    INVOICES ||--o{ INVOICE_ADJUSTMENTS : has

    INVOICE_LINES ||--o{ TIME_ENTRIES : marks_invoiced

    USERS ||--o{ AUDIT_LOG : actor
    USERS ||--|| USER_PREFERENCES : preference

    VECTOR_DOCUMENTS }o--|| TIME_ENTRIES : source_note
```

### Key constraints implemented
- Unique invoice per project/month (`uq_invoice_project_month`)
- Unique rate key per project (`uq_rate_project_key`)
- `time_entries.invoiced_line_id` used to prevent double invoicing
- Project `NOT_AWARDED` requires reason in service validation

## 8. Automation and AI Approach

### Where AI is used
- Timesheet note rewrite (`/ai/improve-notes`)
- Voice transcription + parse into structured draft entries (`/ai/voice/*`, `/ai/parse-timesheet-text`)
- Billable suggestion with confidence (`/ai/billable/classify`, compatibility endpoints)
- Risk explanation narrative from deterministic metrics (`/projects/{id}/risk-explanation`)
- Copilot chat with tool traces (`/copilot/chat`)

### Where AI is explicitly not used
- AI does not compute invoice totals.
- AI does not approve/reject timesheets.
- AI does not set invoice approval status.
- AI does not invent project finance numbers.

### Copilot orchestration pattern
`Intent Router -> Resolver -> Tool Call -> Summarizer -> Memory Update`

Copilot tools include:
- dashboard overview
- project health
- invoice readiness
- pending approvals
- anomalies
- utilization
- draft invoice
- text retrieval

Safety/quality behaviors:
- role-scoped data access
- grounding checks for generated summaries
- deterministic fallback summary if response is ungrounded
- explicit tool trace returned to UI

## 9. ERP Rules and Guardrails Enforced

### Timesheet workflow
- Valid path: `DRAFT -> SUBMITTED -> APPROVED/REJECTED`
- Only owner (employee) can edit `DRAFT`
- Only assigned PM can approve/reject `SUBMITTED`

### Invoicing
- Only `APPROVED` timesheet entries
- Only `billable = true` entries
- Only entries with `invoiced_line_id IS NULL`
- Only projects with status `AWARDED` or `COMPLETED`

### Reporting
- Spend and totals are deterministic
- Forecast and risk inputs are deterministic backend outputs
- AI only explains already computed metrics

## 10. Trade-Offs Due to Time Constraints

1. Lightweight schema migration strategy
- Trade-off: used `create_all()` + compatibility `ALTER TABLE` instead of Alembic migration history.
- Impact: faster setup, weaker production migration governance.
- Follow-up: add Alembic revision pipeline and CI migration checks.

2. Header-based auth for demo speed (`X-User-Id`)
- Trade-off: no OAuth/JWT identity provider.
- Impact: very fast demo onboarding, not production-secure auth model.
- Follow-up: add JWT auth and role claims.

3. Streamlit for rapid UI delivery
- Trade-off: chose delivery speed and explainability over highly customized SPA behavior.
- Impact: strong demo velocity, less granular frontend architecture than React + component tests.
- Follow-up: migrate to React/Next.js if productized.

4. AI retrieval storage without pgvector dependency
- Trade-off: embeddings are stored in JSONB for portability.
- Impact: easier setup, less scalable similarity search versus vector indexes.
- Follow-up: add pgvector + ANN indexing.

5. Focused test coverage for critical rules
- Trade-off: core business rule tests exist, full API/integration/UI test suite is limited.
- Impact: confidence in key invariants, but not exhaustive regression coverage.
- Follow-up: expand tests for RBAC matrix, reporting edge cases, and copilot tool routing.

## 11. Testing and Validation Commands

Run from repo root unless noted.

### Backend import check

```powershell
cd backend
.\.venv\Scripts\python -c "import app.main"
```

### DB init and seed

```powershell
cd backend
.\.venv\Scripts\python -m app.db.init_db
.\.venv\Scripts\python -m app.db.seed
```

### Optional smoke checks

```powershell
cd backend
.\.venv\Scripts\python -m app.db.smoke_ai_status
.\.venv\Scripts\python -m app.db.smoke_pending_approvals
```


## 13. Troubleshooting

### Docker issues
- Symptom: DB connection errors.
- Check:
  - Docker Desktop is running
  - `docker compose ps`
  - port `5432` is free

### Backend startup fails
- Check Python version: `py -3.12 --version`
- Reinstall deps:

```powershell
cd backend
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### Frontend cannot reach backend
- Ensure backend is running on `127.0.0.1:8000`
- In frontend terminal set:

```powershell
$env:BACKEND_URL='http://127.0.0.1:8000'
```

### AI not responding
- Verify key in `.env`: `OPENAI_API_KEY`
- Probe status endpoint: `GET /ai/status?probe=true`
- App remains usable with deterministic fallbacks for many AI flows.
