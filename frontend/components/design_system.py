from __future__ import annotations

from html import escape
from typing import Iterable

import streamlit as st


_PAGE_LINKS: list[tuple[str, str]] = [
    ("Demo Config Dashboard", "streamlit_app.py"),
    ("Projects", "pages/0_Projects.py"),
    ("Timesheets", "pages/1_Timesheets.py"),
    ("Approvals", "pages/2_Approvals.py"),
    ("Invoicing", "pages/3_Invoicing.py"),
    ("Chat Assistant", "pages/5_Chat_Assistant.py"),
    ("Reports", "pages/10_Reports.py"),
]

_ROLE_VISIBLE_PAGES: dict[str, set[str]] = {
    "EMPLOYEE": {"Demo Config Dashboard", "Projects", "Timesheets"},
    "PM": {
        "Demo Config Dashboard",
        "Projects",
        "Timesheets",
        "Approvals",
        "Invoicing",
        "Chat Assistant",
        "Reports",
    },
    "FINANCE": {
        "Demo Config Dashboard",
        "Projects",
        "Timesheets",
        "Invoicing",
        "Chat Assistant",
        "Reports",
    },
    "ADMIN": {
        "Demo Config Dashboard",
        "Projects",
        "Timesheets",
        "Approvals",
        "Invoicing",
        "Chat Assistant",
        "Reports",
    },
}


def _visible_pages_for_role(role: str) -> set[str]:
    role_key = str(role or "").upper()
    return _ROLE_VISIBLE_PAGES.get(role_key, {"Demo Config Dashboard", "Projects", "Timesheets"})


def _render_sidebar_navigation() -> None:
    role = str(st.session_state.get("user_role", "") or "").upper()
    visible_pages = _visible_pages_for_role(role)
    st.sidebar.divider()
    st.sidebar.subheader("Navigation")
    for label, path in _PAGE_LINKS:
        if label in visible_pages:
            st.sidebar.page_link(path, label=label, use_container_width=True)


def apply_theme(
    page_title: str | None = None, subtitle: str | None = None, badge: str | None = None
) -> None:
    style_block = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
  --pc-primary: #137fec;
  --pc-primary-dark: #0b63be;
  --pc-bg: #f6f7f8;
  --pc-surface: #ffffff;
  --pc-border: #e2e8f0;
  --pc-text: #0f172a;
  --pc-muted: #64748b;
  --pc-success: #16a34a;
  --pc-warn: #f59e0b;
  --pc-danger: #ef4444;
  --pc-shell-start: #d7e9ff;
  --pc-shell-end: #f6f7f8;
  --pc-sidebar-start: #f9fbff;
  --pc-sidebar-end: #f4f7fb;
}

html,
body,
.stApp,
[data-testid="stAppViewContainer"] {
  color-scheme: light !important;
}

.stApp {
  font-family: "Inter", sans-serif;
  color: var(--pc-text);
  background: radial-gradient(1600px 600px at 50% -260px, var(--pc-shell-start) 0%, var(--pc-shell-end) 45%);
}

[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
#MainMenu {
  display: none !important;
}

[data-testid="stHeader"] {
  background: transparent !important;
}

[data-testid="stAppViewContainer"] > .main {
  padding-top: 0 !important;
}

[data-testid="stSidebar"] {
  border-right: 1px solid var(--pc-border);
}

[data-testid="stSidebar"] > div:first-child {
  background: linear-gradient(180deg, var(--pc-sidebar-start) 0%, var(--pc-sidebar-end) 100%);
}

[data-testid="block-container"],
.block-container {
  padding-top: 0 !important;
  padding-bottom: 2rem;
}

.pc-page-head {
  position: sticky;
  top: 0;
  z-index: 40;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--pc-border);
  padding: 0.12rem 1.05rem 0.52rem;
  margin: 0 -1.05rem 0.95rem;
  min-height: 56px;
  display: flex;
  align-items: center;
}

.pc-page-head-left {
  display: flex;
  flex-direction: column;
  gap: 0.08rem;
}

.pc-page-kicker-row {
  display: flex;
  align-items: center;
  gap: 0.46rem;
}

.pc-page-kicker {
  color: #1d4ed8;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.pc-page-beta {
  background: #dbeafe;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
  border-radius: 999px;
  padding: 0.1rem 0.48rem;
  font-size: 0.66rem;
  font-weight: 800;
}

.pc-page-title-row {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.pc-page-title {
  color: var(--pc-text);
  margin: 0;
  font-size: 2.05rem;
  font-weight: 800;
  line-height: 1;
}

.pc-page-badge {
  border-radius: 999px;
  border: 1px solid #d0d7e2;
  background: #eef2f7;
  color: #6b7280;
  font-size: 0.76rem;
  font-weight: 700;
  padding: 0.14rem 0.54rem;
}

.pc-page-sub {
  color: var(--pc-muted);
  margin-top: 0.18rem;
  font-size: 0.88rem;
}

@media (max-width: 900px) {
  .pc-page-head {
    margin-left: -0.55rem;
    margin-right: -0.55rem;
    padding-left: 0.7rem;
    padding-right: 0.7rem;
  }
  .pc-page-title {
    font-size: 1.66rem;
  }
}

.pc-chip {
  display: inline-block;
  border-radius: 999px;
  padding: 0.22rem 0.6rem;
  font-size: 0.75rem;
  font-weight: 700;
  border: 1px solid transparent;
}

.pc-chip-primary { background: #e0f0ff; color: var(--pc-primary-dark); border-color: #bfdfff; }
.pc-chip-success { background: #dcfce7; color: #166534; border-color: #bbf7d0; }
.pc-chip-warn { background: #fef3c7; color: #92400e; border-color: #fde68a; }
.pc-chip-danger { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
.pc-chip-neutral { background: #f1f5f9; color: #334155; border-color: #e2e8f0; }

.pc-kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.8rem;
  margin: 0.2rem 0 1rem;
}

.pc-kpi-card {
  background: var(--pc-surface);
  border: 1px solid var(--pc-border);
  border-radius: 14px;
  padding: 0.9rem 1rem;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.03);
}

.pc-kpi-label {
  color: var(--pc-muted);
  font-size: 0.78rem;
  font-weight: 600;
  margin: 0;
}

.pc-kpi-value {
  color: var(--pc-text);
  font-size: 1.45rem;
  font-weight: 800;
  margin: 0.24rem 0 0.15rem;
}

.pc-kpi-foot {
  font-size: 0.74rem;
  font-weight: 600;
}

.pc-foot-success { color: var(--pc-success); }
.pc-foot-warn { color: #b45309; }
.pc-foot-danger { color: #b91c1c; }
.pc-foot-neutral { color: var(--pc-muted); }

.pc-section {
  margin-top: 0.8rem;
  margin-bottom: 0.2rem;
}

.pc-section h3 {
  margin: 0;
  color: var(--pc-text);
  font-size: 1.1rem;
  font-weight: 800;
}

.pc-section p {
  margin: 0.16rem 0 0;
  color: var(--pc-muted);
  font-size: 0.86rem;
}

.pc-progress-block { margin: 0.56rem 0 0.5rem; }
.pc-progress-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  margin-bottom: 0.28rem;
}
.pc-progress-label { color: var(--pc-text); font-size: 0.85rem; font-weight: 700; }
.pc-progress-detail { color: var(--pc-muted); font-size: 0.78rem; }
.pc-progress-track {
  height: 12px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}
.pc-progress-fill { height: 100%; border-radius: 999px; }
.pc-fill-primary { background: linear-gradient(90deg, #137fec 0%, #3998f9 100%); }
.pc-fill-success { background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%); }
.pc-fill-warn { background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%); }
.pc-fill-danger { background: linear-gradient(90deg, #ef4444 0%, #dc2626 100%); }

[data-testid="stDataFrame"] {
  border: 1px solid var(--pc-border);
  border-radius: 12px;
}

[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stCaptionContainer"] {
  color: var(--pc-text);
}

[data-testid="stButton"] button {
  border-radius: 10px;
  border: 1px solid var(--pc-border);
  font-weight: 600;
}

[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stDateInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stFileUploader"] section {
  color: var(--pc-text) !important;
  background: #ffffff !important;
  border: 1px solid var(--pc-border) !important;
  border-radius: 10px !important;
}

.pc-page-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 0.75rem;
}

.pc-page-card {
  background: var(--pc-surface);
  border: 1px solid var(--pc-border);
  border-radius: 12px;
  padding: 0.8rem 0.9rem;
}

.pc-page-card-title {
  font-weight: 800;
  color: var(--pc-text);
}

.pc-page-card-sub {
  font-size: 0.85rem;
  color: var(--pc-muted);
  margin-top: 0.2rem;
}
</style>
"""
    st.markdown(style_block, unsafe_allow_html=True)
    _render_sidebar_navigation()
    if page_title:
        header(page_title, subtitle=subtitle, badge=badge)


def header(title: str, subtitle: str | None = None, badge: str | None = None) -> None:
    subtitle_html = (
        f"<div class='pc-page-sub'>{escape(subtitle)}</div>" if subtitle else ""
    )
    badge_html = f"<span class='pc-page-badge'>{escape(badge)}</span>" if badge else ""
    st.markdown(
        f"""
<div class="pc-page-head">
  <div class="pc-page-head-left">
    <div class="pc-page-kicker-row">
      <span class="pc-page-kicker">Project Control Copilot</span>
      <span class="pc-page-beta">BETA</span>
    </div>
    <div class="pc-page-title-row">
      <div class="pc-page-title">{escape(title)}</div>
      {badge_html}
    </div>
    {subtitle_html}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str | None = None) -> None:
    subtitle_html = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f"""
<div class="pc-section">
  <h3>{escape(title)}</h3>
  {subtitle_html}
</div>
""",
        unsafe_allow_html=True,
    )


def kpi_strip(items: Iterable[dict]) -> None:
    cards = []
    for item in items:
        label = escape(str(item.get("label", "")))
        value = escape(str(item.get("value", "")))
        foot = escape(str(item.get("foot", "")))
        tone = str(item.get("tone", "neutral")).lower()
        tone_class = tone if tone in {"success", "warn", "danger"} else "neutral"
        cards.append(
            f"""
<div class="pc-kpi-card">
  <p class="pc-kpi-label">{label}</p>
  <p class="pc-kpi-value">{value}</p>
  <div class="pc-kpi-foot pc-foot-{tone_class}">{foot}</div>
</div>
"""
        )
    st.markdown(
        f"<div class='pc-kpi-grid'>{''.join(cards)}</div>", unsafe_allow_html=True
    )


def progress_bar(
    label: str, percent: float, detail: str = "", tone: str = "primary"
) -> None:
    safe_tone = tone if tone in {"primary", "success", "warn", "danger"} else "primary"
    clipped = max(0.0, min(100.0, float(percent)))
    st.markdown(
        f"""
<div class="pc-progress-block">
  <div class="pc-progress-top">
    <div class="pc-progress-label">{escape(label)}</div>
    <div class="pc-progress-detail">{escape(detail)}</div>
  </div>
  <div class="pc-progress-track">
    <div class="pc-progress-fill pc-fill-{safe_tone}" style="width:{clipped:.1f}%"></div>
  </div>
  <div class="pc-progress-detail" style="margin-top:0.22rem;">{clipped:.1f}%</div>
</div>
""",
        unsafe_allow_html=True,
    )


def chip(text: str, tone: str = "neutral") -> str:
    safe_tone = (
        tone
        if tone in {"primary", "success", "warn", "danger", "neutral"}
        else "neutral"
    )
    return f"<span class='pc-chip pc-chip-{safe_tone}'>{escape(text)}</span>"
