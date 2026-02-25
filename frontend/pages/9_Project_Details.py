import os
from datetime import date

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, chip, kpi_strip, section

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


def _money(value) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


def _status_tone(status: str) -> str:
    tone_map = {
        "PROPOSAL": "primary",
        "AWARDED": "success",
        "COMPLETED": "neutral",
        "CANCELLED": "danger",
        "NOT_AWARDED": "warn",
    }
    return tone_map.get(str(status or "").upper(), "neutral")


apply_theme(
    "Project Details",
    "Detailed project view including not-awarded reason and rate schedule.",
    badge="Projects",
)

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

try:
    projects = api.list_projects()
except APIError as e:
    st.error(str(e))
    st.stop()

if not projects:
    st.info("No projects found.")
    st.stop()

project_map = {f"{p['project_name']} ({p['status']})": p for p in projects}
project_labels = list(project_map.keys())
project_ids = [p["id"] for p in projects]
default_project_id = st.session_state.get("context_project_id")
default_index = project_ids.index(default_project_id) if default_project_id in project_ids else 0

nav_left, nav_mid, nav_right = st.columns([1, 1, 1.2])
with nav_left:
    if st.button("Back to Projects", use_container_width=True):
        try:
            st.switch_page("pages/0_Projects.py")
        except Exception:
            st.caption("Open `pages/0_Projects.py` from the sidebar.")
with nav_mid:
    if st.button("Edit Project", use_container_width=True):
        try:
            st.switch_page("pages/8_Project_Edit.py")
        except Exception:
            st.caption("Open `pages/8_Project_Edit.py` from the sidebar.")
with nav_right:
    selected_label = st.selectbox("Project", project_labels, index=default_index, key="project_detail_pick")

selected_project = project_map[selected_label]
project_id = selected_project["id"]
st.session_state["context_project_id"] = project_id
st.session_state["context_project_label"] = selected_label

try:
    detail = api.get_project(project_id)
except APIError as e:
    st.error(str(e))
    st.stop()

default_month = _as_date(st.session_state.get("context_month"))
month_ctx = st.date_input("Month context", value=default_month, key="project_detail_month")
st.session_state["context_month"] = month_ctx

consumed_pct = 0.0
remaining_budget = float(detail.get("approved_budget", 0.0))
try:
    dash = api.dashboard(str(month_ctx))
    match = next((p for p in dash.get("projects", []) if p.get("project_id") == detail.get("id")), None)
    if match:
        consumed_pct = float(match.get("percent_budget_consumed", 0.0))
        remaining_budget = float(match.get("remaining_budget", remaining_budget))
except APIError:
    pass

kpi_strip(
    [
        {"label": "Project", "value": detail.get("project_name", "-"), "foot": detail.get("client_name", "-"), "tone": "neutral"},
        {"label": "Status", "value": str(detail.get("status", "")).replace("_", " ").title(), "foot": "Lifecycle state", "tone": _status_tone(detail.get("status", ""))},
        {"label": "Approved Budget", "value": _money(detail.get("approved_budget", 0.0)), "foot": "Commercial baseline", "tone": "primary"},
        {"label": "Budget Used", "value": f"{consumed_pct:.1f}%", "foot": f"Remaining {_money(remaining_budget)}", "tone": "warn" if consumed_pct >= 70 else "success"},
    ]
)

section("Project Profile")
left, right = st.columns(2)
with left:
    st.markdown(f"**Project Name:** {detail.get('project_name', '-')}")
    st.markdown(f"**Client:** {detail.get('client_name', '-')}")
    st.markdown(f"**Division:** {detail.get('division', '-')}")
    st.markdown(f"**Discipline:** {detail.get('discipline', '-')}")
    st.markdown(f"**Project Manager ID:** {detail.get('pm_user_id', '-')}")
with right:
    st.markdown(f"**Contract Type:** {str(detail.get('contract_type', '')).replace('_', ' ').title()}")
    st.markdown(f"**Start Date:** {detail.get('start_date', '-')}")
    st.markdown(f"**End Date:** {detail.get('end_date', '-')}")
    st.markdown(f"**Project ID:** {detail.get('id', '-')}")
    st.markdown(
        f"**Status:** {chip(str(detail.get('status', '')).replace('_', ' ').title(), _status_tone(detail.get('status', '')))}",
        unsafe_allow_html=True,
    )

section("Not Awarded Reason")
if str(detail.get("status", "")).upper() == "NOT_AWARDED":
    st.warning(detail.get("not_awarded_reason", "No reason provided"))
else:
    st.caption("Reason is only captured when status is Not Awarded.")

section("Rate Schedule")
rates_df = pd.DataFrame(detail.get("rates", []))
if rates_df.empty:
    st.info("No rates configured.")
else:
    rates_df = rates_df[["rate_key", "rate"]].rename(columns={"rate_key": "Role/Discipline", "rate": "Rate"})
    rates_df["Rate"] = rates_df["Rate"].map(lambda v: _money(v))
    st.dataframe(rates_df, use_container_width=True, hide_index=True)
