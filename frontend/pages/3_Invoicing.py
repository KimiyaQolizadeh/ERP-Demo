import os
from datetime import date

import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, section, kpi_strip, chip

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

apply_theme(
    "Invoicing",
    "Draft and approve invoices from approved, billable, uninvoiced time entries.",
    badge="Finance",
)

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
user_role = str(st.session_state.get("user_role", "") or "").upper()
if user_role not in {"PM", "FINANCE", "ADMIN"}:
    st.warning("This page is restricted to PM/Finance users.")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

default_month = st.session_state.get("context_month", date.today())
if isinstance(default_month, str):
    default_month = date.fromisoformat(default_month)
month_ctx = st.date_input("Project listing month context", value=default_month, key="inv_month_ctx")
st.session_state["context_month"] = month_ctx
try:
    dash = api.dashboard(str(month_ctx))
except APIError as e:
    st.error(str(e))
    st.stop()

projects = dash.get("projects", [])
if not projects:
    st.warning("No projects found. Run seed first.")
    st.stop()

proj_map = {f"{p['project_name']} ({p['status']})": p for p in projects}
proj_labels = list(proj_map.keys())
proj_ids = [p["project_id"] for p in projects]
default_project_id = st.session_state.get("context_project_id")
default_proj_idx = proj_ids.index(default_project_id) if default_project_id in proj_ids else 0
proj_label = st.selectbox("Project", proj_labels, index=default_proj_idx, key="inv_project_label")
project = proj_map[proj_label]
project_id = project["project_id"]
st.session_state["context_project_id"] = project_id
st.session_state["context_project_label"] = proj_label
invoice_month = st.date_input("Invoice month", value=month_ctx, key="inv_month")

kpi_strip(
    [
        {"label": "Project", "value": project["project_name"], "foot": f"Status: {project['status']}", "tone": "neutral"},
        {"label": "Contract Type", "value": str(project.get("contract_type", "N/A")), "foot": "Commercial structure", "tone": "primary"},
        {
            "label": "Budget Consumed",
            "value": f"{float(project.get('percent_budget_consumed', 0.0)):.1f}%",
            "foot": f"Spend ${float(project.get('spend_to_date', 0.0)):,.0f}",
            "tone": "warn",
        },
        {"label": "ERP Rule", "value": "No double invoicing", "foot": "Guard: invoiced_line_id IS NULL", "tone": "primary"},
    ]
)

section("Generate Draft", "Only approved + billable + uninvoiced entries in eligible project statuses are included.")
if str(project.get("contract_type", "")).upper() == "LUMP_SUM":
    st.caption("Lump-sum projects bill progress value and cap against remaining approved budget.")
if st.button("Generate invoice draft", type="primary"):
    try:
        draft = api.draft_invoice(project_id, str(invoice_month))
        st.session_state["last_draft"] = draft
        st.success("Invoice draft generated.")
    except APIError as e:
        st.error(str(e))

draft = st.session_state.get("last_draft")
if not draft:
    st.info("Generate a draft invoice to continue.")
    st.stop()

status = str(draft.get("status", "UNKNOWN"))
subtotal = float(draft.get("subtotal", draft.get("line_total", 0.0)))
adjustments_total = float(draft.get("adjustments_total", 0.0))
total = float(draft.get("total", draft.get("amount_due", 0.0)))

section("Invoice Draft Detail")
kpi_strip(
    [
        {"label": "Invoice ID", "value": str(draft.get("invoice_id", "")), "foot": f"Month: {draft.get('month', str(invoice_month))}", "tone": "neutral"},
        {"label": "Status", "value": status, "foot": "Draft must be approved by finance", "tone": "warn" if status == "DRAFT" else "success"},
        {"label": "Subtotal", "value": f"${subtotal:,.2f}", "foot": "Deterministic backend calc", "tone": "primary"},
        {"label": "Adjustments", "value": f"${adjustments_total:,.2f}", "foot": "Manual patch items", "tone": "neutral"},
        {"label": "Total", "value": f"${total:,.2f}", "foot": "Final amount due", "tone": "success"},
    ]
)

section("Adjustment", "Allowed only while status is DRAFT.")
desc = st.text_input("Description", value="Manual adjustment", key="inv_adj_desc")
amt = st.number_input("Amount (+/-)", value=0.0, step=10.0, key="inv_adj_amt")
if st.button("Apply adjustment", use_container_width=True):
    if status != "DRAFT":
        st.warning("Adjustments are allowed only on draft invoices.")
    else:
        try:
            updated = api.add_adjustment(draft["invoice_id"], desc, float(amt))
            st.session_state["last_draft"] = updated
            st.success("Adjustment applied.")
            st.rerun()
        except APIError as e:
            st.error(str(e))

left, right = st.columns(2)
with left:
    section("Approve Invoice", "Finance action.")
    if st.button("Approve invoice", use_container_width=True, type="primary"):
        try:
            st.json(api.approve_invoice(draft["invoice_id"]))
        except APIError as e:
            st.error(str(e))
with right:
    section("Export")
    if st.button("Export invoice JSON", use_container_width=True):
        try:
            st.json(api.export_invoice(draft["invoice_id"]))
        except APIError as e:
            st.error(str(e))

st.markdown(f"ERP safety: {chip('LLM does not calculate totals', 'success')}", unsafe_allow_html=True)
with st.expander("Trace: raw draft payload"):
    st.json(draft)
