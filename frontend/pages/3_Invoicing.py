import os
import json
from datetime import date
from html import escape

import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, section, kpi_strip, chip

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
INVOICE_ISSUER_NAME = os.getenv("INVOICE_ISSUER_NAME", "Project Control Copilot Services")
INVOICE_ISSUER_ADDRESS = os.getenv("INVOICE_ISSUER_ADDRESS", "100 Main Street, Suite 400")
INVOICE_ISSUER_EMAIL = os.getenv("INVOICE_ISSUER_EMAIL", "billing@projectcontrol.local")


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _money(value) -> str:
    return f"${_as_float(value):,.2f}"


def _invoice_preview_html(project: dict, invoice_doc: dict, status: str) -> str:
    lines = list(invoice_doc.get("lines") or [])
    adjustments = list(invoice_doc.get("adjustments") or [])
    invoice_id = str(invoice_doc.get("invoice_id", ""))
    invoice_month = str(invoice_doc.get("invoice_month", ""))
    client_name = str(project.get("client_name") or "Client")
    project_name = str(project.get("project_name") or "Project")

    line_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(str(line.get('rate_key') or '-'))}</td>"
            f"<td style='text-align:right'>{_as_float(line.get('hours')):,.2f}</td>"
            f"<td style='text-align:right'>{_money(line.get('rate'))}</td>"
            f"<td style='text-align:right'>{_money(line.get('amount'))}</td>"
            "</tr>"
        )
        for line in lines
    ) or (
        "<tr><td colspan='4' style='text-align:center;color:#64748b'>No billed line items for this invoice period.</td></tr>"
    )

    adjustment_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(str(adj.get('description') or '-'))}</td>"
            f"<td style='text-align:right'>{_money(adj.get('amount'))}</td>"
            "</tr>"
        )
        for adj in adjustments
    ) or (
        "<tr><td style='color:#64748b'>No manual adjustments</td><td style='text-align:right;color:#64748b'>$0.00</td></tr>"
    )

    subtotal = _as_float(invoice_doc.get("subtotal"))
    adjustments_total = _as_float(invoice_doc.get("adjustments_total"))
    total = _as_float(invoice_doc.get("total"))

    return f"""
<style>
.inv-preview {{
  border: 1px solid #dbe2ec;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08);
  padding: 1.1rem 1.2rem 1.3rem;
}}
.inv-head {{
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 0.9rem;
  margin-bottom: 0.9rem;
}}
.inv-title {{
  margin: 0;
  font-size: 1.3rem;
  color: #0f172a;
  font-weight: 800;
}}
.inv-sub {{
  color: #475569;
  font-size: 0.86rem;
  margin-top: 0.15rem;
}}
.inv-meta {{
  text-align: right;
  font-size: 0.84rem;
  color: #334155;
}}
.inv-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.8rem;
  margin-bottom: 0.9rem;
}}
.inv-card {{
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  background: #f8fafc;
}}
.inv-label {{
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #64748b;
  font-weight: 700;
}}
.inv-value {{
  color: #0f172a;
  font-size: 0.92rem;
  margin-top: 0.18rem;
  font-weight: 600;
}}
.inv-table {{
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.45rem;
}}
.inv-table th {{
  text-align: left;
  color: #334155;
  font-size: 0.76rem;
  font-weight: 700;
  border-bottom: 1px solid #dbe2ec;
  padding: 0.48rem 0.42rem;
  background: #f8fafc;
}}
.inv-table td {{
  border-bottom: 1px solid #edf2f7;
  padding: 0.45rem 0.42rem;
  color: #0f172a;
  font-size: 0.84rem;
}}
.inv-total {{
  margin-top: 0.95rem;
  display: flex;
  justify-content: flex-end;
}}
.inv-total-box {{
  width: min(360px, 100%);
  border: 1px solid #dbe2ec;
  border-radius: 10px;
  overflow: hidden;
}}
.inv-total-row {{
  display: flex;
  justify-content: space-between;
  padding: 0.48rem 0.62rem;
  font-size: 0.86rem;
  color: #0f172a;
  background: #ffffff;
}}
.inv-total-row + .inv-total-row {{
  border-top: 1px solid #e2e8f0;
}}
.inv-grand {{
  font-weight: 800;
  font-size: 0.92rem;
  background: #eff6ff;
}}
</style>
<div class="inv-preview">
  <div class="inv-head">
    <div>
      <h3 class="inv-title">Invoice</h3>
      <div class="inv-sub">{escape(INVOICE_ISSUER_NAME)}</div>
      <div class="inv-sub">{escape(INVOICE_ISSUER_ADDRESS)}</div>
      <div class="inv-sub">{escape(INVOICE_ISSUER_EMAIL)}</div>
    </div>
    <div class="inv-meta">
      <div><b>Invoice #</b> {escape(invoice_id[:8])}</div>
      <div><b>Status:</b> {escape(status)}</div>
      <div><b>Month:</b> {escape(invoice_month)}</div>
    </div>
  </div>

  <div class="inv-grid">
    <div class="inv-card">
      <div class="inv-label">Bill To</div>
      <div class="inv-value">{escape(client_name)}</div>
    </div>
    <div class="inv-card">
      <div class="inv-label">Project</div>
      <div class="inv-value">{escape(project_name)} ({escape(str(project.get("contract_type") or ""))})</div>
    </div>
  </div>

  <table class="inv-table">
    <thead>
      <tr>
        <th>Rate Key</th>
        <th style="text-align:right">Hours</th>
        <th style="text-align:right">Rate</th>
        <th style="text-align:right">Amount</th>
      </tr>
    </thead>
    <tbody>
      {line_rows}
    </tbody>
  </table>

  <table class="inv-table" style="margin-top:0.8rem">
    <thead>
      <tr>
        <th>Adjustment</th>
        <th style="text-align:right">Amount</th>
      </tr>
    </thead>
    <tbody>
      {adjustment_rows}
    </tbody>
  </table>

  <div class="inv-total">
    <div class="inv-total-box">
      <div class="inv-total-row"><span>Subtotal</span><span>{_money(subtotal)}</span></div>
      <div class="inv-total-row"><span>Adjustments</span><span>{_money(adjustments_total)}</span></div>
      <div class="inv-total-row inv-grand"><span>Total</span><span>{_money(total)}</span></div>
    </div>
  </div>
</div>
"""


def _invoice_download_html(project: dict, invoice_doc: dict, status: str) -> str:
    body = _invoice_preview_html(project, invoice_doc, status)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Invoice</title></head><body style='margin:20px;background:#f1f5f9'>"
        f"{body}"
        "<p style='font-family:Arial,sans-serif;color:#475569;font-size:12px;margin-top:16px'>"
        "Tip: Use browser Print to save as PDF."
        "</p></body></html>"
    )

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
        st.session_state["last_invoice_export"] = api.export_invoice(draft["invoice_id"])
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
    section("Approve Invoice")
    if st.button("Approve invoice", use_container_width=True, type="primary"):
        try:
            approved = api.approve_invoice(draft["invoice_id"])
            refreshed = dict(draft)
            refreshed["status"] = str(approved.get("status", "APPROVED"))
            st.session_state["last_draft"] = refreshed
            st.session_state["last_invoice_export"] = api.export_invoice(draft["invoice_id"])
            st.success("Invoice approved.")
            st.rerun()
        except APIError as e:
            st.error(str(e))
with right:
    section("Refresh Document")
    if st.button("Refresh invoice document", use_container_width=True):
        try:
            st.session_state["last_invoice_export"] = api.export_invoice(draft["invoice_id"])
            st.success("Invoice document refreshed.")
            st.rerun()
        except APIError as e:
            st.error(str(e))

st.markdown(f"ERP safety: {chip('LLM does not calculate totals', 'success')}", unsafe_allow_html=True)
st.caption("Approved invoices remain stored in ERP and can be reopened by project/month.")

invoice_doc = st.session_state.get("last_invoice_export")
if not invoice_doc or str(invoice_doc.get("invoice_id", "")) != str(draft.get("invoice_id", "")):
    try:
        invoice_doc = api.export_invoice(draft["invoice_id"])
        st.session_state["last_invoice_export"] = invoice_doc
    except APIError:
        invoice_doc = {
            "invoice_id": draft.get("invoice_id"),
            "invoice_month": draft.get("invoice_month", str(invoice_month)),
            "status": draft.get("status", "DRAFT"),
            "subtotal": subtotal,
            "adjustments_total": adjustments_total,
            "total": total,
            "lines": list(draft.get("lines", [])),
            "adjustments": [],
        }

section("Invoice Document", "Professional preview for review and handoff.")
status_label = str(invoice_doc.get("status") or status)
st.markdown(_invoice_preview_html(project, invoice_doc, status_label), unsafe_allow_html=True)

download_cols = st.columns(2)
with download_cols[0]:
    invoice_html = _invoice_download_html(project, invoice_doc, status_label)
    st.download_button(
        "Download Invoice (HTML, printable)",
        data=invoice_html.encode("utf-8"),
        file_name=f"invoice-{str(invoice_doc.get('invoice_id', 'draft'))[:8]}.html",
        mime="text/html",
        use_container_width=True,
    )
with download_cols[1]:
    st.download_button(
        "Download Invoice JSON",
        data=json.dumps(invoice_doc, indent=2),
        file_name=f"invoice-{str(invoice_doc.get('invoice_id', 'draft'))[:8]}.json",
        mime="application/json",
        use_container_width=True,
    )
