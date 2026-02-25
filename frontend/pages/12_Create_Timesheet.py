import hashlib
import os
from datetime import date, timedelta

import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, chip, section

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
DEFAULT_DISCIPLINE_CHOICES = ["Mechanical", "Electrical", "Civil", "PM"]


def _period_signature(project_id: str, period_start: date, period_end: date) -> str:
    return f"{project_id}|{period_start}|{period_end}"


def _set_active_draft(timesheet_id: str, signature: str) -> None:
    st.session_state["ts_active_draft_id"] = str(timesheet_id)
    st.session_state["ts_active_draft_signature"] = signature
    st.session_state["context_timesheet_id"] = str(timesheet_id)


def _get_active_draft(signature: str) -> str | None:
    active_id = str(st.session_state.get("ts_active_draft_id") or "").strip()
    active_sig = str(st.session_state.get("ts_active_draft_signature") or "")
    if active_id and active_sig == signature:
        return active_id
    return None


def _create_draft(api: APIClient, project_id: str, period_start: date, period_end: date) -> str:
    created = api.create_timesheet(
        {
            "project_id": project_id,
            "period_start": str(period_start),
            "period_end": str(period_end),
        }
    )
    return str(created["id"])


def _add_entry(
    api: APIClient,
    *,
    timesheet_id: str,
    period_end: date,
    discipline: str,
    hours: float,
    billable: bool,
    notes: str,
) -> None:
    api.add_entry(
        timesheet_id,
        {
            "work_date": str(period_end),
            "discipline": discipline,
            "hours": float(hours),
            "billable": bool(billable),
            "notes": notes,
        },
    )


def _ensure_active_draft(
    api: APIClient,
    *,
    signature: str,
    project_id: str,
    period_start: date,
    period_end: date,
) -> str:
    active_id = _get_active_draft(signature)
    if active_id:
        return active_id
    created_id = _create_draft(api, project_id, period_start, period_end)
    _set_active_draft(created_id, signature)
    return created_id


def _normalize_ai_entries(
    entries: list[dict], *, period_end: date, discipline: str
) -> list[dict]:
    normalized = []
    for entry in entries:
        hours = float(entry.get("hours", 0.0) or 0.0)
        notes = str(entry.get("notes_clean") or "").strip()
        if hours <= 0 or not notes:
            continue
        normalized.append(
            {
                "work_date": str(entry.get("work_date") or period_end),
                "discipline": str(entry.get("discipline") or discipline),
                "hours": hours,
                "billable": bool(entry.get("billable_suggestion", True)),
                "notes": notes,
            }
        )
    return normalized


def _missing_details_question(entries: list[dict], transcript: str) -> str | None:
    if entries:
        return None
    transcript_hint = transcript[:140].strip() if transcript else ""
    hint = f" Transcript: {transcript_hint}" if transcript_hint else ""
    return "I need at least hours and notes to create an entry." + hint


def _apply_entries_to_active_draft(
    api: APIClient,
    *,
    entries: list[dict],
    signature: str,
    project_id: str,
    period_start: date,
    period_end: date,
) -> tuple[str, int]:
    draft_id = _ensure_active_draft(
        api,
        signature=signature,
        project_id=project_id,
        period_start=period_start,
        period_end=period_end,
    )
    for payload in entries:
        api.add_entry(draft_id, payload)
    return draft_id, len(entries)


apply_theme(
    "Create Timesheet",
    "Single-form creation flow with AI note assist and voice entry.",
    badge="Timesheets",
)

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
user_role = str(st.session_state.get("user_role", "") or "").upper()
if user_role not in {"EMPLOYEE", "ADMIN"}:
    st.warning("Timesheet creation is available only for Employee or Admin users.")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

nav_left, nav_mid = st.columns([1.0, 4.0])
with nav_left:
    if st.button("Back to Timesheets", use_container_width=True):
        try:
            st.switch_page("pages/1_Timesheets.py")
        except Exception:
            st.caption("Open `pages/1_Timesheets.py` from the sidebar.")
with nav_mid:
    st.empty()

if "ts_create_notes" not in st.session_state:
    st.session_state["ts_create_notes"] = "Client coordination and design review"

today = date.today()
try:
    projects = api.list_projects()
    users = api.list_users()
except APIError as e:
    st.error(str(e))
    st.stop()

if not projects:
    st.warning("No projects found. Run seed first.")
    st.stop()

current_user = next((u for u in users if str(u.get("id")) == str(user_id)), None)
employee_discipline = str((current_user or {}).get("discipline") or "PM")
employee_name = str((current_user or {}).get("name") or "Current user")
voice_discipline_choices = [employee_discipline] + [
    d for d in DEFAULT_DISCIPLINE_CHOICES if d != employee_discipline
]

project_by_id = {p["id"]: p for p in projects}
proj_ids = list(project_by_id.keys())
default_project_id = st.session_state.get("context_project_id")
default_proj_idx = (
    proj_ids.index(default_project_id) if default_project_id in proj_ids else 0
)

section("Create Timesheet", "One form: save draft, submit, add entry, and speak-to-create.")
c1, c2, c3 = st.columns([1.5, 1.0, 1.0])
with c1:
    project_id = st.selectbox(
        "Project",
        proj_ids,
        index=default_proj_idx,
        format_func=lambda pid: (
            f"{project_by_id[pid]['project_name']} ({project_by_id[pid]['status'].replace('_', ' ').title()})"
        ),
        key="ts_create_project_id",
    )
    project_name = project_by_id[project_id]["project_name"]
    st.session_state["context_project_id"] = project_id
    st.session_state["context_project_label"] = (
        f"{project_name} ({project_by_id[project_id]['status'].replace('_', ' ').title()})"
    )
with c2:
    period_start = st.date_input("Period start", value=today - timedelta(days=6))
with c3:
    period_end = st.date_input("Period end", value=today)

signature = _period_signature(project_id, period_start, period_end)
active_draft_id = _get_active_draft(signature)

c4, c5, c6 = st.columns([1.0, 1.0, 1.2])
with c4:
    hours = st.number_input("Hours", min_value=0.5, max_value=24.0, value=8.0, step=0.5)
with c5:
    billable = st.checkbox("Billable (final override)", value=True)
with c6:
    st.markdown(
        f"Discipline: {chip(employee_discipline, 'neutral')}",
        unsafe_allow_html=True,
    )
    draft_label = active_draft_id[:8] if active_draft_id else "Not created yet"
    st.caption(f"Current draft: {draft_label}")

notes_head_left, notes_head_right = st.columns([12, 1], vertical_alignment="center")
with notes_head_left:
    st.markdown("**Notes**")
with notes_head_right:
    if st.button("✨", key="ts_notes_improve_icon", help="Improve notes (AI)"):
        try:
            resp = api.ai_improve_notes(
                st.session_state["ts_create_notes"],
                discipline=employee_discipline,
                project_name=project_name,
            )
            improved = resp.get("result", {}).get("improved_notes", "")
            if improved:
                st.session_state["ts_create_notes"] = improved
                api.ai_accept_suggestion(
                    "AI_ACCEPTED_NOTES",
                    entity_type="TimeEntry",
                    accepted=True,
                    input_payload={"raw_notes": st.session_state["ts_create_notes"]},
                    output_payload={"improved_notes": improved},
                )
                st.success("Notes improved and applied.")
                st.rerun()
        except APIError as e:
            st.error(str(e))

st.text_area("Notes", key="ts_create_notes", height=120, label_visibility="collapsed")

save_col, submit_col, add_col = st.columns(3)
with save_col:
    if st.button("Save as Draft", use_container_width=True):
        try:
            draft_id = _ensure_active_draft(
                api,
                signature=signature,
                project_id=project_id,
                period_start=period_start,
                period_end=period_end,
            )
            _add_entry(
                api,
                timesheet_id=draft_id,
                period_end=period_end,
                discipline=employee_discipline,
                hours=float(hours),
                billable=bool(billable),
                notes=st.session_state["ts_create_notes"],
            )
            st.success(f"Saved to draft {draft_id[:8]}.")
        except APIError as e:
            st.error(str(e))
with submit_col:
    if st.button("Submit", type="primary", use_container_width=True):
        try:
            draft_id = _ensure_active_draft(
                api,
                signature=signature,
                project_id=project_id,
                period_start=period_start,
                period_end=period_end,
            )
            _add_entry(
                api,
                timesheet_id=draft_id,
                period_end=period_end,
                discipline=employee_discipline,
                hours=float(hours),
                billable=bool(billable),
                notes=st.session_state["ts_create_notes"],
            )
            api.submit_timesheet(draft_id)
            st.success(f"Submitted timesheet {draft_id[:8]}.")
            st.session_state["ts_active_draft_id"] = ""
            st.session_state["ts_active_draft_signature"] = ""
            st.session_state["context_timesheet_id"] = draft_id
        except APIError as e:
            st.error(str(e))
with add_col:
    if st.button("Add Entry to Draft", use_container_width=True):
        try:
            draft_id = _ensure_active_draft(
                api,
                signature=signature,
                project_id=project_id,
                period_start=period_start,
                period_end=period_end,
            )
            _add_entry(
                api,
                timesheet_id=draft_id,
                period_end=period_end,
                discipline=employee_discipline,
                hours=float(hours),
                billable=bool(billable),
                notes=st.session_state["ts_create_notes"],
            )
            st.success(f"Entry added to draft {draft_id[:8]}.")
        except APIError as e:
            st.error(str(e))

section("Speak to Create Entry", "Press once, speak, and AI will create the entry for the current draft.")
voice_notice = str(st.session_state.pop("ts_voice_apply_notice", "") or "").strip()
if voice_notice:
    st.success(voice_notice)
if hasattr(st, "audio_input"):
    speech_audio = st.audio_input(
        "Speak to create entry", key="ts_voice_single_button"
    )
    if speech_audio:
        audio_bytes = speech_audio.getvalue()
        audio_hash = hashlib.sha1(audio_bytes).hexdigest()
        if st.session_state.get("ts_voice_last_hash") != audio_hash:
            st.session_state["ts_voice_last_hash"] = audio_hash
            try:
                voice_resp = api.ai_voice_parse(
                    wav_bytes=audio_bytes,
                    week_start=str(period_start),
                    discipline_choices=voice_discipline_choices,
                    project_name=project_name,
                )
                transcript = str(voice_resp.get("transcript", "")).strip()
                st.session_state["ts_voice_transcript"] = transcript
                entries_raw = voice_resp.get("result", {}).get("entries", [])
                entries = _normalize_ai_entries(
                    entries_raw, period_end=period_end, discipline=employee_discipline
                )
                question = _missing_details_question(entries, transcript)
                if question:
                    st.session_state["ts_voice_followup_question"] = question
                    st.warning(question)
                else:
                    draft_id, applied = _apply_entries_to_active_draft(
                        api,
                        entries=entries,
                        signature=signature,
                        project_id=project_id,
                        period_start=period_start,
                        period_end=period_end,
                    )
                    st.success(
                        f"Added {applied} voice entr{'y' if applied == 1 else 'ies'} to draft {draft_id[:8]}."
                    )
                    st.session_state["ts_voice_followup_question"] = ""
                    st.session_state["ts_voice_apply_notice"] = (
                        f"Added {applied} voice entr{'y' if applied == 1 else 'ies'} to draft {draft_id[:8]}."
                    )
                    st.rerun()
            except APIError as e:
                st.error(str(e))
else:
    st.warning("This Streamlit version does not support audio_input.")

if st.session_state.get("ts_voice_transcript"):
    st.caption(f"Transcript: {st.session_state['ts_voice_transcript']}")

if st.session_state.get("ts_voice_followup_question"):
    followup = st.text_input("Follow-up details", key="ts_voice_followup_details")
    if st.button("Send follow-up"):
        if not followup.strip():
            st.warning("Provide follow-up details first.")
        else:
            combined = (
                f"{st.session_state.get('ts_voice_transcript', '')}\n"
                f"Follow-up: {followup.strip()}"
            )
            try:
                parsed = api.ai_parse_timesheet_text(
                    combined,
                    str(period_start),
                    voice_discipline_choices,
                    [{"project_id": project_id, "project_name": project_name}],
                )
                entries_raw = parsed.get("result", {}).get("entries", [])
                entries = _normalize_ai_entries(
                    entries_raw, period_end=period_end, discipline=employee_discipline
                )
                question = _missing_details_question(entries, combined)
                if question:
                    st.session_state["ts_voice_followup_question"] = question
                    st.warning(question)
                else:
                    draft_id, applied = _apply_entries_to_active_draft(
                        api,
                        entries=entries,
                        signature=signature,
                        project_id=project_id,
                        period_start=period_start,
                        period_end=period_end,
                    )
                    st.success(
                        f"Added {applied} follow-up entr{'y' if applied == 1 else 'ies'} to draft {draft_id[:8]}."
                    )
                    st.session_state["ts_voice_followup_question"] = ""
                    st.session_state["ts_voice_followup_details"] = ""
                    st.session_state["ts_voice_apply_notice"] = (
                        f"Added {applied} follow-up entr{'y' if applied == 1 else 'ies'} to draft {draft_id[:8]}."
                    )
                    st.rerun()
            except APIError as e:
                st.error(str(e))

section("Draft Entry Preview", "Latest entries currently saved on this draft timesheet.")
preview_draft_id = _get_active_draft(signature)
if not preview_draft_id:
    st.caption("Create or update a draft to see entry preview.")
else:
    try:
        preview_rows = api.list_time_entries(preview_draft_id)
        if not preview_rows:
            st.caption("No entries on this draft yet.")
        else:
            preview_data = [
                {
                    "Work Date": str(row.get("work_date") or ""),
                    "Discipline": str(row.get("discipline") or ""),
                    "Hours": float(row.get("hours") or 0.0),
                    "Billable": bool(row.get("billable")),
                    "Notes": str(row.get("notes") or ""),
                }
                for row in preview_rows
            ]
            st.dataframe(preview_data, use_container_width=True, hide_index=True)
    except APIError as e:
        st.error(str(e))

st.caption(f"Current user: {employee_name} ({employee_discipline})")
