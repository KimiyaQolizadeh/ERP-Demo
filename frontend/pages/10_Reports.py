from datetime import date, timedelta

import pandas as pd
import streamlit as st

from client.api import APIClient, APIError
from components.design_system import apply_theme, kpi_strip, progress_bar, section
from components.reports_utils import (
    base_url,
    fallback_ai,
    inject_shared_css,
    load_health,
    load_portfolio_health,
    load_projects,
    money,
    pct,
    risk_chip,
    safe_float,
)

DEFAULT_BUCKET_DAYS = 14
DEFAULT_LOOKBACK_BUCKETS = 12


def _clip(v: float) -> float:
    return max(0.0, min(100.0, float(v)))


def _tone(v: float) -> str:
    if v < 35:
        return "success"
    if v < 70:
        return "warn"
    return "danger"


def _inject_css() -> None:
    st.markdown(
        """
<style>
[data-testid="stButton"] button[kind="primary"] {
  background: #dc2626 !important;
  border-color: #b91c1c !important;
  color: #ffffff !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def _default_range() -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=365)
    return start.isoformat(), end.isoformat()


def _mode_picker() -> str:
    if "reports_mode_initialized" not in st.session_state:
        st.session_state["reports_mode"] = "overview"
        st.session_state["reports_mode_initialized"] = True
    if st.session_state.get("reports_mode") not in {"overview", "forecast", "utilization", "profit"}:
        st.session_state["reports_mode"] = "overview"
    mode = st.session_state["reports_mode"]
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Overview", key="rp_mode_overview", use_container_width=True, type="primary" if mode == "overview" else "secondary"):
        st.session_state["reports_mode"] = "overview"
        st.rerun()
    if c2.button("Forecast To Completion", key="rp_mode_forecast", use_container_width=True, type="primary" if mode == "forecast" else "secondary"):
        st.session_state["reports_mode"] = "forecast"
        st.rerun()
    if c3.button("Employee Utilization", key="rp_mode_util", use_container_width=True, type="primary" if mode == "utilization" else "secondary"):
        st.session_state["reports_mode"] = "utilization"
        st.rerun()
    if c4.button("Profit Estimate", key="rp_mode_profit", use_container_width=True, type="primary" if mode == "profit" else "secondary"):
        st.session_state["reports_mode"] = "profit"
        st.rerun()
    return st.session_state["reports_mode"]


def _points(health: dict) -> list[tuple[date, float]]:
    rows = []
    for name in ("actual", "forecast"):
        for p in (health.get("series", {}).get(name, []) or []):
            d = p.get("date")
            v = safe_float(p.get("cumulative_cost"))
            if d and v is not None:
                rows.append((date.fromisoformat(str(d)), float(v)))
    by_day = {}
    for d, v in rows:
        by_day[d] = v
    return sorted(by_day.items(), key=lambda x: x[0])


def _budget_reach_date(health: dict) -> str | None:
    native = health.get("forecast_budget_exceed_date")
    if native:
        return str(native)
    budget = safe_float(health.get("budget"))
    if budget is None or budget <= 0:
        return None
    pts = _points(health)
    if not pts:
        return None
    prev_d, prev_v = pts[0]
    if prev_v >= budget:
        return prev_d.isoformat()
    for curr_d, curr_v in pts[1:]:
        if curr_v >= budget:
            if curr_v == prev_v:
                return curr_d.isoformat()
            ratio = (budget - prev_v) / (curr_v - prev_v)
            days = max((curr_d - prev_d).days, 0)
            return (prev_d + timedelta(days=int(round(days * ratio)))).isoformat()
        prev_d, prev_v = curr_d, curr_v
    deltas = [pts[i][1] - pts[i - 1][1] for i in range(1, len(pts)) if pts[i][1] - pts[i - 1][1] > 0]
    if not deltas:
        return None
    inc = sum(deltas[-4:]) / min(len(deltas), 4)
    last_d, last_v = pts[-1]
    for step in range(1, 261):
        nd = last_d + timedelta(days=DEFAULT_BUCKET_DAYS * step)
        nv = last_v + inc * step
        if nv >= budget:
            ratio = (budget - last_v) / max((nv - last_v), 1e-9)
            span = max((nd - last_d).days, 0)
            return (last_d + timedelta(days=int(round(span * ratio)))).isoformat()
    return None


def _readiness_proxy(health: dict) -> float:
    s = health.get("signals", {}) or {}
    approved_uninv = float(s.get("approved_uninvoiced_hours") or 0.0)
    pending = float(s.get("pending_timesheets_hours") or 0.0)
    return _clip(100.0 - ((approved_uninv * 0.45) + (pending * 0.55)))

def _portfolio_df(health_rows: list[dict]) -> pd.DataFrame:
    rows = []
    for h in health_rows:
        util = h.get("employee_utilization", []) or []
        bill = sum(float(x.get("billable_hours") or 0.0) for x in util)
        total = sum(float(x.get("total_hours") or 0.0) for x in util)
        rows.append(
            {
                "project_id": str(h.get("project_id")),
                "project_name": str(h.get("project_name", "Project")),
                "status": str(h.get("status", "")),
                "risk_score": float(h.get("risk_score") or 0.0),
                "budget": float(h.get("budget") or 0.0),
                "cost_to_date": float(h.get("cost_to_date") or 0.0),
                "forecast_cost": float(h.get("forecast_total_cost_at_end") or 0.0),
                "forecast_profit": float(h.get("forecast_profit_at_end") or 0.0),
                "billable": bill,
                "nonbillable": max(0.0, total - bill),
                "readiness": _readiness_proxy(h),
            }
        )
    return pd.DataFrame(rows).sort_values(["risk_score", "project_name"], ascending=[False, True]) if rows else pd.DataFrame()


def _render_overview(df: pd.DataFrame, start_iso: str, end_iso: str) -> None:
    total_budget = float(df["budget"].sum())
    total_spend = float(df["cost_to_date"].sum())
    total_forecast = float(df["forecast_cost"].sum())
    at_risk = int((df["risk_score"] >= 60).sum())
    avg_risk = float(df["risk_score"].mean())
    budget_pct = (total_spend / total_budget * 100.0) if total_budget > 0 else 0.0
    forecast_pct = (total_forecast / total_budget * 100.0) if total_budget > 0 else 0.0
    readiness = float(df["readiness"].mean())
    billable = float(df["billable"].sum())
    nonbillable = float(df["nonbillable"].sum())
    mix = (billable / (billable + nonbillable) * 100.0) if (billable + nonbillable) > 0 else 0.0

    section("Report Overview", f"Data window: {start_iso} to {end_iso}")
    kpi_strip(
        [
            {"label": "Total Budget", "value": money(total_budget), "foot": "Approved budget", "tone": "neutral"},
            {"label": "Spend To Date", "value": money(total_spend), "foot": f"{budget_pct:.1f}% consumed", "tone": _tone(budget_pct)},
            {"label": "Burn Rate Forecast", "value": money(total_forecast), "foot": "Projected completion cost", "tone": _tone(forecast_pct)},
            {"label": "Projects At Risk", "value": str(at_risk), "foot": f"{len(df)} projects tracked", "tone": "danger" if at_risk else "success"},
        ]
    )
    progress_bar("Budget consumed", budget_pct, detail=f"Spend {money(total_spend)} / Budget {money(total_budget)}", tone=_tone(budget_pct))
    progress_bar("Invoice readiness", readiness, detail="Approval + uninvoiced signal", tone="success" if readiness >= 75 else "warn" if readiness >= 45 else "danger")
    progress_bar("Risk index", avg_risk, detail=f"Average risk {avg_risk:.1f}%", tone=_tone(avg_risk))
    progress_bar("Billable mix", mix, detail=f"Billable {billable:.1f}h / Total {(billable + nonbillable):.1f}h", tone="success" if mix >= 70 else "warn" if mix >= 50 else "danger")


def _select_project(df: pd.DataFrame) -> str:
    labels = [f"{r['project_name']} ({r['status']})" for _, r in df.iterrows()]
    ids = [str(r["project_id"]) for _, r in df.iterrows()]
    current = st.session_state.get("context_project_id")
    idx = ids.index(current) if current in ids else 0
    picked = st.selectbox("Project", labels, index=idx)
    pid = ids[labels.index(picked)]
    st.session_state["context_project_id"] = pid
    st.session_state["context_project_label"] = picked
    return pid


def _plot_forecast(health: dict, reach_date: str | None) -> None:
    actual = pd.DataFrame(health.get("series", {}).get("actual", []) or [])
    forecast = pd.DataFrame(health.get("series", {}).get("forecast", []) or [])
    if actual.empty:
        st.info("No cost trend available.")
        return
    actual["date"] = pd.to_datetime(actual["date"])
    if not forecast.empty:
        forecast["date"] = pd.to_datetime(forecast["date"])
    if forecast.empty and "bucket_cost" in actual:
        last_date = actual["date"].max()
        last_cost = float(actual["cumulative_cost"].iloc[-1])
        recent = [float(v) for v in actual["bucket_cost"].tail(4).tolist() if float(v) > 0]
        increment = (sum(recent) / len(recent)) if recent else 0.0
        if increment > 0:
            rows = [{"date": last_date, "cumulative_cost": last_cost}]
            for step in range(1, 9):
                rows.append(
                    {
                        "date": last_date + pd.Timedelta(days=DEFAULT_BUCKET_DAYS * step),
                        "cumulative_cost": last_cost + (increment * step),
                    }
                )
            forecast = pd.DataFrame(rows)

    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=actual["date"], y=actual["cumulative_cost"], mode="lines", name="Actual Cost", line={"color": "#2563eb", "width": 3}))
        if not forecast.empty:
            fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["cumulative_cost"], mode="lines", name="Forecast Cost", line={"color": "#f59e0b", "width": 2.7, "dash": "dash"}))
        budget = safe_float(health.get("budget"))
        if budget is not None and budget > 0:
            fig.add_hline(y=budget, line_color="#16a34a", line_width=2, annotation_text="Budget")
        end_date = health.get("effective_end_date") or health.get("project_end_date")
        if end_date:
            fig.add_vline(x=end_date, line_color="#dc2626", line_dash="dot", annotation_text="Project End")
        if reach_date:
            fig.add_vline(x=reach_date, line_color="#ef4444", line_dash="dash", annotation_text="Budget Reach")
        fig.update_layout(height=430, margin={"l": 20, "r": 20, "t": 18, "b": 20}, xaxis_title="Date", yaxis_title="Cumulative Internal Cost", legend={"orientation": "h", "y": 1.01})
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        fallback = actual[["date", "cumulative_cost"]].copy().rename(columns={"cumulative_cost": "Actual Cost"}).set_index("date")
        if not forecast.empty:
            f2 = forecast[["date", "cumulative_cost"]].copy().rename(columns={"cumulative_cost": "Forecast Cost"}).set_index("date")
            fallback = fallback.join(f2, how="outer")
        st.line_chart(fallback, use_container_width=True)


@st.cache_data(ttl=300, show_spinner=False)
def _generate_ai_report(base_url_value: str, user_id: str, project_id: str, start_iso: str, end_iso: str) -> dict:
    return APIClient(base_url_value, user_id=user_id).project_risk_explanation(
        project_id,
        bucket_days=DEFAULT_BUCKET_DAYS,
        lookback_buckets=DEFAULT_LOOKBACK_BUCKETS,
        start_date=start_iso,
        end_date=end_iso,
        approved_only=True,
    )

def _render_forecast(base_url_value: str, user_id: str, project_id: str, start_iso: str, end_iso: str, health: dict) -> None:
    section("Forecast To Completion", f"{health.get('project_name', 'Project')} cost forecast and risk status")
    st.markdown(risk_chip(float(health.get("risk_score") or 0.0)), unsafe_allow_html=True)
    reach_date = _budget_reach_date(health)
    budget = safe_float(health.get("budget"))
    forecast = safe_float(health.get("forecast_total_cost_at_end"))
    variance = ((forecast - budget) / budget * 100.0) if budget and budget > 0 and forecast is not None else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cost To Date", money(health.get("cost_to_date")))
    c2.metric("Forecast Completion Cost", money(health.get("forecast_total_cost_at_end")))
    c3.metric("Budget Variance (%)", f"{variance:.1f}%" if variance is not None else pct((health.get("signals") or {}).get("forecast_over_budget_pct")))
    c4.metric("Estimated Budget Reach Date", reach_date or "Not reached in current trend")
    _plot_forecast(health, reach_date)

    section("Top Deterministic Drivers")
    for driver in (health.get("drivers") or []):
        st.markdown(f"- **{driver.get('title', 'Driver')}**: {driver.get('evidence', '')}")

    section("AI Report")
    if "rp_ai_reports" not in st.session_state:
        st.session_state["rp_ai_reports"] = {}
    cache_key = f"{project_id}|{start_iso}|{end_iso}"

    if st.button("Generate AI Report", key=f"rp_ai_btn_{project_id}", type="secondary"):
        try:
            with st.spinner("Generating"):
                payload = _generate_ai_report(base_url_value, user_id, project_id, start_iso, end_iso)
            result = payload.get("result", {}) or {}
        except APIError:
            fb = fallback_ai(health)
            result = {k: v for k, v in fb.items() if k != "meta"}
        st.session_state["rp_ai_reports"][cache_key] = {"result": result}

    report = st.session_state["rp_ai_reports"].get(cache_key)
    if not report:
        return

    result = report.get("result", {}) or {}
    risk_pct = float(result.get("score", health.get("risk_score", 0)) or 0.0)
    c1, c2 = st.columns([1, 3])
    c1.metric("Risk Estimate", f"{risk_pct:.1f}%")
    c2.markdown(f"**Summary**\n\n{result.get('summary', 'No summary available.')}")

    a, b = st.columns(2)
    with a:
        st.markdown("Top Drivers")
        drivers = result.get("top_drivers", []) or []
        if drivers:
            for item in drivers:
                st.markdown(f"- **{item.get('title', 'Driver')}**: {item.get('evidence', '')}")
        else:
            st.markdown("- No drivers available.")
    with b:
        st.markdown("Recommended Actions")
        actions = result.get("recommended_actions", []) or []
        if actions:
            for item in actions:
                st.markdown(
                    f"- **[{item.get('owner', 'PM')}]** {item.get('action', '')}  \n"
                    f"  Why: {item.get('why', '')}"
                )
        else:
            st.markdown("- No actions available.")


def _render_utilization_by_project(health: dict) -> None:
    section("Employee Utilization", f"{health.get('project_name', 'Project')} utilization by employee")
    rows = health.get("employee_utilization", []) or []
    if not rows:
        st.info("No utilization data for this project.")
        return
    df = pd.DataFrame(rows)
    df["utilization_pct"] = df["utilization_logged"].astype(float) * 100.0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Employees", str(len(df)))
    k2.metric("Average Utilization", f"{float(df['utilization_pct'].mean()):.1f}%")
    k3.metric("Billable Hours", f"{float(df['billable_hours'].sum()):.1f}h")
    k4.metric("Total Hours", f"{float(df['total_hours'].sum()):.1f}h")

    try:
        import plotly.express as px

        c1, c2 = st.columns(2)
        with c1:
            bar_df = df.sort_values("utilization_pct", ascending=True)
            fig = px.bar(
                bar_df,
                x="utilization_pct",
                y="employee_name",
                orientation="h",
                color="utilization_pct",
                color_continuous_scale=["#ef4444", "#f59e0b", "#16a34a"],
                labels={"utilization_pct": "Utilization %", "employee_name": "Employee"},
                text="utilization_pct",
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(
                height=420,
                margin={"l": 20, "r": 20, "t": 18, "b": 20},
                coloraxis_showscale=False,
                xaxis_title="Utilization %",
                yaxis_title="",
            )
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            scatter_df = df.copy()
            fig2 = px.scatter(
                scatter_df,
                x="total_hours",
                y="utilization_pct",
                size="billable_hours",
                color="utilization_pct",
                hover_name="employee_name",
                color_continuous_scale=["#ef4444", "#f59e0b", "#16a34a"],
                labels={"total_hours": "Total Hours", "utilization_pct": "Utilization %", "billable_hours": "Billable Hours"},
            )
            fig2.update_layout(
                height=420,
                margin={"l": 20, "r": 20, "t": 18, "b": 20},
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig2, use_container_width=True)
    except Exception:
        st.bar_chart(df.set_index("employee_name")["utilization_pct"], use_container_width=True)

    table = df[["employee_name", "billable_hours", "total_hours", "utilization_pct"]].copy()
    table = table.rename(
        columns={
            "employee_name": "Employee",
            "billable_hours": "Billable Hours",
            "total_hours": "Total Hours",
            "utilization_pct": "Utilization %",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True, height=360)


def _render_utilization_by_employee(all_health_rows: list[dict]) -> None:
    section("Employee Utilization", "Cross-project utilization profile by employee")
    by_employee: dict[str, dict] = {}
    for project_health in all_health_rows:
        project_name = str(project_health.get("project_name") or "Project")
        for util_row in (project_health.get("employee_utilization") or []):
            emp_id = str(util_row.get("employee_id") or "")
            if not emp_id:
                continue
            row = by_employee.setdefault(
                emp_id,
                {
                    "employee_name": str(util_row.get("employee_name") or f"Employee {emp_id[:8]}"),
                    "projects": [],
                },
            )
            bill = float(util_row.get("billable_hours") or 0.0)
            total = float(util_row.get("total_hours") or 0.0)
            util_pct = (bill / total * 100.0) if total > 0 else 0.0
            row["projects"].append(
                {
                    "Project": project_name,
                    "Billable Hours": round(bill, 2),
                    "Total Hours": round(total, 2),
                    "Utilization %": round(util_pct, 1),
                }
            )

    if not by_employee:
        st.info("No employee utilization data available.")
        return

    opts = sorted([(emp_id, data["employee_name"]) for emp_id, data in by_employee.items()], key=lambda x: x[1])
    labels = [f"{name} ({emp_id[:8]})" for emp_id, name in opts]
    picked = st.selectbox("Employee", labels, key="util_emp_pick")
    idx = labels.index(picked)
    emp_id, emp_name = opts[idx]
    across_rows = by_employee[emp_id]["projects"]
    if not across_rows:
        st.info("No cross-project utilization history found for this employee.")
        return

    across_df = pd.DataFrame(across_rows).sort_values("Utilization %", ascending=False)
    st.caption(f"Employee profile: {emp_name}")
    k1, k2, k3 = st.columns(3)
    k1.metric("Projects", str(len(across_df)))
    k2.metric("Average Utilization", f"{float(across_df['Utilization %'].mean()):.1f}%")
    k3.metric("Total Hours", f"{float(across_df['Total Hours'].sum()):.1f}h")

    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(
                x=across_df["Project"],
                y=across_df["Total Hours"],
                name="Total Hours",
                marker_color="#93c5fd",
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Bar(
                x=across_df["Project"],
                y=across_df["Billable Hours"],
                name="Billable Hours",
                marker_color="#2563eb",
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=across_df["Project"],
                y=across_df["Utilization %"],
                name="Utilization %",
                mode="lines+markers",
                line={"color": "#f59e0b", "width": 3},
                marker={"size": 8},
            ),
            secondary_y=True,
        )
        fig.update_layout(
            barmode="group",
            height=430,
            margin={"l": 20, "r": 20, "t": 18, "b": 20},
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0},
        )
        fig.update_yaxes(title_text="Hours", secondary_y=False)
        fig.update_yaxes(title_text="Utilization %", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.bar_chart(across_df.set_index("Project")[["Billable Hours", "Total Hours"]], use_container_width=True)

    st.dataframe(across_df, use_container_width=True, hide_index=True, height=290)


def _render_profit(health: dict) -> None:
    section("Profit Estimate", f"{health.get('project_name', 'Project')} revenue/cost/profit trend")
    rev = safe_float(health.get("revenue_to_date")) or 0.0
    cost = safe_float(health.get("cost_to_date")) or 0.0
    prof = safe_float(health.get("profit_to_date")) or 0.0
    f_rev = safe_float(health.get("forecast_total_revenue_at_end")) or 0.0
    f_cost = safe_float(health.get("forecast_total_cost_at_end")) or 0.0
    f_prof = safe_float(health.get("forecast_profit_at_end")) or 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue To Date", money(rev))
    c2.metric("Cost To Date", money(cost))
    c3.metric("Profit To Date", money(prof))
    c4.metric("Profit Margin", pct((prof / rev) if rev > 0 else None, ratio=True))
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Forecast Revenue", money(f_rev))
    d2.metric("Forecast Cost", money(f_cost))
    d3.metric("Forecast Profit", money(f_prof))
    d4.metric("Budget Variance (%)", pct((health.get("signals") or {}).get("forecast_over_budget_pct")))

    actual = pd.DataFrame(health.get("series", {}).get("actual", []) or [])
    forecast = pd.DataFrame(health.get("series", {}).get("forecast", []) or [])
    if not actual.empty:
        actual["date"] = pd.to_datetime(actual["date"])
    if not forecast.empty:
        forecast["date"] = pd.to_datetime(forecast["date"])
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.11, row_heights=[0.62, 0.38])
        if not actual.empty:
            fig.add_trace(go.Scatter(x=actual["date"], y=actual["cumulative_revenue"], mode="lines", name="Actual Revenue", line={"color": "#16a34a", "width": 3}), row=1, col=1)
            fig.add_trace(go.Scatter(x=actual["date"], y=actual["cumulative_cost"], mode="lines", name="Actual Cost", line={"color": "#2563eb", "width": 3}), row=1, col=1)
            fig.add_trace(go.Scatter(x=actual["date"], y=actual["cumulative_profit"], mode="lines", name="Actual Profit", line={"color": "#7e22ce", "width": 3}, fill="tozeroy", fillcolor="rgba(126,34,206,0.14)"), row=2, col=1)
        if not forecast.empty:
            fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["cumulative_revenue"], mode="lines", name="Forecast Revenue", line={"color": "#22c55e", "width": 2.5, "dash": "dash"}), row=1, col=1)
            fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["cumulative_cost"], mode="lines", name="Forecast Cost", line={"color": "#60a5fa", "width": 2.5, "dash": "dash"}), row=1, col=1)
            fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["cumulative_profit"], mode="lines", name="Forecast Profit", line={"color": "#a855f7", "width": 2.5, "dash": "dash"}), row=2, col=1)
        fig.add_hline(y=0, row=2, col=1, line_color="#64748b", line_width=1)
        end_date = health.get("effective_end_date") or health.get("project_end_date")
        reach = _budget_reach_date(health)
        if end_date:
            fig.add_vline(x=end_date, line_color="#dc2626", line_dash="dot", annotation_text="Project End")
        if reach:
            fig.add_vline(x=reach, line_color="#ef4444", line_dash="dash", annotation_text="Budget Reach")
        fig.update_layout(height=500, margin={"l": 20, "r": 20, "t": 18, "b": 20}, legend={"orientation": "h", "y": 1.02})
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        if not actual.empty:
            simple = actual[["date", "cumulative_revenue", "cumulative_cost", "cumulative_profit"]].set_index("date")
            st.line_chart(simple, use_container_width=True)


apply_theme("Reports", "Default report page with forecast, utilization, and profit modules.", badge="Center")
inject_shared_css()
_inject_css()

user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
user_role = str(st.session_state.get("user_role", "") or "").upper()
if user_role not in {"PM", "FINANCE", "ADMIN"}:
    st.warning("Reports is available only for PM, Finance, or Admin users.")
    st.stop()

start_iso, end_iso = _default_range()
base_url_value = base_url()
try:
    projects = load_projects(base_url_value, user_id)
except APIError as exc:
    st.error(str(exc))
    st.stop()
project_ids = tuple(str(p.get("id")) for p in projects if p.get("id"))
try:
    health_rows = load_portfolio_health(
        base_url_value,
        user_id,
        project_ids,
        DEFAULT_BUCKET_DAYS,
        DEFAULT_LOOKBACK_BUCKETS,
        start_iso,
        end_iso,
        True,
        0,
    )
except APIError as exc:
    st.error(str(exc))
    st.stop()
if not health_rows:
    st.info("No report data available.")
    st.stop()

df = _portfolio_df(health_rows)
if df.empty:
    st.info("No projects with report data.")
    st.stop()

mode = _mode_picker()
if mode == "overview":
    _render_overview(df, start_iso, end_iso)
    st.stop()

health_by_id = {str(h.get("project_id")): h for h in health_rows}

if mode == "utilization":
    util_scope = st.radio(
        "Utilization Filter",
        ["By Project", "By Employee"],
        horizontal=True,
    )
    if util_scope == "By Employee":
        _render_utilization_by_employee(health_rows)
        st.stop()

project_id = _select_project(df)
selected = health_by_id.get(project_id)
if not selected:
    try:
        selected = load_health(
            base_url_value,
            user_id,
            project_id,
            DEFAULT_BUCKET_DAYS,
            DEFAULT_LOOKBACK_BUCKETS,
            start_iso,
            end_iso,
            True,
            0,
        )
    except APIError as exc:
        st.error(str(exc))
        st.stop()

if mode == "forecast":
    _render_forecast(base_url_value, user_id, project_id, start_iso, end_iso, selected)
elif mode == "utilization":
    _render_utilization_by_project(selected)
else:
    _render_profit(selected)
