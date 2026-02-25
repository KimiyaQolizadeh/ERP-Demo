import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, section

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

DIVISIONS = ["ICI", "Cx", "SD"]
CONTRACT_TYPES = ["HOURLY", "LUMP_SUM"]
STATUSES = ["PROPOSAL", "AWARDED", "COMPLETED", "CANCELLED", "NOT_AWARDED"]
DEFAULT_RATES = [
    {"rate_key": "Mechanical", "rate": 140.0},
    {"rate_key": "Electrical", "rate": 160.0},
    {"rate_key": "Civil", "rate": 130.0},
    {"rate_key": "PM", "rate": 180.0},
]


def _clean_rates(rows: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        key = str(row.get("rate_key", "")).strip()
        if not key:
            continue
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        try:
            rate = float(row.get("rate", 0))
        except Exception:
            continue
        if rate <= 0:
            continue
        out.append({"rate_key": key, "rate": rate})
    return out


apply_theme(
    "Create Project",
    "Project setup and initial rate schedule are created here.",
    badge="Projects",
)

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
user_role = str(st.session_state.get("user_role", "") or "").upper()
if user_role not in {"PM", "ADMIN"}:
    st.warning("Project creation is available only for PM or Admin users.")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

nav_left, nav_right = st.columns([1, 1])
with nav_left:
    if st.button("Back to Projects", use_container_width=True):
        try:
            st.switch_page("pages/0_Projects.py")
        except Exception:
            st.caption("Open `pages/0_Projects.py` from the sidebar.")
with nav_right:
    st.empty()

try:
    users = api.list_users()
except APIError as e:
    st.error(str(e))
    st.stop()

pm_users = [u for u in users if u["role"] in ("PM", "ADMIN")]
pm_map = {f"{u['name']} ({u['role']})": u for u in pm_users}
if not pm_map:
    st.error("No PM/ADMIN users are available to assign as project manager.")
    st.stop()

section("Project Form")
with st.form("create_project_form", clear_on_submit=False):
    c1, c2 = st.columns(2)
    with c1:
        project_name = st.text_input("Project name", value="New Project")
        client_name = st.text_input("Client name", value="Client Inc.")
        division = st.selectbox("Division", DIVISIONS)
        discipline = st.selectbox("Discipline", ["Mechanical", "Electrical", "Civil", "PM"])
        pm_label = st.selectbox("Assigned PM", list(pm_map.keys()))
    with c2:
        start_date = st.date_input("Start date", value=date.today())
        end_date = st.date_input("End date", value=date.today() + timedelta(days=120))
        contract_type = st.selectbox("Contract type", CONTRACT_TYPES)
        approved_budget = st.number_input("Approved budget", min_value=1000.0, value=150000.0, step=1000.0)
        status = st.selectbox("Status", STATUSES)
        not_awarded_reason = st.text_input(
            "Not awarded reason",
            value="Lost to competitor" if status == "NOT_AWARDED" else "",
            disabled=(status != "NOT_AWARDED"),
        )

    create_rates_df = st.data_editor(
        pd.DataFrame(DEFAULT_RATES),
        num_rows="dynamic",
        use_container_width=True,
        key="project_create_rates_page",
    )
    create_btn = st.form_submit_button("Create project", type="primary")

if create_btn:
    try:
        payload = {
            "project_name": project_name,
            "client_name": client_name,
            "division": division,
            "discipline": discipline,
            "pm_user_id": pm_map[pm_label]["id"],
            "start_date": str(start_date),
            "end_date": str(end_date),
            "contract_type": contract_type,
            "approved_budget": float(approved_budget),
            "status": status,
            "not_awarded_reason": not_awarded_reason if status == "NOT_AWARDED" else None,
            "rates": _clean_rates(create_rates_df.to_dict(orient="records")),
        }
        created = api.create_project(payload)
        st.session_state["context_project_id"] = created.get("id")
        st.session_state["context_project_label"] = f"{created.get('project_name')} ({created.get('status')})"
        st.success(f"Created project: {created.get('project_name')}")
        try:
            st.switch_page("pages/9_Project_Details.py")
        except Exception:
            st.caption("Open `pages/9_Project_Details.py` from the sidebar.")
    except APIError as e:
        st.error(str(e))
