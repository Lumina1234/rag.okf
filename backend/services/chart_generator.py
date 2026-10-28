"""
Chart generator service.
Creates interactive, Power BI-style Plotly charts from structured data and saves them as JSON.
Supports Bar, Stacked Bar, Line, Area, Pie/Donut, Waterfall, Scatter, and KPI metric cards.
"""
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from core.config import settings

logger = logging.getLogger(__name__)

# Premium Enterprise Dark Theme Palette
ENTERPRISE_COLORS = [
    "#6366f1",  # Indigo primary
    "#8b5cf6",  # Violet
    "#06b6d4",  # Cyan
    "#10b981",  # Emerald green
    "#f59e0b",  # Amber
    "#ec4899",  # Pink
    "#3b82f6",  # Blue
    "#14b8a6",  # Teal
]


def _apply_theme(fig) -> None:
    """Apply the dark enterprise theme to a Plotly figure."""
    fig.update_layout(
        paper_bgcolor="rgba(15, 15, 35, 0)",
        plot_bgcolor="rgba(15, 15, 35, 0)",
        font=dict(family="Inter, system-ui, sans-serif", color="#e2e8f0", size=13),
        title_font=dict(size=16, color="#a5b4fc"),
        legend=dict(
            bgcolor="rgba(30, 41, 59, 0.7)",
            bordercolor="rgba(255, 255, 255, 0.1)",
            font=dict(color="#cbd5e1"),
        ),
        margin=dict(l=40, r=40, t=60, b=40),
        colorway=ENTERPRISE_COLORS,
    )
    fig.update_xaxes(
        gridcolor="rgba(100, 116, 139, 0.15)",
        zerolinecolor="rgba(100, 116, 139, 0.25)",
        tickfont=dict(color="#94a3b8"),
    )
    fig.update_yaxes(
        gridcolor="rgba(100, 116, 139, 0.15)",
        zerolinecolor="rgba(100, 116, 139, 0.25)",
        tickfont=dict(color="#94a3b8"),
    )


def validate_plotly_json(chart_json: Any) -> bool:
    """Ensure the generated Plotly specification is valid JSON with data and layout."""
    if not isinstance(chart_json, dict):
        return False
    if "data" not in chart_json or not isinstance(chart_json["data"], list):
        return False
    return True


def generate_bar_chart(
    x: list,
    y: list,
    title: str = "Bar Chart",
    x_label: str = "",
    y_label: str = "",
    horizontal: bool = False,
) -> dict:
    """Generate a standard bar or horizontal bar chart."""
    import plotly.graph_objects as go

    orientation = "h" if horizontal else "v"
    x_vals, y_vals = (y, x) if horizontal else (x, y)

    fig = go.Figure(
        go.Bar(
            x=x_vals,
            y=y_vals,
            orientation=orientation,
            marker=dict(
                color=y_vals if not horizontal else x_vals,
                colorscale=[[0, "#6366f1"], [1, "#8b5cf6"]],
                showscale=False,
            ),
            text=y_vals if not horizontal else x_vals,
            textposition="outside",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        template="plotly_dark",
    )
    _apply_theme(fig)
    return json.loads(fig.to_json())


def generate_stacked_bar_chart(
    x: list,
    series_dict: dict[str, list],
    title: str = "Stacked Bar Chart",
    x_label: str = "",
    y_label: str = "",
) -> dict:
    """Generate a stacked bar chart across multiple sub-categories."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for i, (name, values) in enumerate(series_dict.items()):
        color = ENTERPRISE_COLORS[i % len(ENTERPRISE_COLORS)]
        fig.add_trace(go.Bar(name=name, x=x, y=values, marker_color=color))

    fig.update_layout(
        barmode="stack",
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        template="plotly_dark",
    )
    _apply_theme(fig)
    return json.loads(fig.to_json())


def generate_line_chart(
    x: list,
    y: list | dict,
    title: str = "Line Chart",
    x_label: str = "",
    y_label: str = "",
) -> dict:
    """Generate a line chart. y can be a single list or a dict of {series_name: [values]}."""
    import plotly.graph_objects as go

    fig = go.Figure()
    if isinstance(y, dict):
        for i, (name, values) in enumerate(y.items()):
            color = ENTERPRISE_COLORS[i % len(ENTERPRISE_COLORS)]
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=values,
                    name=name,
                    mode="lines+markers",
                    line=dict(color=color, width=2.5),
                    marker=dict(size=6),
                )
            )
    else:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines+markers",
                line=dict(color="#6366f1", width=2.5),
                marker=dict(size=6),
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        template="plotly_dark",
    )
    _apply_theme(fig)
    return json.loads(fig.to_json())


def generate_area_chart(
    x: list,
    y: list,
    title: str = "Area Trend Chart",
    x_label: str = "",
    y_label: str = "",
) -> dict:
    """Generate an area chart with gradient fill for cumulative/trend visualization."""
    import plotly.graph_objects as go

    fig = go.Figure(
        go.Scatter(
            x=x,
            y=y,
            fill="tozeroy",
            mode="lines+markers",
            line=dict(color="#6366f1", width=2.5),
            fillcolor="rgba(99, 102, 241, 0.25)",
            marker=dict(size=6),
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        template="plotly_dark",
    )
    _apply_theme(fig)
    return json.loads(fig.to_json())


def generate_pie_chart(
    labels: list,
    values: list,
    title: str = "Distribution",
    hole: float = 0.45,
) -> dict:
    """Generate a donut/pie chart with clean percentage callouts."""
    import plotly.graph_objects as go

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=hole,
            textinfo="label+percent",
            hoverinfo="label+value+percent",
            marker=dict(colors=ENTERPRISE_COLORS),
        )
    )
    fig.update_layout(title=title, template="plotly_dark")
    _apply_theme(fig)
    return json.loads(fig.to_json())


def generate_waterfall_chart(
    categories: list[str],
    values: list[float],
    title: str = "Variance / Breakdown Bridge",
) -> dict:
    """Generate a waterfall chart to display variance bridges or component changes."""
    import plotly.graph_objects as go

    measures = ["relative"] * (len(categories) - 1) + ["total"] if len(categories) > 1 else ["total"]

    fig = go.Figure(
        go.Waterfall(
            name="Bridge",
            orientation="v",
            measure=measures,
            x=categories,
            textposition="outside",
            text=[f"{v:+,.2f}" for v in values],
            y=values,
            connector={"line": {"color": "rgba(255, 255, 255, 0.3)"}},
            decreasing={"marker": {"color": "#ef4444"}},
            increasing={"marker": {"color": "#10b981"}},
            totals={"marker": {"color": "#6366f1"}},
        )
    )
    fig.update_layout(title=title, template="plotly_dark")
    _apply_theme(fig)
    return json.loads(fig.to_json())


def generate_scatter_chart(
    x: list,
    y: list,
    labels: Optional[list] = None,
    title: str = "Correlation Scatter Plot",
    x_label: str = "",
    y_label: str = "",
) -> dict:
    """Generate a correlation scatter plot with optional text labels."""
    import plotly.graph_objects as go

    fig = go.Figure(
        go.Scatter(
            x=x,
            y=y,
            mode="markers+text" if labels else "markers",
            text=labels if labels else None,
            textposition="top center",
            marker=dict(
                size=10,
                color="#8b5cf6",
                line=dict(width=1, color="#cbd5e1"),
            ),
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        template="plotly_dark",
    )
    _apply_theme(fig)
    return json.loads(fig.to_json())


def generate_kpi_cards(kpis: list[dict]) -> dict:
    """
    Generate KPI indicator cards.
    kpis: [{"label": "Revenue", "value": 1234567, "delta": 12.5, "unit": "$"}]
    """
    import plotly.graph_objects as go

    cols = min(len(kpis), 4)
    rows = (len(kpis) - 1) // cols + 1
    fig = go.Figure()

    for i, kpi in enumerate(kpis):
        col = i % cols
        row = i // cols
        delta = kpi.get("delta")
        fig.add_trace(
            go.Indicator(
                mode="number+delta" if delta is not None else "number",
                value=kpi["value"],
                title={"text": kpi["label"], "font": {"size": 14, "color": "#cbd5e1"}},
                delta={"reference": kpi["value"] - delta, "relative": True} if delta else None,
                number={"prefix": kpi.get("unit", ""), "font": {"size": 28, "color": "#818cf8"}},
                domain={"row": row, "column": col},
            )
        )

    fig.update_layout(
        grid={"rows": rows, "columns": cols, "pattern": "independent"},
        template="plotly_dark",
    )
    _apply_theme(fig)
    return json.loads(fig.to_json())


def save_chart(plotly_json: dict, workspace_id: int) -> str:
    """Save chart JSON to disk. Returns the relative URL path."""
    chart_id = str(uuid.uuid4())[:8]
    chart_file = settings.CHARTS_DIR / f"{workspace_id}_{chart_id}.json"
    chart_file.write_text(json.dumps(plotly_json), encoding="utf-8")
    return f"/charts/{workspace_id}_{chart_id}.json"


def build_powerbi_chart(
    df: pd.DataFrame,
    query: str,
    chart_type_hint: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[dict]:
    """
    Intelligently construct a validated Power BI-style chart based on data and user intent.
    Automatically maps dimensions, dates, and metrics based on dataset schema inspection.
    """
    try:
        from services.analytics.calculation_engine import resolve_column, inspect_dataset_schema
        q_lower = query.lower()
        schema = inspect_dataset_schema(df)

        # Handle aggregate-only datasets (no categorical breakdown available)
        if schema["is_aggregate_only"]:
            kpis = []
            rev_col = schema["revenue_col"]
            profit_col = schema["profit_col"]
            cost_col = schema["cost_col"]
            if rev_col and rev_col in df:
                rev_val = float(pd.to_numeric(df[rev_col], errors="coerce").dropna().sum())
                kpis.append({"label": "Total Revenue", "value": round(rev_val, 2), "unit": "$"})
            if profit_col and profit_col in df:
                prof_val = float(pd.to_numeric(df[profit_col], errors="coerce").dropna().sum())
                kpis.append({"label": "Total Profit", "value": round(prof_val, 2), "unit": "$"})
            elif rev_col and cost_col and rev_col in df and cost_col in df:
                rev_val = float(pd.to_numeric(df[rev_col], errors="coerce").dropna().sum())
                cost_val = float(pd.to_numeric(df[cost_col], errors="coerce").dropna().sum())
                kpis.append({"label": "Total Profit", "value": round(rev_val - cost_val, 2), "unit": "$"})
            if cost_col and cost_col in df:
                cost_val = float(pd.to_numeric(df[cost_col], errors="coerce").dropna().sum())
                kpis.append({"label": "Total Cost", "value": round(cost_val, 2), "unit": "$"})
            
            if kpis:
                chart_json = generate_kpi_cards(kpis)
                return {"chart_type": "kpi", "title": title or "Financial KPI Summary", "plotly_json": chart_json}
            return None

        # Find target metric column
        metric_col = None
        for candidate in ["profit", "revenue", "cost", "quantity", "discount", "satisfaction"]:
            if candidate in q_lower or (candidate == "revenue" and "sales" in q_lower):
                metric_col = resolve_column(df, candidate)
                if metric_col:
                    break
        if not metric_col:
            if schema["profit_col"]:
                metric_col = schema["profit_col"]
            elif schema["revenue_col"]:
                metric_col = schema["revenue_col"]
            else:
                num_cols = df.select_dtypes(include="number").columns.tolist()
                metric_col = num_cols[0] if num_cols else None

        if not metric_col:
            return None

        # Check date / trend
        date_col = resolve_column(df, "date")
        is_trend = any(w in q_lower for w in ["trend", "monthly", "over time", "by date", "timeline", "progression"])
        if is_trend and date_col:
            temp = df[[date_col, metric_col]].copy()
            temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
            temp[metric_col] = pd.to_numeric(temp[metric_col], errors="coerce")
            temp = temp.dropna().sort_values(by=date_col)
            temp["period"] = temp[date_col].dt.to_period("M").astype(str)
            grouped = temp.groupby("period", as_index=False)[metric_col].sum()

            chart_title = title or f"{metric_col} Trend Over Time"
            x_vals = grouped["period"].tolist()
            y_vals = grouped[metric_col].tolist()

            if chart_type_hint == "area" or "area" in q_lower:
                chart_json = generate_area_chart(x_vals, y_vals, title=chart_title, x_label="Period", y_label=metric_col)
                chart_type = "area"
            else:
                chart_json = generate_line_chart(x_vals, y_vals, title=chart_title, x_label="Period", y_label=metric_col)
                chart_type = "line"

            return {"chart_type": chart_type, "title": chart_title, "plotly_json": chart_json}

        # Check dimension (Region, Product, Category, Customer Segment, Channel)
        dim_col = None
        for cand in ["product", "category", "region", "channel", "customer", "segment"]:
            if cand in q_lower:
                dim_col = resolve_column(df, cand)
                if dim_col:
                    break
        if not dim_col:
            dim_col = schema["preferred_dimension"]
        if not dim_col:
            str_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
            dim_col = str_cols[0] if str_cols else None

        if not dim_col or dim_col == metric_col:
            return None

        # Group by dimension
        clean_df = df[[dim_col, metric_col]].copy()
        clean_df[metric_col] = pd.to_numeric(clean_df[metric_col], errors="coerce")
        grouped = clean_df.groupby(dim_col, as_index=False)[metric_col].sum().sort_values(by=metric_col, ascending=False)

        x_vals = [str(x) for x in grouped[dim_col].tolist()[:10]]
        y_vals = [round(float(y), 2) for y in grouped[metric_col].tolist()[:10]]
        chart_title = title or f"{metric_col} by {dim_col}"

        # Choose visual type
        if chart_type_hint == "pie" or any(w in q_lower for w in ["share", "distribution", "pie", "donut", "proportion"]):
            chart_json = generate_pie_chart(labels=x_vals, values=y_vals, title=chart_title)
            chart_type = "pie"
        elif chart_type_hint == "waterfall" or "waterfall" in q_lower:
            chart_json = generate_waterfall_chart(categories=x_vals, values=y_vals, title=chart_title)
            chart_type = "waterfall"
        elif chart_type_hint == "scatter" or "scatter" in q_lower or "correlation" in q_lower:
            num_cols = df.select_dtypes(include="number").columns.tolist()
            y2_col = num_cols[1] if len(num_cols) > 1 and num_cols[1] != metric_col else metric_col
            chart_json = generate_scatter_chart(
                x=df[metric_col].head(50).tolist(),
                y=df[y2_col].head(50).tolist(),
                labels=[str(x) for x in df[dim_col].head(50).tolist()],
                title=f"{metric_col} vs {y2_col}",
                x_label=metric_col,
                y_label=y2_col,
            )
            chart_type = "scatter"
        else:
            # Default to Bar chart
            chart_json = generate_bar_chart(
                x=x_vals,
                y=y_vals,
                title=chart_title,
                x_label=dim_col,
                y_label=metric_col,
                horizontal=len(x_vals) > 6,
            )
            chart_type = "bar"

        if validate_plotly_json(chart_json):
            return {"chart_type": chart_type, "title": chart_title, "plotly_json": chart_json}

        return None
    except Exception as e:
        logger.error(f"build_powerbi_chart failed: {e}")
        return None
