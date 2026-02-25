import os
from datetime import date

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, chip, section

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
    "Edit Timesheet",
    "Edit lines for draft-ready timesheets and submit to PM.",
    badge="Timesheets",
)

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
user_role = str(st.session_state.get("user_role", "") or "").upper()
if user_role not in {"EMPLOYEE", "ADMIN"}:
    st.warning("Timesheet edit is available only for Employee or Admin users.")
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
editable_rows = [r for r in rows if str(r.get("status", "")).upper() in {"REJECTED", "DRAFT"}]
if not editable_rows:
    st.info("No rejected or draft timesheets available for editing.")
    st.stop()

ts_ids = [str(r["id"]) for r in editable_rows]
default_ts = st.session_state.get("context_timesheet_id")
default_idx = ts_ids.index(default_ts) if default_ts in ts_ids else 0

nav_left, nav_mid, nav_right = st.columns([1, 1, 1.5])
with nav_left:
    if st.button("Back to Timesheets", use_container_width=True):
        try:
            st.switch_page("pages/1_Timesheets.py")
        except Exception:
            st.caption("Open `pages/1_Timesheets.py` from the sidebar.")
with nav_mid:
    if st.button("Open Details", use_container_width=True):
        try:
            st.switch_page("pages/10_Timesheet_Details.py")
        except Exception:
            st.caption("Open `pages/10_Timesheet_Details.py` from the sidebar.")
with nav_right:
    timesheet_by_id = {str(r["id"]): r for r in editable_rows}
    timesheet_options = list(timesheet_by_id.keys())
    selected_label = st.selectbox(
        "Timesheet",
        timesheet_options,
        index=default_idx,
        key="timesheet_edit_pick",
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

section("Timesheet Context")
st.markdown(
    f"Status: {chip(status.title(), _status_tone(status))} &nbsp;&nbsp; Project: **{project_name}**",
    unsafe_allow_html=True,
)
st.caption(f"Period: {detail.get('period_start')} -> {detail.get('period_end')}")

if status == "REJECTED":
    try:
        api.reopen_timesheet(timesheet_id)
        st.success("Rejected timesheet reopened as Draft for editing.")
        st.rerun()
    except APIError as e:
        st.error(str(e))
        st.stop()

if status != "DRAFT":
    st.warning("Only Draft timesheets can be edited and submitted.")
    st.stop()

section("Current Entries")
try:
    entries = api.list_time_entries(timesheet_id)
except APIError as e:
    st.error(str(e))
    st.stop()

if entries:
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
else:
    st.caption("No entries yet.")

section("Add Entry")
c1, c2, c3 = st.columns(3)
with c1:
    work_date = st.date_input("Work date", value=date.today())
with c2:
    discipline = st.selectbox("Discipline", ["Mechanical", "Electrical", "Civil", "PM"])
with c3:
    hours = st.number_input("Hours", min_value=0.5, max_value=24.0, value=8.0, step=0.5)
billable = st.checkbox("Billable", value=True)
notes = st.text_area("Notes", value="Client coordination and design review", height=110)

add_col, submit_col = st.columns(2)
with add_col:
    if st.button("Add entry", use_container_width=True):
        try:
            payload = {
                "work_date": str(work_date),
                "discipline": discipline,
                "hours": float(hours),
                "billable": bool(billable),
                "notes": notes,
            }
            api.add_entry(timesheet_id, payload)
            st.success("Entry added.")
            st.rerun()
        except APIError as e:
            st.error(str(e))

with submit_col:
    if st.button("Submit timesheet", type="primary", use_container_width=True):
        try:
            api.submit_timesheet(timesheet_id)
            st.success("Timesheet submitted.")
            st.rerun()
        except APIError as e:
            st.error(str(e))
