import os
import streamlit as st
from dotenv import load_dotenv
from client.api import APIClient
from components.design_system import apply_theme, section, kpi_strip

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Project Control Copilot",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"Get Help": None, "Report a Bug": None, "About": None},
)

# Session defaults
if "backend_url" not in st.session_state:
    st.session_state["backend_url"] = BACKEND_URL
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "user_label" not in st.session_state:
    st.session_state["user_label"] = None
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None
if "context_month" not in st.session_state:
    st.session_state["context_month"] = None
if "context_project_id" not in st.session_state:
    st.session_state["context_project_id"] = None
if "context_project_label" not in st.session_state:
    st.session_state["context_project_label"] = None

api = APIClient(st.session_state["backend_url"])

# Sidebar: Backend + Login
st.sidebar.header("Connection")
st.sidebar.text_input("Backend URL", key="backend_url")

st.sidebar.divider()
st.sidebar.header("Login (Fake Auth)")

try:
    users = api.list_login_options()
except Exception as e:
    st.error(f"Backend not reachable. Error: {e}")
    st.stop()

labels = [f"{u['name']} ({u['role']})" for u in users]
default_idx = 0
if st.session_state["user_label"] in labels:
    default_idx = labels.index(st.session_state["user_label"])

selected = st.sidebar.selectbox("Select a user", labels, index=default_idx)
st.session_state["user_label"] = selected
selected_user = users[labels.index(selected)]
st.session_state["user_id"] = selected_user["id"]
st.session_state["user_role"] = selected_user["role"]

st.sidebar.caption(f"Using X-User-Id: {st.session_state['user_id']}")

st.sidebar.divider()
st.sidebar.subheader("Health")
if st.sidebar.button("Check API"):
    st.sidebar.write(api.health())

apply_theme(
    "ERP Project Control Copilot",
    "AI-assisted timesheets, approvals, invoicing, reporting, and copilot assistance.",
    badge="Demo",
)

# Main home
section("Workspace Snapshot", "Current connection and identity context for this session.")
kpi_strip(
    [
        {"label": "Connected API", "value": st.session_state["backend_url"], "foot": "Backend target", "tone": "neutral"},
        {"label": "Logged User", "value": selected_user["name"], "foot": selected_user["role"], "tone": "primary"},
        {"label": "Available Users", "value": str(len(users)), "foot": "Seeded demo accounts", "tone": "success"},
    ]
)

section("Pages", "Use the Streamlit multipage navigation on the left.")
st.markdown(
    """
<div class="pc-page-grid">
  <div class="pc-page-card">
    <div class="pc-page-card-title">Projects</div>
    <div class="pc-page-card-sub">Project setup, lifecycle status, PM assignment, and rate schedule management.</div>
  </div>
  <div class="pc-page-card">
    <div class="pc-page-card-title">Timesheets</div>
    <div class="pc-page-card-sub">Draft entries, AI note rewrite, billable probability, text/voice parsing.</div>
  </div>
  <div class="pc-page-card">
    <div class="pc-page-card-title">Approvals</div>
    <div class="pc-page-card-sub">PM approval inbox with submit/approve/reject ERP workflow guardrails.</div>
  </div>
  <div class="pc-page-card">
    <div class="pc-page-card-title">Invoicing</div>
    <div class="pc-page-card-sub">Draft invoice, deterministic totals, adjustments, approval, export.</div>
  </div>
  <div class="pc-page-card">
    <div class="pc-page-card-title">Reports / Chat Assistant</div>
    <div class="pc-page-card-sub">Portfolio reporting plus AI chat for project, employee, forecast, and invoice insights.</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.info("Seed data includes pending approvals, approved entries, and invoice-ready scenarios for demo flow.")
