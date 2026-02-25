import os
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from client.api import APIClient

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
UTC = timezone.utc


def base_url() -> str:
    return st.session_state.get("backend_url", BACKEND_URL)


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def money(value: Any) -> str:
    parsed = safe_float(value)
    return f"${parsed:,.0f}" if parsed is not None else "N/A"


def pct(value: Any, *, ratio: bool = False) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "N/A"
    if ratio:
        parsed *= 100.0
    return f"{parsed:.1f}%"


def as_iso(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    return None


def risk_dot_class(risk_pct: float) -> str:
    if risk_pct >= 60:
        return "ru-risk-red"
    if risk_pct >= 30:
        return "ru-risk-amber"
    return "ru-risk-green"


def risk_chip(risk_pct: float) -> str:
    dot = risk_dot_class(risk_pct)
    return (
        f"<span class='ru-risk-chip'><span class='ru-risk-dot {dot}'></span>"
        f"{risk_pct:.1f}%</span>"
    )


def inject_shared_css() -> None:
    st.markdown(
        """
<style>
.ru-risk-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  border-radius: 999px;
  border: 1px solid #dbe3ee;
  background: #ffffff;
  color: #1f2937;
  padding: 0.17rem 0.5rem;
  font-weight: 800;
  font-size: 0.73rem;
}
.ru-risk-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
}
.ru-risk-green { background: #16a34a; }
.ru-risk-amber { background: #d97706; }
.ru-risk-red { background: #dc2626; }
</style>
""",
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=300)
def load_projects(base_url_value: str, user_id: str) -> list[dict]:
    return APIClient(base_url_value, user_id=user_id).list_projects()


@st.cache_data(ttl=150)
def load_health(
    base_url_value: str,
    user_id: str,
    project_id: str,
    bucket_days: int,
    lookback_buckets: int,
    start_date: str | None,
    end_date: str | None,
    approved_only: bool,
    refresh_nonce: int,
) -> dict:
    _ = refresh_nonce
    return APIClient(base_url_value, user_id=user_id).project_health(
        project_id,
        bucket_days=bucket_days,
        lookback_buckets=lookback_buckets,
        start_date=start_date,
        end_date=end_date,
        approved_only=approved_only,
    )


@st.cache_data(ttl=150)
def load_portfolio_health(
    base_url_value: str,
    user_id: str,
    project_ids: tuple[str, ...],
    bucket_days: int,
    lookback_buckets: int,
    start_date: str | None,
    end_date: str | None,
    approved_only: bool,
    refresh_nonce: int,
) -> list[dict]:
    _ = refresh_nonce
    api = APIClient(base_url_value, user_id=user_id)
    rows: list[dict] = []
    for project_id in project_ids:
        try:
            rows.append(
                api.project_health(
                    project_id,
                    bucket_days=bucket_days,
                    lookback_buckets=lookback_buckets,
                    start_date=start_date,
                    end_date=end_date,
                    approved_only=approved_only,
                )
            )
        except Exception:
            continue
    return rows


def fallback_ai(health: dict[str, Any]) -> dict[str, Any]:
    drivers = health.get("drivers", []) or []
    summary = "Deterministic fallback generated because AI request failed."
    if drivers:
        summary = f"{summary} Main signal: {drivers[0].get('title', 'N/A')}."
    return {
        "risk_level": health.get("risk_level", "GREEN"),
        "score": float(health.get("risk_score", 0) or 0),
        "summary": summary,
        "top_drivers": drivers,
        "recommended_actions": [
            {
                "action": "Review top cost and invoicing drivers this week",
                "owner": "PM",
                "why": "Deterministic controls indicate pressure points.",
            }
        ],
        "assumptions": [
            f"Cost forecast method: {health.get('forecast_method', 'moving_average')}",
            f"Revenue forecast method: {health.get('revenue_forecast_method', 'moving_average')}",
        ],
        "data_quality_flags": health.get("data_quality_flags", []) or [],
        "meta": {
            "model": "local_fallback",
            "timestamp": datetime.now(UTC).isoformat(),
            "used_fallback": True,
        },
    }


def chart_cost_forecast(health: dict[str, Any], budget: float | None, exceed_date: str | None) -> None:
    actual_df = pd.DataFrame(health.get("series", {}).get("actual", []))
    forecast_df = pd.DataFrame(health.get("series", {}).get("forecast", []))
    if actual_df.empty:
        st.info("No cost history available for this range.")
        return

    actual_df["date"] = pd.to_datetime(actual_df["date"])
    if not forecast_df.empty:
        forecast_df["date"] = pd.to_datetime(forecast_df["date"])

    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=actual_df["date"],
                y=actual_df["cumulative_cost"],
                mode="lines",
                name="Actual Cost",
                line={"color": "#2563eb", "width": 3},
            )
        )
        if not forecast_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=forecast_df["date"],
                    y=forecast_df["cumulative_cost"],
                    mode="lines",
                    name="Forecast Cost",
                    line={"color": "#f59e0b", "width": 2.5, "dash": "dash"},
                )
            )
        if budget is not None:
            fig.add_hline(y=budget, line_color="#16a34a", line_width=2, annotation_text="Budget")
        if exceed_date:
            fig.add_vline(x=exceed_date, line_dash="dot", line_color="#dc2626", line_width=2)
        fig.update_layout(
            margin={"l": 20, "r": 20, "t": 18, "b": 20},
            height=360,
            xaxis_title="Date",
            yaxis_title="Cumulative Cost",
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0},
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        chart_df = actual_df[["date", "cumulative_cost"]].copy()
        chart_df["series"] = "Actual Cost"
        if not forecast_df.empty:
            ff = forecast_df[["date", "cumulative_cost"]].copy()
            ff["series"] = "Forecast Cost"
            chart_df = pd.concat([chart_df, ff], ignore_index=True)
        st.line_chart(
            chart_df.pivot_table(index="date", columns="series", values="cumulative_cost", aggfunc="last"),
            use_container_width=True,
        )


def chart_revenue_profit(health: dict[str, Any]) -> None:
    actual_df = pd.DataFrame(health.get("series", {}).get("actual", []))
    forecast_df = pd.DataFrame(health.get("series", {}).get("forecast", []))
    if actual_df.empty:
        st.info("No revenue/profit history available for this range.")
        return

    actual_df["date"] = pd.to_datetime(actual_df["date"])
    if not forecast_df.empty:
        forecast_df["date"] = pd.to_datetime(forecast_df["date"])

    try:
        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=actual_df["date"],
                y=actual_df["cumulative_revenue"],
                mode="lines",
                name="Actual Revenue",
                line={"color": "#16a34a", "width": 3},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=actual_df["date"],
                y=actual_df["cumulative_profit"],
                mode="lines",
                name="Actual Profit",
                line={"color": "#7c3aed", "width": 2.6},
            )
        )
        if not forecast_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=forecast_df["date"],
                    y=forecast_df["cumulative_revenue"],
                    mode="lines",
                    name="Forecast Revenue",
                    line={"color": "#22c55e", "width": 2.3, "dash": "dash"},
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=forecast_df["date"],
                    y=forecast_df["cumulative_profit"],
                    mode="lines",
                    name="Forecast Profit",
                    line={"color": "#a78bfa", "width": 2.3, "dash": "dash"},
                )
            )
        fig.update_layout(
            margin={"l": 20, "r": 20, "t": 18, "b": 20},
            height=360,
            xaxis_title="Date",
            yaxis_title="Revenue / Profit",
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0},
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        chart_df = actual_df[["date", "cumulative_revenue", "cumulative_profit"]].copy()
        chart_df = chart_df.rename(
            columns={"cumulative_revenue": "Actual Revenue", "cumulative_profit": "Actual Profit"}
        )
        st.line_chart(chart_df.set_index("date"), use_container_width=True)

