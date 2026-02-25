import os
from collections import Counter
from datetime import date, timedelta
from html import escape

import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return date.today()


def _parse_iso_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _money(amount) -> str:
    try:
        return f"${float(amount):,.0f}"
    except Exception:
        return "$0"


def _avg_budget_hint(percent: float) -> str:
    if percent < 70:
        return "Healthy range"
    if percent < 90:
        return "Watch range"
    return "At-risk range"


def _open_project_page(path: str, project: dict) -> None:
    st.session_state["context_project_id"] = project["id"]
    st.session_state["context_project_label"] = (
        f"{project.get('project_name', 'Project')} ({project.get('status', '')})"
    )
    try:
        st.switch_page(path)
    except Exception:
        st.caption(f"Open `{path}` from the sidebar.")


def _inject_projects_ui_css() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/icon?family=Material+Icons');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons+Outlined');
.pc-projects-header-anchor { display: none; }
div[data-testid="stVerticalBlock"]:has(.pc-projects-header-anchor) {
  position: sticky;
  top: 0;
  z-index: 44;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--pc-border);
  margin: 0 -1.05rem 0.9rem;
  padding: 0.12rem 1.05rem 0.52rem;
}
.pc-projects-header-left {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.pc-projects-kicker-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.pc-projects-kicker {
  color: #1d4ed8;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.pc-projects-beta {
  background: #dbeafe;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
  border-radius: 999px;
  padding: 0.1rem 0.48rem;
  font-size: 0.66rem;
  font-weight: 800;
}
.pc-projects-title-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}
.pc-projects-title {
  margin: 0;
  color: #0f172a;
  font-size: 2.05rem;
  font-weight: 800;
  line-height: 1;
}
.pc-projects-badge {
  border-radius: 999px;
  border: 1px solid #d0d7e2;
  background: #eef2f7;
  color: #6b7280;
  font-size: 0.76rem;
  font-weight: 700;
  padding: 0.15rem 0.54rem;
}
.pc-projects-header-search [data-testid="stTextInput"] {
  margin-top: 0.04rem;
  position: relative;
}
.pc-projects-header-search [data-testid="stTextInput"]::before {
  content: "search";
  font-family: "Material Icons Outlined";
  position: absolute;
  left: 0.72rem;
  top: 50%;
  transform: translateY(-50%);
  color: #94a3b8;
  font-size: 1.18rem;
  z-index: 2;
  pointer-events: none;
}
.pc-projects-header-search [data-testid="stTextInput"] input {
  height: 2.55rem;
  border-radius: 10px;
  background: #f8fafc !important;
  border: 1px solid #d7dee8 !important;
  padding-left: 2.4rem !important;
  font-size: 1.02rem;
}
.pc-projects-header-cta [data-testid="stButton"] button {
  margin-top: 0.05rem;
  height: 2.55rem;
  border-radius: 10px;
  background: #2563eb;
  border: 1px solid #1d4ed8;
  color: #ffffff;
  font-size: 1.03rem;
  font-weight: 700;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.2);
}
.pc-projects-header-cta [data-testid="stButton"] button:hover {
  background: #1d4ed8;
  border-color: #1e40af;
}
.pc-projects-toolbar-gap { height: 1.62rem; }
.pc-phase-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 0.8rem;
  margin: 0.35rem 0 1rem;
}
.pc-phase-card {
  position: relative;
  background: var(--pc-surface);
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  padding: 0.9rem 1rem 1.05rem;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
  overflow: hidden;
}
.pc-phase-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pc-phase-title {
  color: #476181;
  font-size: 0.86rem;
  font-weight: 700;
}
.pc-phase-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.15rem;
}
.pc-phase-icon .material-icons-outlined {
  font-size: 1.45rem;
  line-height: 1;
}
.pc-phase-value {
  margin-top: 0.35rem;
  color: #0b2240;
  font-size: 2.15rem;
  font-weight: 900;
  line-height: 1;
}
.pc-phase-foot {
  margin-top: 0.42rem;
  font-size: 0.82rem;
  color: #7488a4;
  font-weight: 600;
}
.pc-phase-accent {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 4px;
}
.pc-variant-projects .pc-phase-icon { background: #e9f1ff; color: #245dd8; }
.pc-variant-projects .pc-phase-accent { background: #2a6be8; }
.pc-variant-projects .pc-phase-foot { color: #3e6bb7; }

.pc-variant-proposal .pc-phase-icon { background: #f3e9ff; color: #7c3aed; }
.pc-variant-proposal .pc-phase-accent { background: #8b5cf6; }
.pc-variant-proposal .pc-phase-foot { color: #7c4ec2; }

.pc-variant-awarded .pc-phase-icon { background: #e7fbef; color: #0e9f6e; }
.pc-variant-awarded .pc-phase-accent { background: #12b981; }
.pc-variant-awarded .pc-phase-foot { color: #0f9a61; }

.pc-variant-not-awarded .pc-phase-icon { background: #ffe9ee; color: #e11d48; }
.pc-variant-not-awarded .pc-phase-accent { background: #f43f5e; }
.pc-variant-not-awarded .pc-phase-foot { color: #be123c; }

.pc-variant-avg-budget .pc-phase-icon { background: #fff3e6; color: #ea580c; }
.pc-variant-avg-budget .pc-phase-accent { background: #f97316; }
.pc-variant-avg-budget .pc-phase-foot { color: #c45b15; }

.pc-registry-card {
  background: #ffffff;
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
  overflow: hidden;
}
.pc-registry-shell-anchor { display: none; }
div[data-testid="stVerticalBlock"]:has(.pc-registry-shell-anchor) {
  background: #ffffff;
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
  overflow: hidden;
  padding-bottom: 0.16rem;
}
.pc-registry-head {
  padding: 1rem 1.2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--pc-border);
}
.pc-registry-head-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  color: #0f172a;
}
.pc-registry-head-sub {
  margin-top: 0.2rem;
  font-size: 0.86rem;
  color: #64748b;
}
.pc-registry-headrow-anchor,
.pc-registry-row-anchor,
.pc-registry-footer-anchor { display: none; }
div[data-testid="stVerticalBlock"]:has(.pc-registry-headrow-anchor) {
  background: #f8fafc;
  border-bottom: 1px solid var(--pc-border);
  padding: 1.5rem 0.95rem;
}
div[data-testid="stVerticalBlock"]:has(.pc-registry-row-anchor) {
  border-bottom: 1px solid var(--pc-border);
  padding: 1.5rem 0.95rem;
}
div[data-testid="stVerticalBlock"]:has(.pc-registry-footer-anchor) {
  background: #f8fafc;
  padding: 0.5rem 0.95rem 0.18rem;
  gap: 0.25rem;
}
div[data-testid="stElementContainer"]:has(.pc-registry-headrow-anchor),
div[data-testid="stElementContainer"]:has(.pc-registry-row-anchor),
div[data-testid="stElementContainer"]:has(.pc-registry-footer-anchor) { display: none; }
.pc-col-head {
  font-size: 0.72rem;
  text-transform: uppercase;
  line-height: 1;
  letter-spacing: 0.08em;
  color: #64748b;
  font-weight: 700;
}
.pc-col-head-center { text-align: center; }
.pc-col-head-right { text-align: right; }
.pc-registry-scroll { overflow-x: auto; }
.pc-registry-table {
  width: 100%;
  min-width: 1020px;
  border-collapse: collapse;
}
.pc-registry-table thead tr {
  background: #f8fafc;
  border-bottom: 1px solid var(--pc-border);
}
.pc-registry-table th {
  padding: 0.78rem 1rem;
  text-align: left;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #64748b;
  font-weight: 700;
}
.pc-registry-table th.pc-th-center,
.pc-registry-table td.pc-td-center { text-align: center; }
.pc-registry-table th.pc-th-right,
.pc-registry-table td.pc-td-right { text-align: right; }
.pc-registry-table tbody tr {
  border-bottom: 1px solid var(--pc-border);
  transition: background-color 0.15s ease;
}
.pc-registry-table tbody tr:hover { background: #f8fafc; }
.pc-registry-table td {
  padding: 0.9rem 1rem;
  vertical-align: middle;
}
.pc-proj-name {
  font-size: 0.95rem;
  font-weight: 800;
  color: #0f172a;
}
.pc-registry-table tbody tr:hover .pc-proj-name { color: #2563eb; }
.pc-proj-meta {
  margin-top: 0.22rem;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: #64748b;
  font-size: 0.77rem;
}
.pc-proj-meta-dot {
  width: 4px;
  height: 4px;
  border-radius: 999px;
  background: #cbd5e1;
}
.pc-client-cell,
.pc-contract-cell {
  font-size: 0.9rem;
  color: #475569;
}
.pc-money-cell {
  font-size: 0.98rem;
  font-weight: 700;
  color: #0f172a;
}
.pc-mini-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 8px;
  border: 1px solid transparent;
  padding: 0.15rem 0.45rem;
  font-size: 0.71rem;
  font-weight: 700;
}
.pc-div-purple { background: #f3e8ff; color: #7e22ce; border-color: #e9d5ff; }
.pc-div-blue { background: #dbeafe; color: #1d4ed8; border-color: #bfdbfe; }
.pc-div-amber { background: #fef3c7; color: #92400e; border-color: #fde68a; }
.pc-div-slate { background: #e2e8f0; color: #475569; border-color: #cbd5e1; }

.pc-status-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.2rem 0.55rem;
  font-size: 0.73rem;
  font-weight: 700;
}
.pc-status-awarded { background: #dcfce7; color: #166534; }
.pc-status-proposal { background: #dbeafe; color: #1d4ed8; }
.pc-status-completed { background: #ecfeff; color: #0f766e; }
.pc-status-cancelled { background: #fee2e2; color: #991b1b; }
.pc-status-not-awarded { background: #e2e8f0; color: #334155; }
.pc-status-default { background: #e2e8f0; color: #334155; }

.pc-progress-cell { min-width: 135px; }
.pc-progress-top {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.22rem;
}
.pc-progress-text {
  font-size: 0.76rem;
  font-weight: 700;
  color: #2563eb;
}
.pc-progress-text-muted {
  font-size: 0.76rem;
  font-weight: 700;
  color: #94a3b8;
}
.pc-progress-track {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}
.pc-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: #2563eb;
}
.pc-progress-fill-warn { background: #f59e0b; }
.pc-progress-fill-danger { background: #ef4444; }
.pc-progress-fill-muted { background: #94a3b8; opacity: 0.35; }
.pc-progress-sub {
  margin-top: 0.2rem;
  color: #94a3b8;
  font-size: 0.68rem;
  font-weight: 600;
}

.pc-actions {
  display: inline-flex;
  gap: 0.45rem;
}
.pc-action-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #dbe2ec;
  border-radius: 8px;
  color: #94a3b8;
  background: #ffffff;
  text-decoration: none;
}
.pc-action-btn:hover {
  color: #2563eb;
  border-color: #93c5fd;
  background: #eff6ff;
}
.pc-action-btn .material-icons {
  font-size: 0.96rem;
  line-height: 1;
}

.pc-registry-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
  border-top: 1px solid var(--pc-border);
  background: #f8fafc;
  padding: 0.62rem 1rem;
}
.pc-registry-count {
  font-size: 0.73rem;
  color: #64748b;
}
.pc-registry-pages {
  display: inline-flex;
  gap: 0.3rem;
  align-items: center;
}
.pc-page-link {
  padding: 0.18rem 0.46rem;
  border: 1px solid #dbe2ec;
  border-radius: 7px;
  font-size: 0.72rem;
  color: #64748b;
  text-decoration: none;
  background: #ffffff;
}
.pc-page-link:hover {
  border-color: #93c5fd;
  color: #2563eb;
}
.pc-page-link-active {
  border-color: #2563eb;
  background: #2563eb;
  color: #ffffff;
}
.pc-registry-empty {
  text-align: center;
  color: #64748b;
  font-size: 0.86rem;
  padding: 1rem 0.8rem;
}
@media (max-width: 900px) {
  div[data-testid="stVerticalBlock"]:has(.pc-projects-header-anchor) {
    margin-left: -0.55rem;
    margin-right: -0.55rem;
    padding-left: 0.55rem;
    padding-right: 0.55rem;
  }
  .pc-projects-title {
    font-size: 1.72rem;
  }
}
@media (max-width: 780px) {
  .pc-projects-header-search {
    display: none;
  }
  .pc-registry-footer {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
""",
        unsafe_allow_html=True,
    )


def _phase_card_html(label: str, value: str, foot: str, variant: str, icon: str) -> str:
    safe_variant = (
        variant
        if variant in {"projects", "proposal", "awarded", "not-awarded", "avg-budget"}
        else "projects"
    )
    return (
        f"<div class='pc-phase-card pc-variant-{safe_variant}'>"
        f"<div class='pc-phase-top'><div class='pc-phase-title'>{escape(label)}</div><div class='pc-phase-icon'><span class='material-icons-outlined'>{escape(icon)}</span></div></div>"
        f"<div class='pc-phase-value'>{escape(value)}</div>"
        f"<div class='pc-phase-foot'>{escape(foot)}</div>"
        "<div class='pc-phase-accent'></div>"
        "</div>"
    )


def _render_phase_cards(month_ctx: date, filtered_projects: list[dict]) -> None:
    status_counts = Counter(
        [str(p.get("status", "")).upper() for p in filtered_projects]
    )
    avg_consumed = (
        sum(float(p.get("_consumed_pct", 0.0)) for p in filtered_projects)
        / len(filtered_projects)
        if filtered_projects
        else 0.0
    )
    cards = [
        _phase_card_html(
            "Projects",
            str(len(filtered_projects)),
            "Setup records active",
            "projects",
            "folder",
        ),
        _phase_card_html(
            "Proposal",
            str(status_counts.get("PROPOSAL", 0)),
            "Pipeline opportunities",
            "proposal",
            "description",
        ),
        _phase_card_html(
            "Awarded",
            str(status_counts.get("AWARDED", 0)),
            "Invoice-eligible",
            "awarded",
            "verified",
        ),
        _phase_card_html(
            "Not Awarded",
            str(status_counts.get("NOT_AWARDED", 0)),
            "Reason in details",
            "not-awarded",
            "report",
        ),
        _phase_card_html(
            "Avg Budget Used",
            f"{avg_consumed:.1f}%",
            f"{_avg_budget_hint(avg_consumed)} • Metrics as of {month_ctx}",
            "avg-budget",
            "pie_chart",
        ),
    ]
    st.markdown(
        f"<div class='pc-phase-grid'>{''.join(cards)}</div>", unsafe_allow_html=True
    )


def _division_chip_class(division: str) -> str:
    division_key = str(division or "").strip().upper()
    if division_key in {"SD", "SERVICE", "STRUCTURAL"}:
        return "pc-div-purple"
    if division_key in {"ICI", "INDUSTRIAL", "ELECTRICAL"}:
        return "pc-div-blue"
    if division_key in {"GV", "CIVIL", "INFRA"}:
        return "pc-div-amber"
    return "pc-div-slate"


def _status_chip_class(status: str) -> str:
    status_key = str(status or "").upper()
    mapping = {
        "AWARDED": "pc-status-awarded",
        "PROPOSAL": "pc-status-proposal",
        "COMPLETED": "pc-status-completed",
        "CANCELLED": "pc-status-cancelled",
        "NOT_AWARDED": "pc-status-not-awarded",
    }
    return mapping.get(status_key, "pc-status-default")


def _progress_fill_class(status: str, pct: float) -> str:
    status_key = str(status or "").upper()
    if status_key in {"NOT_AWARDED", "CANCELLED"}:
        return "pc-progress-fill-muted"
    if pct >= 90:
        return "pc-progress-fill-danger"
    if pct >= 75:
        return "pc-progress-fill-warn"
    return "pc-progress-fill"


apply_theme()
_inject_projects_ui_css()

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

default_month = _as_date(st.session_state.get("context_month"))
today = date.today()
default_range_from = today - timedelta(days=365)
default_range_to = today + timedelta(days=365)
if "projects_date_from" not in st.session_state:
    st.session_state["projects_date_from"] = default_range_from
if "projects_date_to" not in st.session_state:
    st.session_state["projects_date_to"] = default_range_to
if "projects_filter_visible" not in st.session_state:
    st.session_state["projects_filter_visible"] = False
if "projects_filter_status" not in st.session_state:
    st.session_state["projects_filter_status"] = []
if "projects_filter_division" not in st.session_state:
    st.session_state["projects_filter_division"] = []
if "projects_filter_contract" not in st.session_state:
    st.session_state["projects_filter_contract"] = []

with st.container():
    st.markdown("<div class='pc-projects-header-anchor'></div>", unsafe_allow_html=True)
    head_left, head_search, head_cta = st.columns([1.55, 1.1, 0.65])
    with head_left:
        st.markdown(
            """
<div class="pc-projects-header-left">
  <div class="pc-projects-kicker-row">
    <span class="pc-projects-kicker">Project Control Copilot</span>
    <span class="pc-projects-beta">BETA</span>
  </div>
  <div class="pc-projects-title-row">
    <h1 class="pc-projects-title">Projects</h1>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    with head_search:
        st.markdown("<div class='pc-projects-header-search'>", unsafe_allow_html=True)
        search_query = st.text_input(
            "Search projects",
            value=st.session_state.get("projects_search_query", ""),
            key="projects_search_query",
            placeholder="Search projects...",
            label_visibility="collapsed",
        ).strip()
        st.markdown("</div>", unsafe_allow_html=True)
    with head_cta:
        st.markdown("<div class='pc-projects-header-cta'>", unsafe_allow_html=True)
        if st.button("+  Create Project", use_container_width=True):
            try:
                st.switch_page("pages/7_Project_Create.py")
            except Exception:
                st.caption("Open `pages/7_Project_Create.py` from the sidebar.")
        st.markdown("</div>", unsafe_allow_html=True)

row_left, row_mid, row_filter = st.columns([1.2, 2.1, 0.8])
with row_left:
    selected_range = st.date_input(
        "Project date range",
        value=(
            _as_date(st.session_state.get("projects_date_from")),
            _as_date(st.session_state.get("projects_date_to")),
        ),
        key="projects_date_range",
    )
    if isinstance(selected_range, (tuple, list)):
        range_from = _as_date(selected_range[0]) if selected_range else default_month
        range_to = (
            _as_date(selected_range[1]) if len(selected_range) > 1 else range_from
        )
    else:
        range_from = _as_date(selected_range)
        range_to = range_from
    if range_from > range_to:
        range_from, range_to = range_to, range_from

    st.session_state["projects_date_from"] = range_from
    st.session_state["projects_date_to"] = range_to
    month_ctx = range_to
    st.session_state["context_month"] = month_ctx
with row_mid:
    st.empty()
with row_filter:
    st.markdown("<div class='pc-projects-toolbar-gap'></div>", unsafe_allow_html=True)
    if st.button("≡ Filter", use_container_width=True):
        st.session_state["projects_filter_visible"] = not st.session_state[
            "projects_filter_visible"
        ]

try:
    projects = api.list_projects()
    users = api.list_users()
except APIError as e:
    st.error(str(e))
    st.stop()

dashboard_map: dict[str, dict] = {}
try:
    dash = api.dashboard(str(month_ctx))
    dashboard_map = {row.get("project_id"): row for row in dash.get("projects", [])}
except APIError as e:
    st.caption(f"Budget progress metrics unavailable for month context: {e}")

pm_name_by_id = {u["id"]: u["name"] for u in users}

enriched_projects_all = []
for project in projects:
    project_metrics = dashboard_map.get(str(project["id"]), {})
    consumed_pct = float(project_metrics.get("percent_budget_consumed", 0.0))
    enriched_projects_all.append(
        {
            **project,
            "_consumed_pct": consumed_pct,
            "_remaining_budget": float(
                project_metrics.get(
                    "remaining_budget", project.get("approved_budget", 0.0)
                )
            ),
        }
    )

if st.session_state["projects_filter_visible"]:
    f1, f2, f3 = st.columns(3)
    with f1:
        st.session_state["projects_filter_status"] = st.multiselect(
            "Status",
            ["PROPOSAL", "AWARDED", "COMPLETED", "CANCELLED", "NOT_AWARDED"],
            default=st.session_state["projects_filter_status"],
            key="projects_filter_status_widget",
        )
    with f2:
        divisions = sorted(
            {str(p.get("division", "")) for p in projects if p.get("division")}
        )
        st.session_state["projects_filter_division"] = st.multiselect(
            "Division",
            divisions,
            default=st.session_state["projects_filter_division"],
            key="projects_filter_division_widget",
        )
    with f3:
        contracts = sorted(
            {
                str(p.get("contract_type", ""))
                for p in projects
                if p.get("contract_type")
            }
        )
        st.session_state["projects_filter_contract"] = st.multiselect(
            "Contract Type",
            contracts,
            default=st.session_state["projects_filter_contract"],
            key="projects_filter_contract_widget",
        )

date_filter_from = _as_date(st.session_state.get("projects_date_from"))
date_filter_to = _as_date(st.session_state.get("projects_date_to"))


def _matches_filters(project: dict) -> bool:
    query = str(search_query or "").lower()
    haystack = " ".join(
        [
            str(project.get("project_name", "")),
            str(project.get("client_name", "")),
            str(project.get("division", "")),
            str(project.get("discipline", "")),
            str(project.get("status", "")),
        ]
    ).lower()
    if query and query not in haystack:
        return False
    selected_status = st.session_state.get("projects_filter_status", [])
    if selected_status and str(project.get("status", "")).upper() not in set(
        selected_status
    ):
        return False
    selected_divisions = st.session_state.get("projects_filter_division", [])
    if selected_divisions and str(project.get("division", "")) not in set(
        selected_divisions
    ):
        return False
    selected_contracts = st.session_state.get("projects_filter_contract", [])
    if selected_contracts and str(project.get("contract_type", "")) not in set(
        selected_contracts
    ):
        return False
    project_start = _parse_iso_date(project.get("start_date"))
    project_end = _parse_iso_date(project.get("end_date"))
    if not project_start or not project_end:
        return False
    if project_start > project_end:
        project_start, project_end = project_end, project_start
    if project_start < date_filter_from or project_end > date_filter_to:
        return False
    return True


filtered_projects = [p for p in enriched_projects_all if _matches_filters(p)]
_render_phase_cards(month_ctx, filtered_projects)

if not filtered_projects:
    if projects:
        st.info("No projects match current search/filter.")
    else:
        st.info("No projects yet. Use Create New Project.")
    st.stop()

projects_by_id = {str(p.get("id")): p for p in filtered_projects}
sorted_projects = sorted(
    filtered_projects, key=lambda x: str(x.get("project_name", "")).lower()
)
total_projects = len(sorted_projects)
if "projects_table_page" not in st.session_state:
    st.session_state["projects_table_page"] = 1
current_page = int(st.session_state.get("projects_table_page", 1))
page_size = 6
page_count = max(1, (total_projects + page_size - 1) // page_size)
current_page = max(1, min(current_page, page_count))
st.session_state["projects_table_page"] = current_page
start_idx = (current_page - 1) * page_size
end_idx = min(start_idx + page_size, total_projects)
visible_projects = sorted_projects[start_idx:end_idx]

with st.container():
    st.markdown("<div class='pc-registry-shell-anchor'></div>", unsafe_allow_html=True)
    st.markdown(
        """
<div class="pc-registry-head">
  <div>
    <h3 class="pc-registry-head-title">Project Registry</h3>
    <div class="pc-registry-head-sub">Clean table with progress cue and quick actions.</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown(
            "<div class='pc-registry-headrow-anchor'></div>", unsafe_allow_html=True
        )
        hdr = st.columns(
            [2.2, 1.75, 0.85, 1.1, 1.0, 1.05, 1.5, 1.0], vertical_alignment="center"
        )
        with hdr[0]:
            st.markdown(
                "<div class='pc-col-head'>Project</div>", unsafe_allow_html=True
            )
        with hdr[1]:
            st.markdown("<div class='pc-col-head'>Client</div>", unsafe_allow_html=True)
        with hdr[2]:
            st.markdown(
                "<div class='pc-col-head pc-col-head-center'>Division</div>",
                unsafe_allow_html=True,
            )
        with hdr[3]:
            st.markdown(
                "<div class='pc-col-head'>Contract</div>", unsafe_allow_html=True
            )
        with hdr[4]:
            st.markdown(
                "<div class='pc-col-head pc-col-head-right'>Budget</div>",
                unsafe_allow_html=True,
            )
        with hdr[5]:
            st.markdown(
                "<div class='pc-col-head pc-col-head-center'>Status</div>",
                unsafe_allow_html=True,
            )
        with hdr[6]:
            st.markdown(
                "<div class='pc-col-head'>Progress</div>", unsafe_allow_html=True
            )
        with hdr[7]:
            st.markdown(
                "<div class='pc-col-head pc-col-head-center'>Actions</div>",
                unsafe_allow_html=True,
            )

    for project in visible_projects:
        status = str(project.get("status", "")).upper()
        progress_pct = max(0.0, min(100.0, float(project.get("_consumed_pct", 0.0))))
        budget = float(project.get("approved_budget", 0.0) or 0.0)
        used = budget * (progress_pct / 100.0)
        is_na = status in {"NOT_AWARDED", "CANCELLED"}
        progress_value = "--" if is_na else f"{progress_pct:.1f}%"
        progress_label_class = "pc-progress-text-muted" if is_na else "pc-progress-text"
        progress_width = 0.0 if is_na else progress_pct
        progress_note = "N/A" if is_na else "Used of Budget"
        progress_title = "N/A" if is_na else f"{_money(used)} / {_money(budget)}"
        division = str(project.get("division", "") or "-")
        status_label = status.replace("_", " ").title()
        contract = str(project.get("contract_type", "")).replace("_", " ").title()
        pm_name = pm_name_by_id.get(project.get("pm_user_id"), "Unassigned")

        with st.container():
            st.markdown(
                "<div class='pc-registry-row-anchor'></div>", unsafe_allow_html=True
            )
            row = st.columns(
                [2.2, 1.75, 0.85, 1.1, 1.0, 1.05, 1.5, 1.0], vertical_alignment="center"
            )
            with row[0]:
                st.markdown(
                    f"""
<div class='pc-proj-name'>{escape(str(project.get('project_name', '-')))}</div>
<div class='pc-proj-meta'>
  <span>{escape(str(project.get('discipline', '-') or '-'))}</span>
  <span class='pc-proj-meta-dot'></span>
  <span>PM: {escape(pm_name)}</span>
</div>
""",
                    unsafe_allow_html=True,
                )
            with row[1]:
                st.markdown(
                    f"<div class='pc-client-cell'>{escape(str(project.get('client_name', '-') or '-'))}</div>",
                    unsafe_allow_html=True,
                )
            with row[2]:
                st.markdown(
                    f"<div style='text-align:center;'><span class='pc-mini-chip {_division_chip_class(division)}'>{escape(division)}</span></div>",
                    unsafe_allow_html=True,
                )
            with row[3]:
                st.markdown(
                    f"<div class='pc-contract-cell'>{escape(contract or '-')}</div>",
                    unsafe_allow_html=True,
                )
            with row[4]:
                st.markdown(
                    f"<div class='pc-money-cell' style='text-align:right;'>{escape(_money(budget))}</div>",
                    unsafe_allow_html=True,
                )
            with row[5]:
                st.markdown(
                    f"<div style='text-align:center;'><span class='pc-status-chip {_status_chip_class(status)}'>{escape(status_label)}</span></div>",
                    unsafe_allow_html=True,
                )
            with row[6]:
                st.markdown(
                    f"""
<div class='pc-progress-cell'>
  <div class='pc-progress-top'><span class='{progress_label_class}'>{escape(progress_value)}</span></div>
  <div class='pc-progress-track' title='{escape(progress_title)}'>
    <div class='pc-progress-fill {_progress_fill_class(status, progress_pct)}' style='width:{progress_width:.1f}%;'></div>
  </div>
  <div class='pc-progress-sub'>{escape(progress_note)}</div>
</div>
""",
                    unsafe_allow_html=True,
                )
            with row[7]:
                b1, b2 = st.columns(2, gap="small")
                with b1:
                    if st.button(
                        "✎",
                        key=f"project_edit_{project['id']}",
                        help="Edit project",
                        use_container_width=True,
                    ):
                        _open_project_page(
                            "pages/8_Project_Edit.py",
                            projects_by_id[str(project["id"])],
                        )
                with b2:
                    if st.button(
                        "👁",
                        key=f"project_detail_{project['id']}",
                        help="Project details",
                        use_container_width=True,
                    ):
                        _open_project_page(
                            "pages/9_Project_Details.py",
                            projects_by_id[str(project["id"])],
                        )

    with st.container():
        st.markdown(
            "<div class='pc-registry-footer-anchor'></div>", unsafe_allow_html=True
        )
        count_col, nav_col = st.columns([3.0, 2.2], vertical_alignment="center")
        with count_col:
            st.markdown(
                f"<div class='pc-registry-count'>Showing {start_idx + 1} to {end_idx} of {total_projects} results</div>",
                unsafe_allow_html=True,
            )
        with nav_col:
            page_targets = sorted(
                {1, page_count, current_page - 1, current_page, current_page + 1}
            )
            page_targets = [p for p in page_targets if 1 <= p <= page_count]
            button_specs = [
                ("Prev", "pc_prev_page", max(1, current_page - 1), current_page <= 1)
            ]
            button_specs += [
                (str(p), f"pc_page_{p}", p, p == current_page) for p in page_targets
            ]
            button_specs += [
                (
                    "Next",
                    "pc_next_page",
                    min(page_count, current_page + 1),
                    current_page >= page_count,
                )
            ]
            nav_buttons = st.columns(len(button_specs), gap="small")
            for idx, (label, key, target_page, disabled) in enumerate(button_specs):
                with nav_buttons[idx]:
                    if st.button(
                        label, disabled=disabled, use_container_width=True, key=key
                    ):
                        st.session_state["projects_table_page"] = target_page
                        st.rerun()
