import os
from datetime import date

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


def _safe_index(options: list[str], value: str, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


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


def _parse_date(raw) -> date:
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


apply_theme(
    "Edit Project",
    "Update project setup, lifecycle state, and rate schedule.",
    badge="Projects",
)

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
user_role = str(st.session_state.get("user_role", "") or "").upper()
if user_role not in {"PM", "ADMIN"}:
    st.warning("Project edit is available only for PM or Admin users.")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

try:
    projects = api.list_projects()
    users = api.list_users()
except APIError as e:
    st.error(str(e))
    st.stop()

if not projects:
    st.info("No projects found.")
    st.stop()

pm_users = [u for u in users if u["role"] in ("PM", "ADMIN")]
pm_map = {f"{u['name']} ({u['role']})": u for u in pm_users}
if not pm_map:
    st.error("No PM/ADMIN users are available to assign as project manager.")
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
    if st.button("Open Details", use_container_width=True):
        try:
            st.switch_page("pages/9_Project_Details.py")
        except Exception:
            st.caption("Open `pages/9_Project_Details.py` from the sidebar.")
with nav_right:
    selected_label = st.selectbox("Project", project_labels, index=default_index, key="project_edit_pick")

selected_project = project_map[selected_label]
project_id = selected_project["id"]
st.session_state["context_project_id"] = project_id
st.session_state["context_project_label"] = selected_label

try:
    detail = api.get_project(project_id)
except APIError as e:
    st.error(str(e))
    st.stop()

pm_default_idx = 0
for idx, label in enumerate(pm_map.keys()):
    if pm_map[label]["id"] == detail.get("pm_user_id"):
        pm_default_idx = idx
        break

section("Project Form")
with st.form("update_project_form"):
    u1, u2 = st.columns(2)
    with u1:
        up_project_name = st.text_input("Project name", value=detail.get("project_name", ""))
        up_client_name = st.text_input("Client name", value=detail.get("client_name", ""))
        up_division = st.selectbox("Division", DIVISIONS, index=_safe_index(DIVISIONS, detail.get("division", "ICI")))
        up_discipline = st.text_input("Discipline", value=detail.get("discipline", ""))
        up_pm_label = st.selectbox("Assigned PM", list(pm_map.keys()), index=pm_default_idx)
    with u2:
        up_start = st.date_input("Start date", value=_parse_date(detail.get("start_date")))
        up_end = st.date_input("End date", value=_parse_date(detail.get("end_date")))
        up_contract = st.selectbox(
            "Contract type",
            CONTRACT_TYPES,
            index=_safe_index(CONTRACT_TYPES, detail.get("contract_type", "HOURLY")),
        )
        up_budget = st.number_input("Approved budget", min_value=1000.0, value=float(detail.get("approved_budget", 0.0)))
        up_status = st.selectbox("Status", STATUSES, index=_safe_index(STATUSES, detail.get("status", "PROPOSAL")))
        up_reason = st.text_input(
            "Not awarded reason",
            value=detail.get("not_awarded_reason") or "",
            disabled=(up_status != "NOT_AWARDED"),
        )
    update_btn = st.form_submit_button("Save project changes", type="primary")

if update_btn:
    try:
        payload = {
            "project_name": up_project_name,
            "client_name": up_client_name,
            "division": up_division,
            "discipline": up_discipline,
            "pm_user_id": pm_map[up_pm_label]["id"],
            "start_date": str(up_start),
            "end_date": str(up_end),
            "contract_type": up_contract,
            "approved_budget": float(up_budget),
            "status": up_status,
            "not_awarded_reason": up_reason if up_status == "NOT_AWARDED" else None,
        }
        updated = api.update_project(project_id, payload)
        st.session_state["context_project_label"] = f"{updated.get('project_name')} ({updated.get('status')})"
        st.success("Project updated.")
        st.rerun()
    except APIError as e:
        st.error(str(e))

section("Rate Schedule")
rates_df = pd.DataFrame(detail.get("rates", []))
if rates_df.empty:
    rates_df = pd.DataFrame(DEFAULT_RATES)
else:
    rates_df = rates_df[["rate_key", "rate"]]

edited_rates = st.data_editor(
    rates_df,
    num_rows="dynamic",
    use_container_width=True,
    key=f"project_rates_editor_{project_id}",
)

if st.button("Save rate schedule", use_container_width=True):
    cleaned = _clean_rates(edited_rates.to_dict(orient="records"))
    if not cleaned:
        st.warning("At least one valid rate row is required.")
    else:
        try:
            api.replace_project_rates(project_id, cleaned)
            st.success("Rate schedule updated.")
            st.rerun()
        except APIError as e:
            st.error(str(e))
