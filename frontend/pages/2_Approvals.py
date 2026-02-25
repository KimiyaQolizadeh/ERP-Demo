import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, section, kpi_strip, chip

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

apply_theme(
    "Approvals Console",
    "PM-only workflow to approve or reject submitted timesheets on managed projects.",
    badge="PM",
)

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
user_role = str(st.session_state.get("user_role", "") or "").upper()
if user_role not in {"PM", "ADMIN"}:
    st.warning("This page is available only to PM users.")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

try:
    rows = api.pending_approvals()
except APIError as e:
    st.error(str(e))
    st.info("Approvals require a PM user who manages at least one project.")
    st.stop()

pending_df = pd.DataFrame(rows)
pending_count = len(rows)
billable_hours = float(sum(float(r.get("total_billable_hours", 0.0)) for r in rows))

kpi_strip(
    [
        {"label": "Pending Approvals", "value": str(pending_count), "foot": "Submitted timesheets", "tone": "warn"},
        {"label": "Billable Hours Pending", "value": f"{billable_hours:.1f}h", "foot": "Potential invoice unlock", "tone": "primary"},
        {"label": "Workflow Rule", "value": "PM only", "foot": "Submitted -> Approved/Rejected", "tone": "neutral"},
    ]
)

section("Approval Inbox", "These rows are pending for your projects only.")
if pending_df.empty:
    st.info("No pending approvals for this user.")
else:
    display_cols = [
        "employee_name",
        "project_name",
        "period_start",
        "period_end",
        "status",
        "total_hours",
        "total_billable_hours",
    ]
    display_df = pending_df[[c for c in display_cols if c in pending_df.columns]].copy()
    display_df = display_df.rename(
        columns={
            "employee_name": "Employee",
            "project_name": "Project",
            "period_start": "Period Start",
            "period_end": "Period End",
            "status": "Status",
            "total_hours": "Total Hours",
            "total_billable_hours": "Billable Hours",
        }
    )
    st.dataframe(display_df, use_container_width=True, height=300, hide_index=True)

section("Approve / Reject", "Use explicit action with reason for rejects.")
pending_ids = [r.get("id", "") for r in rows if r.get("id")]
selected = st.selectbox("Pending Timesheet ID", ["(enter manually)"] + pending_ids, key="appr_pending_select")
if selected != "(enter manually)":
    st.session_state["appr_ts_id"] = selected
ts_id = st.text_input("Timesheet ID", key="appr_ts_id")
reason = st.text_input("Reject reason", value="Missing detail in notes", key="appr_reject_reason")

action_left, action_right = st.columns(2)
with action_left:
    if st.button("Approve", use_container_width=True, type="primary"):
        if not ts_id.strip():
            st.warning("Enter or select a timesheet ID.")
        else:
            try:
                st.json(api.approve_timesheet(ts_id.strip()))
                st.success("Timesheet approved.")
            except APIError as e:
                st.error(str(e))

with action_right:
    if st.button("Reject", use_container_width=True):
        if not ts_id.strip():
            st.warning("Enter or select a timesheet ID.")
        else:
            try:
                st.json(api.reject_timesheet(ts_id.strip(), reason))
                st.warning("Timesheet rejected.")
            except APIError as e:
                st.error(str(e))

st.markdown(
    f"RBAC guard: {chip('Only PM of project can approve/reject', 'warn')}",
    unsafe_allow_html=True,
)
