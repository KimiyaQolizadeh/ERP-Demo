import os
from collections import Counter
from html import escape

import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme, section

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

STATUS_CARD_META = [
    {
        "key": "DRAFT",
        "label": "Draft",
        "foot": "Editable by owner",
        "icon": "edit_note",
        "variant": "draft",
    },
    {
        "key": "SUBMITTED",
        "label": "Submitted",
        "foot": "Waiting PM action",
        "icon": "hourglass_top",
        "variant": "submitted",
    },
    {
        "key": "APPROVED",
        "label": "Approved",
        "foot": "Invoice-ready candidates",
        "icon": "task_alt",
        "variant": "approved",
    },
    {
        "key": "REJECTED",
        "label": "Rejected",
        "foot": "Needs employee revision",
        "icon": "cancel",
        "variant": "rejected",
    },
]


def _inject_timesheets_ui_css() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/icon?family=Material+Icons+Outlined');
.pc-projects-header-anchor { display: none; }
div[data-testid="stVerticalBlock"]:has(.pc-projects-header-anchor) {
  position: sticky;
  top: 0;
  z-index: 44;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--pc-border);
  margin: 0 -1.05rem 0.9rem;
  padding: 0.12rem 1.05rem 0.52rem;
}
.pc-projects-header-left {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.pc-projects-kicker-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.pc-projects-kicker {
  color: #1d4ed8;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.pc-projects-beta {
  background: #dbeafe;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
  border-radius: 999px;
  padding: 0.1rem 0.48rem;
  font-size: 0.66rem;
  font-weight: 800;
}
.pc-projects-title-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}
.pc-projects-title {
  margin: 0;
  color: #0f172a;
  font-size: 2.05rem;
  font-weight: 800;
  line-height: 1;
}
.pc-projects-badge {
  border-radius: 999px;
  border: 1px solid #d0d7e2;
  background: #eef2f7;
  color: #6b7280;
  font-size: 0.76rem;
  font-weight: 700;
  padding: 0.15rem 0.54rem;
}
.pc-timesheets-meta {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.2rem;
  min-height: 2.55rem;
}
.pc-timesheets-meta-title {
  color: #334155;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 700;
}
.pc-timesheets-meta-value {
  color: #0f172a;
  font-size: 0.9rem;
  font-weight: 700;
}
.pc-projects-header-cta [data-testid="stButton"] button {
  margin-top: 0.05rem;
  height: 2.55rem;
  border-radius: 10px;
  background: #2563eb;
  border: 1px solid #1d4ed8;
  color: #ffffff;
  font-size: 0.93rem;
  font-weight: 700;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.2);
}
.pc-projects-header-cta [data-testid="stButton"] button:hover {
  background: #1d4ed8;
  border-color: #1e40af;
}
.ts-registry-shell-anchor { display: none; }
div[data-testid="stVerticalBlock"]:has(.ts-registry-shell-anchor) {
  background: #ffffff;
  border: 1px solid var(--pc-border);
  border-radius: 16px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
  overflow: hidden;
  padding-bottom: 0.16rem;
}
.ts-registry-head {
  padding: 1rem 1.2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--pc-border);
}
.ts-registry-head-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  color: #0f172a;
}
.ts-registry-head-sub {
  margin-top: 0.2rem;
  font-size: 0.86rem;
  color: #64748b;
}
.ts-row-anchor,
.ts-headrow-anchor,
.ts-footer-anchor { display: none; }
div[data-testid="stVerticalBlock"]:has(.ts-headrow-anchor) {
  background: #f8fafc;
  border-bottom: 1px solid var(--pc-border);
  padding: 1.2rem 0.95rem;
}
div[data-testid="stVerticalBlock"]:has(.ts-row-anchor) {
  border-bottom: 1px solid var(--pc-border);
  padding: 0rem 0.92rem;
  gap: 0.2rem;
}
div[data-testid="stVerticalBlock"]:has(.ts-footer-anchor) {
  background: #f8fafc;
  padding: 0.55rem 0.95rem 0.18rem;
}
div[data-testid="stElementContainer"]:has(.ts-row-anchor),
div[data-testid="stElementContainer"]:has(.ts-headrow-anchor),
div[data-testid="stElementContainer"]:has(.ts-footer-anchor) { display: none; }
.ts-col-head {
  font-size: 0.72rem;
  text-transform: uppercase;
  line-height: 1;
  letter-spacing: 0.08em;
  color: #64748b;
  font-weight: 700;
}
.ts-col-head-center { text-align: center; }
.ts-col-head-right { text-align: right; }
.ts-cell-title {
  font-size: 0.95rem;
  font-weight: 800;
  color: #0f172a;
}
.ts-cell-sub {
  margin-top: 0.14rem;
  color: #64748b;
  font-size: 0.74rem;
  font-weight: 500;
}
.ts-hours {
  font-size: 0.98rem;
  font-weight: 800;
  color: #0f172a;
  text-align: right;
}
.ts-hours-sub {
  margin-top: 0.12rem;
  color: #94a3b8;
  font-size: 0.7rem;
  text-align: right;
}
.ts-status-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.2rem 0.55rem;
  font-size: 0.73rem;
  font-weight: 700;
}
.ts-status-draft { background: #fef3c7; color: #92400e; }
.ts-status-submitted { background: #dbeafe; color: #1d4ed8; }
.ts-status-approved { background: #dcfce7; color: #166534; }
.ts-status-rejected { background: #fee2e2; color: #991b1b; }
.ts-status-default { background: #e2e8f0; color: #334155; }
.ts-actions-wrap [data-testid="stButton"] button {
  height: 1.88rem;
  border-radius: 8px;
  border: 1px solid #dbe2ec;
  background: #ffffff;
  color: #94a3b8;
  font-size: 0.95rem;
  padding: 0;
  min-width: 0;
}
.ts-actions-wrap [data-testid="stButton"] button:hover {
  color: #2563eb;
  border-color: #93c5fd;
  background: #eff6ff;
}
.ts-count {
  font-size: 0.74rem;
  color: #64748b;
}
.ts-footer-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.8rem;
}
.ts-pages {
  display: inline-flex;
  gap: 0.3rem;
  align-items: center;
}
.ts-pages [data-testid="stButton"] button {
  height: 1.8rem;
  border-radius: 7px;
  border: 1px solid #dbe2ec;
  background: #ffffff;
  color: #64748b;
  font-size: 0.72rem;
  padding: 0.18rem 0.46rem;
}
.ts-pages [data-testid="stButton"] button:hover {
  border-color: #93c5fd;
  color: #2563eb;
}
.ts-pages [data-testid="stButton"] button:disabled {
  color: #cbd5e1;
  border-color: #e2e8f0;
  background: #f8fafc;
}
div.st-key-ts_show_all_statuses_text [data-testid="stButton"] button {
  border: none !important;
  background: transparent !important;
  color: #2563eb !important;
  text-decoration: underline;
  box-shadow: none !important;
  padding: 0 !important;
  min-height: 0 !important;
  height: auto !important;
}
div.st-key-ts_show_all_statuses_text [data-testid="stButton"] button:hover {
  color: #1d4ed8 !important;
}
div.st-key-ts_show_all_statuses_text [data-testid="stButton"] button:focus {
  box-shadow: none !important;
}

@media (max-width: 900px) {
  div[data-testid="stVerticalBlock"]:has(.pc-projects-header-anchor) {
    margin-left: -0.55rem;
    margin-right: -0.55rem;
    padding-left: 0.55rem;
    padding-right: 0.55rem;
  }
  .pc-projects-title {
    font-size: 1.72rem;
  }
}
</style>
""",
        unsafe_allow_html=True,
    )


def _status_filter_from_query() -> str:
    selected = _get_query_param("ts_status", "ALL").upper()
    valid = {meta["key"] for meta in STATUS_CARD_META} | {"ALL"}
    return selected if selected in valid else "ALL"


def _get_query_param(name: str, default: str) -> str:
    try:
        raw = st.query_params.get(name, default)
    except Exception:
        raw = st.experimental_get_query_params().get(name, [default])
    if isinstance(raw, list):
        raw = raw[0] if raw else default
    return str(raw or default)


def _set_query_param(name: str, value: str) -> None:
    try:
        st.query_params[name] = value
        return
    except Exception:
        params = st.experimental_get_query_params()
    params[name] = [value]
    st.experimental_set_query_params(**params)


def _inject_status_card_button_css(selected_status: str) -> None:
    wrapper_selectors = [
        f"div.st-key-ts_card_filter_{meta['key']}" for meta in STATUS_CARD_META
    ]

    def _group(suffix: str = "") -> str:
        return ",\n".join([f"{selector}{suffix}" for selector in wrapper_selectors])

    variant_styles = {
        "DRAFT": {
            "accent": "#f59e0b",
            "icon_bg": "#fff3e6",
            "icon_fg": "#d97706",
            "foot_fg": "#b45309",
            "icon": "edit_note",
        },
        "SUBMITTED": {
            "accent": "#2a6be8",
            "icon_bg": "#e9f1ff",
            "icon_fg": "#245dd8",
            "foot_fg": "#3e6bb7",
            "icon": "hourglass_top",
        },
        "APPROVED": {
            "accent": "#12b981",
            "icon_bg": "#e7fbef",
            "icon_fg": "#0e9f6e",
            "foot_fg": "#0f9a61",
            "icon": "task_alt",
        },
        "REJECTED": {
            "accent": "#f43f5e",
            "icon_bg": "#ffe9ee",
            "icon_fg": "#e11d48",
            "foot_fg": "#be123c",
            "icon": "cancel",
        },
    }
    variant_rules = []
    for key, style in variant_styles.items():
        variant_rules.append(
            f"""
div.st-key-ts_card_filter_{key} {{
  --ts-accent: {style["accent"]};
  --ts-icon-bg: {style["icon_bg"]};
  --ts-icon-fg: {style["icon_fg"]};
  --ts-foot-fg: {style["foot_fg"]};
}}
div.st-key-ts_card_filter_{key} [data-testid="stBaseButton-secondary"]::before {{
  content: "{style["icon"]}";
}}
"""
        )

    active_rule = ""
    if selected_status in variant_styles:
        active_rule = f"""
div.st-key-ts_card_filter_{selected_status} [data-testid="stBaseButton-secondary"] {{
  border-color: var(--ts-accent) !important;
  box-shadow: 0 11px 24px rgba(30, 64, 175, 0.16) !important;
}}
"""

    css = f"""
<style>
{_group()} {{
  min-height: 154px;
}}
{_group(' [data-testid="stButton"]')} {{
  height: 100%;
}}
{_group(' [data-testid="stBaseButton-secondary"]')} {{
  position: relative;
  width: 100%;
  height: 154px;
  border-radius: 16px !important;
  border: 1px solid var(--pc-border) !important;
  background: var(--pc-surface) !important;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05) !important;
  padding: 0.9rem 1rem 1.05rem !important;
  text-align: left !important;
  align-items: flex-start !important;
  justify-content: flex-start !important;
  overflow: hidden;
  transition: all 0.15s ease;
}}
{_group(' [data-testid="stBaseButton-secondary"]::after')} {{
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 4px;
  background: var(--ts-accent);
}}
{_group(' [data-testid="stBaseButton-secondary"]::before')} {{
  font-family: "Material Icons Outlined";
  position: absolute;
  top: 0.8rem;
  right: 0.9rem;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.45rem;
  line-height: 1;
  background: var(--ts-icon-bg);
  color: var(--ts-icon-fg);
}}
{_group(' [data-testid="stBaseButton-secondary"]:hover')} {{
  border-color: #93c5fd !important;
  box-shadow: 0 9px 22px rgba(37, 99, 235, 0.14) !important;
  transform: translateY(-1px);
}}
{_group(' [data-testid="stBaseButton-secondary"] > div')} {{
  width: 100%;
  align-items: flex-start !important;
}}
{_group(' [data-testid="stMarkdownContainer"]')} {{
  width: 100%;
  padding-right: 3.25rem;
}}
{_group(' [data-testid="stMarkdownContainer"] p')} {{
  margin: 0 !important;
  text-align: left !important;
}}
{_group(' [data-testid="stMarkdownContainer"] p:nth-of-type(1)')} {{
  color: #476181 !important;
  font-size: 0.86rem !important;
  font-weight: 700 !important;
}}
{_group(' [data-testid="stMarkdownContainer"] p:nth-of-type(2)')} {{
  margin-top: 0.35rem !important;
  color: #0b2240 !important;
  font-size: 2.15rem !important;
  font-weight: 900 !important;
  line-height: 1 !important;
}}
{_group(' [data-testid="stMarkdownContainer"] p:nth-of-type(3)')} {{
  margin-top: 0.42rem !important;
  color: var(--ts-foot-fg) !important;
  font-size: 0.82rem !important;
  font-weight: 600 !important;
}}
{''.join(variant_rules)}
{active_rule}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)


def _render_status_cards(status_counts: Counter, selected_status: str) -> None:
    _inject_status_card_button_css(selected_status)
    cols = st.columns(len(STATUS_CARD_META), gap="small")
    for col, meta in zip(cols, STATUS_CARD_META):
        key = meta["key"]
        with col:
            if st.button(
                f"**{meta['label']}**\n\n{int(status_counts.get(key, 0))}\n\n{meta['foot']}",
                key=f"ts_card_filter_{key}",
                use_container_width=True,
            ):
                _set_query_param("ts_status", key)
                st.rerun()


def _timesheet_status_chip_class(status: str) -> str:
    status_key = str(status or "").upper()
    mapping = {
        "DRAFT": "ts-status-draft",
        "SUBMITTED": "ts-status-submitted",
        "APPROVED": "ts-status-approved",
        "REJECTED": "ts-status-rejected",
    }
    return mapping.get(status_key, "ts-status-default")


def _open_timesheet_page(path: str, row: dict) -> None:
    st.session_state["context_timesheet_id"] = str(row["id"])
    st.session_state["context_project_id"] = row["project_id"]
    try:
        st.switch_page(path)
    except Exception:
        st.caption(f"Open `{path}` from the sidebar.")


def _render_timesheets_registry(
    rows: list[dict],
    project_name_map: dict[str, str],
    employee_label: str,
    api_client: APIClient,
    status_scope: str,
) -> None:
    if not rows:
        st.info("No timesheets match the selected status.")
        return

    sorted_rows = sorted(
        rows,
        key=lambda r: (str(r.get("period_end", "")), str(r.get("id", ""))),
        reverse=True,
    )
    page_size = 6
    total_rows = len(sorted_rows)
    page_count = max(1, (total_rows + page_size - 1) // page_size)
    scope_key = str(status_scope or "ALL").lower()
    page_state_key = f"timesheets_table_page_{scope_key}"
    current_page = int(st.session_state.get(page_state_key, 1))
    current_page = max(1, min(current_page, page_count))
    st.session_state[page_state_key] = current_page
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)
    visible_rows = sorted_rows[start_idx:end_idx]

    with st.container():
        st.markdown(
            "<div class='ts-registry-shell-anchor'></div>", unsafe_allow_html=True
        )
        st.markdown(
            """
<div class="ts-registry-head">
  <div>
    <h3 class="ts-registry-head-title">My Timesheets Registry</h3>
    <div class="ts-registry-head-sub">Projects-style layout with workflow actions and status chips.</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        with st.container():
            st.markdown("<div class='ts-headrow-anchor'></div>", unsafe_allow_html=True)
            hdr = st.columns(
                [2.0, 1.8, 1.2, 1.0, 1.5, 1.2], vertical_alignment="center"
            )
            with hdr[0]:
                st.markdown(
                    "<div class='ts-col-head'>Timesheet</div>", unsafe_allow_html=True
                )
            with hdr[1]:
                st.markdown(
                    "<div class='ts-col-head'>Project</div>", unsafe_allow_html=True
                )
            with hdr[2]:
                st.markdown(
                    "<div class='ts-col-head ts-col-head-right'>Hours</div>",
                    unsafe_allow_html=True,
                )
            with hdr[3]:
                st.markdown(
                    "<div class='ts-col-head ts-col-head-center'>Status</div>",
                    unsafe_allow_html=True,
                )
            with hdr[4]:
                st.markdown(
                    "<div class='ts-col-head'>Notes</div>", unsafe_allow_html=True
                )
            with hdr[5]:
                st.markdown(
                    "<div class='ts-col-head ts-col-head-center'>Actions</div>",
                    unsafe_allow_html=True,
                )

        for row in visible_rows:
            status = str(row.get("status", "")).upper()
            project_name = project_name_map.get(row["project_id"], "Unknown project")
            hours = float(row.get("total_hours", 0.0))
            rejection_note = row.get("rejection_reason") or "No rejection note"
            row_id = str(row["id"])
            period = f"{row.get('period_start')} -> {row.get('period_end')}"
            owner = row.get("employee_name") or employee_label

            with st.container():
                st.markdown("<div class='ts-row-anchor'></div>", unsafe_allow_html=True)
                cols = st.columns(
                    [2.0, 1.8, 1.2, 1.0, 1.5, 1.2], vertical_alignment="center"
                )
                with cols[0]:
                    st.markdown(
                        f"""
<div class='ts-cell-title'>TS-{escape(row_id[:8])}</div>
<div class='ts-cell-sub'>{escape(owner)}</div>
""",
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    st.markdown(
                        f"""
<div class='ts-cell-title'>{escape(project_name)}</div>
<div class='ts-cell-sub'>{escape(period)}</div>
""",
                        unsafe_allow_html=True,
                    )
                with cols[2]:
                    st.markdown(
                        f"""
<div class='ts-hours'>{hours:.2f} h</div>
<div class='ts-hours-sub'>Deterministic sum</div>
""",
                        unsafe_allow_html=True,
                    )
                with cols[3]:
                    st.markdown(
                        f"<div style='text-align:center;'><span class='ts-status-chip {_timesheet_status_chip_class(status)}'>{escape(status.title())}</span></div>",
                        unsafe_allow_html=True,
                    )
                with cols[4]:
                    note_text = (
                        rejection_note if status == "REJECTED" else "Workflow healthy"
                    )
                    st.markdown(
                        f"""
<div class='ts-cell-title'>{escape(note_text[:72])}</div>
<div class='ts-cell-sub'>{escape('PM rejection note' if status == 'REJECTED' else 'No blocker')}</div>
""",
                        unsafe_allow_html=True,
                    )
                with cols[5]:
                    st.markdown("<div class='ts-actions-wrap'>", unsafe_allow_html=True)
                    action_specs: list[tuple[str, str, str]] = []
                    if status == "DRAFT":
                        action_specs.append(("submit", "⤴", "Submit"))
                    action_specs.append(("view", "👁", "View details"))
                    if status == "REJECTED":
                        action_specs.append(("edit", "✎", "Edit rejected"))

                    action_cols = st.columns(len(action_specs), gap="small")
                    for action_col, (action, icon, help_text) in zip(
                        action_cols, action_specs
                    ):
                        with action_col:
                            if st.button(
                                icon,
                                key=f"ts_{action}_{row_id}",
                                help=help_text,
                                use_container_width=True,
                            ):
                                if action == "submit":
                                    try:
                                        api_client.submit_timesheet(row_id)
                                        st.success(f"Timesheet {row_id[:8]} submitted.")
                                        st.rerun()
                                    except APIError as ex:
                                        st.error(str(ex))
                                elif action == "view":
                                    _open_timesheet_page(
                                        "pages/10_Timesheet_Details.py", row
                                    )
                                elif action == "edit":
                                    _open_timesheet_page(
                                        "pages/11_Timesheet_Edit.py", row
                                    )
                    st.markdown("</div>", unsafe_allow_html=True)

        with st.container():
            st.markdown("<div class='ts-footer-anchor'></div>", unsafe_allow_html=True)
            left, right = st.columns([2.8, 2.2], vertical_alignment="center")
            with left:
                st.markdown(
                    f"<div class='ts-count'>Showing {start_idx + 1} to {end_idx} of {total_rows} rows</div>",
                    unsafe_allow_html=True,
                )
            with right:
                st.markdown("<div class='ts-pages'>", unsafe_allow_html=True)
                page_targets = sorted(
                    {1, page_count, current_page - 1, current_page, current_page + 1}
                )
                page_targets = [p for p in page_targets if 1 <= p <= page_count]
                button_specs = [
                    ("Prev", "prev", max(1, current_page - 1), current_page <= 1)
                ]
                button_specs += [
                    (str(p), f"page_{p}", p, p == current_page) for p in page_targets
                ]
                button_specs += [
                    (
                        "Next",
                        "next",
                        min(page_count, current_page + 1),
                        current_page >= page_count,
                    )
                ]
                nav_cols = st.columns(len(button_specs), gap="small")
                for idx, (label, key_token, target_page, disabled) in enumerate(
                    button_specs
                ):
                    with nav_cols[idx]:
                        if st.button(
                            label,
                            key=f"ts_nav_{scope_key}_{key_token}",
                            disabled=disabled,
                            use_container_width=True,
                        ):
                            st.session_state[page_state_key] = target_page
                            st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

apply_theme()
_inject_timesheets_ui_css()

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
employee_name = (st.session_state.get("user_label") or "").split(" (")[
    0
] or "Current user"

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

ai_caption = "AI status unavailable."
env_paths_checked: list[str] = []
try:
    ai_status = api.ai_status()
    if ai_status.get("api_key_configured"):
        ai_caption = f"AI connected ({ai_status.get('model')})."
    else:
        ai_caption = "AI key not detected. Rules fallback will still work."
        env_paths_checked = ai_status.get("env_paths_checked", [])
except APIError:
    pass

try:
    projects = api.list_projects()
    ts_rows = api.list_timesheets()
except APIError as e:
    st.error(str(e))
    st.stop()

if not projects:
    st.warning("No projects found. Run seed first.")
    st.stop()
project_name_by_id = {p["id"]: p["project_name"] for p in projects}
selected_status = _status_filter_from_query()
status_counts = Counter(str(row.get("status", "")).upper() for row in ts_rows)

with st.container():
    st.markdown("<div class='pc-projects-header-anchor'></div>", unsafe_allow_html=True)
    head_left, head_meta, head_cta = st.columns([1.55, 1.0, 0.8])
    with head_left:
        st.markdown(
            """
<div class="pc-projects-header-left">
  <div class="pc-projects-kicker-row">
    <span class="pc-projects-kicker">Project Control Copilot</span>
    <span class="pc-projects-beta">BETA</span>
  </div>
  <div class="pc-projects-title-row">
    <h1 class="pc-projects-title">Timesheets</h1>
    <span class="pc-projects-badge">AI-assisted</span>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    with head_meta:
        filter_label = (
            "All statuses"
            if selected_status == "ALL"
            else selected_status.replace("_", " ").title()
        )
        st.markdown(
            f"""
<div class="pc-timesheets-meta">
  <div class="pc-timesheets-meta-title">View</div>
  <div class="pc-timesheets-meta-value">{escape(filter_label)} • {escape(employee_name)}</div>
  <div class="pc-timesheets-meta-value" style="font-size:0.8rem;font-weight:600;color:#64748b;">{escape(ai_caption)}</div>
</div>
""",
            unsafe_allow_html=True,
        )
    with head_cta:
        st.markdown("<div class='pc-projects-header-cta'>", unsafe_allow_html=True)
        if st.button("+ Create Timesheet", use_container_width=True):
            try:
                st.switch_page("pages/12_Create_Timesheet.py")
            except Exception:
                st.caption("Open `pages/12_Create_Timesheet.py` from the sidebar.")
        st.markdown("</div>", unsafe_allow_html=True)

if env_paths_checked:
    with st.expander("Where backend looked for .env", expanded=False):
        st.json(env_paths_checked)

_render_status_cards(status_counts, selected_status)
show_all_cols = st.columns([5, 1])
with show_all_cols[1]:
    if st.button("Show all statuses", key="ts_show_all_statuses_text"):
        _set_query_param("ts_status", "ALL")
        st.rerun()

filtered_ts_rows = (
    [row for row in ts_rows if str(row.get("status", "")).upper() == selected_status]
    if selected_status != "ALL"
    else ts_rows
)

section(
    "My Timesheets",
    "Review periods, progress, and notes. Card selection above filters this table.",
)
_render_timesheets_registry(
    filtered_ts_rows,
    project_name_by_id,
    employee_name,
    api,
    selected_status,
)
