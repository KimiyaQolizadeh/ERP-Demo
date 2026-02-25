import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, chip, kpi_strip, section

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


def _status_tone(status: str) -> str:
    mapping = {
        "DRAFT": "warn",
        "SUBMITTED": "primary",
        "APPROVED": "success",
        "REJECTED": "danger",
    }
    return mapping.get(str(status or "").upper(), "neutral")


apply_theme(
    "Timesheet Details",
    "Full timesheet context, status, and submitted line items.",
    badge="Timesheets",
)

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

try:
    rows = api.list_timesheets()
    projects = api.list_projects()
except APIError as e:
    st.error(str(e))
    st.stop()

if not rows:
    st.info("No timesheets found.")
    st.stop()

project_name_by_id = {p["id"]: p["project_name"] for p in projects}
timesheet_ids = [str(r["id"]) for r in rows]
default_ts = st.session_state.get("context_timesheet_id")
default_idx = timesheet_ids.index(default_ts) if default_ts in timesheet_ids else 0

nav_left, nav_mid, nav_right = st.columns([1, 1, 1.5])
with nav_left:
    if st.button("Back to Timesheets", use_container_width=True):
        try:
            st.switch_page("pages/1_Timesheets.py")
        except Exception:
            st.caption("Open `pages/1_Timesheets.py` from the sidebar.")
with nav_mid:
    if st.button("Open Edit", use_container_width=True):
        try:
            st.switch_page("pages/11_Timesheet_Edit.py")
        except Exception:
            st.caption("Open `pages/11_Timesheet_Edit.py` from the sidebar.")
with nav_right:
    timesheet_by_id = {str(r["id"]): r for r in rows}
    timesheet_options = list(timesheet_by_id.keys())
    selected_label = st.selectbox(
        "Timesheet",
        timesheet_options,
        index=default_idx,
        key="timesheet_detail_pick",
        format_func=lambda ts_id: (
            f"{ts_id[:8]} | "
            f"{project_name_by_id.get(timesheet_by_id[ts_id]['project_id'], 'Unknown project')} | "
            f"{timesheet_by_id[ts_id]['period_start']} -> {timesheet_by_id[ts_id]['period_end']} | "
            f"{str(timesheet_by_id[ts_id]['status']).title()}"
        ),
    )

timesheet_id = selected_label
st.session_state["context_timesheet_id"] = timesheet_id

try:
    detail = api.get_timesheet(timesheet_id)
except APIError as e:
    st.error(str(e))
    st.stop()

status = str(detail.get("status", "")).upper()
project_name = project_name_by_id.get(detail.get("project_id"), "Unknown project")

kpi_strip(
    [
        {
            "label": "Timesheet",
            "value": str(detail.get("id", ""))[:8],
            "foot": f"Project: {project_name}",
            "tone": "neutral",
        },
        {
            "label": "Status",
            "value": status.title(),
            "foot": "Workflow state",
            "tone": _status_tone(status),
        },
        {
            "label": "Period",
            "value": f"{detail.get('period_start')} -> {detail.get('period_end')}",
            "foot": "Timesheet reporting window",
            "tone": "neutral",
        },
        {
            "label": "Total Hours",
            "value": f"{float(detail.get('total_hours', 0.0)):.2f} h",
            "foot": "Deterministic sum of entries",
            "tone": "primary",
        },
    ]
)

section("Timesheet Profile")
left, right = st.columns(2)
with left:
    st.markdown(f"**Employee:** {detail.get('employee_name') or '-'}")
    st.markdown(f"**Employee ID:** {detail.get('employee_id')}")
    st.markdown(f"**Project:** {project_name}")
with right:
    st.markdown(
        f"**Status:** {chip(status.title(), _status_tone(status))}",
        unsafe_allow_html=True,
    )
    st.markdown(f"**Period Start:** {detail.get('period_start')}")
    st.markdown(f"**Period End:** {detail.get('period_end')}")

if detail.get("rejection_reason"):
    section("Rejection Note")
    st.warning(detail.get("rejection_reason"))

section("Entries")
entries = detail.get("entries", [])
if not entries:
    st.caption("No entries added yet.")
else:
    entries_df = pd.DataFrame(
        [
            {
                "Work Date": e.get("work_date"),
                "Discipline": e.get("discipline"),
                "Hours": float(e.get("hours", 0.0)),
                "Billable": "Yes" if e.get("billable") else "No",
                "Notes": e.get("notes") or "",
            }
            for e in entries
        ]
    )
    st.dataframe(
        entries_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Hours": st.column_config.NumberColumn("Hours", format="%.2f h"),
        },
    )
