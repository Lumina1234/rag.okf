"""
Analytics Engine.
Orchestrates tabular data ingestion (Excel/CSV), deterministic calculation execution,
Power BI-style chart generation, and executive intelligence synthesis with gemma4:12b.
"""
import io
import json
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from core.config import settings
from services import ollama_client
from services.analytics import (
    default_calc_engine,
    default_explainer,
    default_analytics_validator,
    resolve_column,
)
from services.chart_generator import build_powerbi_chart, validate_plotly_json
from services.harness import analyze_intent

logger = logging.getLogger(__name__)


def load_dataframe(file_path: Path, file_type: str) -> dict[str, pd.DataFrame]:
    """Load a file into one or more DataFrames keyed by sheet/table name."""
    ft = file_type.lower()
    if ft in ("xlsx", "xls"):
        sheets = pd.read_excel(str(file_path), sheet_name=None)
        return {k: v for k, v in sheets.items()}
    elif ft == "csv":
        df = pd.read_csv(str(file_path))
        return {"data": df}
    else:
        raise ValueError(f"Unsupported analytics file type: {file_type}")


def _df_summary(df: pd.DataFrame, max_rows: int = 5) -> str:
    """Return a concise string summary of a DataFrame for LLM context."""
    lines = [
        f"Columns: {list(df.columns)}",
        f"Rows: {len(df)}",
        f"Dtypes: {df.dtypes.to_dict()}",
        "",
        "First rows:",
        df.head(max_rows).to_string(index=False),
        "",
        "Numeric statistics:",
        df.describe(include="all").to_string(),
    ]
    return "\n".join(str(l) for l in lines)


def detect_chart_intent(query: str) -> Optional[str]:
    """
    Chart-type detection from natural-language query.
    Returns: 'bar' | 'stacked_bar' | 'line' | 'area' | 'pie' | 'waterfall' | 'scatter' | 'kpi' | 'table' | None
    """
    q = query.lower()
    if any(w in q for w in ["waterfall", "bridge", "variance bridge"]):
        return "waterfall"
    if any(w in q for w in ["stacked bar", "stacked"]):
        return "stacked_bar"
    if any(w in q for w in ["area chart", "area", "cumulative"]):
        return "area"
    if any(w in q for w in ["kpi", "metric card", "headline numbers"]):
        return "kpi"
    if any(w in q for w in ["trend", "over time", "monthly", "daily", "weekly", "yearly", "growth", "progress"]):
        return "line"
    if any(w in q for w in ["share", "percentage", "proportion", "distribution", "breakdown", "composition", "donut"]):
        return "pie"
    if any(w in q for w in ["compare", "comparison", "top", "ranking", "best", "worst", "highest", "lowest", "bar", "profitability", "profit margin", "margin", "profit"]):
        return "bar"
    if any(w in q for w in ["correlation", "relationship", "scatter", "vs", "versus"]):
        return "scatter"
    if any(w in q for w in ["table", "list", "show all", "summarize", "summary"]):
        return "table"
    return None


def _build_chart_data(
    df: pd.DataFrame,
    query: str,
    chart_type: str,
    title: str,
) -> Optional[dict]:
    """
    Fallback Plotly chart builder when custom Power BI layout is not used.
    """
    try:
        import plotly.express as px
        num_cols = df.select_dtypes(include="number").columns.tolist()
        str_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

        if not num_cols:
            return None

        y_col = num_cols[0]
        x_col = str_cols[0] if str_cols else df.columns[0]

        if chart_type == "bar":
            fig = px.bar(
                df.head(20), x=x_col, y=y_col,
                title=title,
                color_discrete_sequence=["#6366f1"],
                template="plotly_dark",
            )
        elif chart_type == "line":
            fig = px.line(
                df.head(50), x=x_col, y=y_col,
                title=title,
                color_discrete_sequence=["#6366f1"],
                template="plotly_dark",
                markers=True,
            )
        elif chart_type == "pie":
            fig = px.pie(
                df.head(10), names=x_col, values=y_col,
                title=title,
                template="plotly_dark",
            )
        elif chart_type == "scatter":
            y2_col = num_cols[1] if len(num_cols) > 1 else y_col
            fig = px.scatter(
                df.head(100), x=y_col, y=y2_col,
                title=title,
                color_discrete_sequence=["#6366f1"],
                template="plotly_dark",
            )
        else:
            return None

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0"),
        )
        plotly_json = json.loads(fig.to_json())
        return {
            "chart_type": chart_type,
            "title": title,
            "plotly_json": plotly_json,
        }
    except Exception as e:
        logger.error(f"Fallback chart build error: {e}")
        return None


async def analyze(
    file_path: Path,
    file_type: str,
    query: str,
    chart_type_hint: Optional[str] = None,
) -> dict[str, Any]:
    """
    Full intelligent analytics pipeline:
      1. Ingest Excel/CSV data into pandas
      2. Analyze query intent and analytical dimensions
      3. Execute deterministic calculations (sums, YoY, MoM, margins, variances)
      4. Synthesize with gemma4:12b or format verified BI markdown report
      5. Construct validated Power BI-style Plotly visual
      6. Return verified structured payload
    """
    sheets = load_dataframe(file_path, file_type)
    sheet_name, df = next(iter(sheets.items()))

    # Intent and chart detection
    intent_analysis = analyze_intent(query)
    chart_type = chart_type_hint or intent_analysis.chart_type_hint or detect_chart_intent(query)

    # Deterministic Business Calculation
    calc_res = default_calc_engine.execute_analytical_query(df, query)
    bi_report = default_explainer.format_markdown_report(calc_res, query)

    # Synthesize executive insights with gemma4:12b using verified figures
    system_prompt = (
        "You are an expert Chief Financial Officer and Senior Business Intelligence Analyst. "
        "Explain the business analytical results clearly and concisely for corporate decision-makers.\n"
        "STRICT NON-NEGOTIABLE COMPLIANCE RULES:\n"
        "1. Strictly use the verified figures, metrics, and breakdowns provided in the context. Never invent numbers.\n"
        "2. When baseline is unavailable, you MUST report 'Variance: Not calculated — baseline unavailable.' NEVER report 0% variance, zero variance, or no variance.\n"
        "3. NEVER describe a metric or volume as stable, consistent over time, or showing no change unless verified time-series analysis is explicitly present.\n"
        "4. Strictly separate verified calculations from analytical interpretations.\n"
        "5. For quantity/volume queries, always report Total quantity, Average quantity, Minimum, and Maximum using 'units' as the unit.\n"
        "6. Identify primary drivers ONLY from the verified breakdown table. If drivers cannot be established, state that limitation clearly.\n"
        "7. If Product or Category breakdown is provided in the verified breakdown table, analyze the top products and rankings. NEVER claim that product identifiers, categorical breakdowns, or chart data are unavailable when they are present in the table.\n"
        "8. If the dataset does not contain Product or Category columns, state specifically that Product and Category fields are not present in this dataset; do not claim that the entire dataset contains aggregate figures only unless verified.\n"
        "9. Distinguish revenue and profit totals from product-level findings. Do not infer business drivers from aggregate figures alone.\n"
        "Format your answer with clean Markdown headers, bullet points, and key takeaways."
    )

    baseline_display = (
        f"{calc_res.baseline_value:,.2f}"
        if calc_res.has_baseline and calc_res.baseline_value is not None
        else "Baseline unavailable"
    )
    variance_display = (
        calc_res.variance_status
        if not calc_res.has_baseline
        else f"{calc_res.variance:+,.2f} ({calc_res.variance_pct:+.2f}%)"
    )

    qty_stats_text = "N/A"
    if calc_res.quantity_stats:
        qty_stats_text = (
            f"- Total Quantity: {calc_res.quantity_stats['total_formatted']}\n"
            f"- Average Quantity: {calc_res.quantity_stats['average_formatted']}\n"
            f"- Minimum Quantity: {calc_res.quantity_stats['min_formatted']}\n"
            f"- Maximum Quantity: {calc_res.quantity_stats['max_formatted']}\n"
            f"- Record Count: {calc_res.quantity_stats['count']} records"
        )

    financial_kpis_text = "N/A"
    if calc_res.financial_kpis:
        financial_kpis_text = (
            f"- Total Revenue: {calc_res.financial_kpis['total_revenue_formatted']}\n"
            f"- Total Cost: {calc_res.financial_kpis['total_cost_formatted']}\n"
            f"- Total Profit: {calc_res.financial_kpis['total_profit_formatted']}\n"
            f"- Overall Profit Margin: {calc_res.financial_kpis['profit_margin_formatted']}\n"
            f"- Record Count: {calc_res.financial_kpis['record_count']} records\n"
            f"- Dimension Analyzed: {calc_res.dimension or 'None'}"
        )

    product_rankings_text = "N/A"
    if calc_res.product_rankings:
        product_rankings_text = "\n".join(f"- {r}" for r in calc_res.product_rankings)

    driver_text = (
        calc_res.top_driver
        if calc_res.driver_established
        else (calc_res.driver_explanation or "Primary drivers cannot be established without categorical segmentation in the dataset.")
    )

    missing_cols_text = ", ".join(calc_res.missing_columns) if calc_res.missing_columns else "None"

    user_prompt = f"""Verified Calculation Data:
Metric: {calc_res.metric_name}
Calculated Value: {calc_res.formatted_value}
Formula: {calc_res.formula}
Baseline: {baseline_display}
Variance: {variance_display}
Has Baseline: {calc_res.has_baseline}
Has Time-Series: {calc_res.has_time_series}
Missing Columns: {missing_cols_text}
Financial KPIs:
{financial_kpis_text}

Product Rankings:
{product_rankings_text}

Quantity Statistics:
{qty_stats_text}
Primary Driver: {driver_text}

Verified Breakdown Table:
{pd.DataFrame(calc_res.grouped_table).to_markdown() if calc_res.grouped_table else 'N/A'}

User Business Query:
{query}

Provide a concise, professional executive answer based on these exact figures:"""

    try:
        llm_answer = await ollama_client.chat_complete(
            prompt=user_prompt,
            system=system_prompt,
            model=settings.DEFAULT_LLM_MODEL,
        )
        if llm_answer and not llm_answer.startswith("⚠️ **LLM Error:"):
            # Append verified methodology footer if not present
            if "Methodology" not in llm_answer:
                llm_answer = f"{llm_answer.strip()}\n\n---\n**Verified Formula**: `{calc_res.formula}` | **Exact Value**: `{calc_res.formatted_value}`"
            raw_answer = llm_answer
        else:
            raw_answer = bi_report
    except Exception as e:
        logger.warning(f"LLM synthesis fallback to deterministic report: {e}")
        raw_answer = bi_report

    # Deterministic post-generation validation and correction layer (Requirement 7)
    final_answer, corrections = default_analytics_validator.validate_and_sanitize(
        raw_answer, calc_res, query=query
    )
    if corrections:
        logger.info(f"Analytics post-generation validator applied {len(corrections)} corrections: {corrections}")

    # Power BI-style visual generation
    chart_data = None
    if chart_type and chart_type != "table":
        chart_data = build_powerbi_chart(df, query, chart_type_hint=chart_type, title=calc_res.metric_name)
        if not chart_data:
            chart_data = _build_chart_data(df, query, chart_type, sheet_name)

    raw_data = df.head(50).fillna("").to_dict(orient="records")

    return {
        "query": query,
        "answer": final_answer,
        "chart": chart_data,
        "raw_data": raw_data,
        "sheet_name": sheet_name,
        "total_rows": len(df),
        "columns": list(df.columns),
        "calculation": {
            "metric_name": calc_res.metric_name,
            "value": calc_res.value,
            "formatted_value": calc_res.formatted_value,
            "formula": calc_res.formula,
            "variance": calc_res.variance,
            "variance_pct": calc_res.variance_pct,
            "variance_status": calc_res.variance_status,
            "has_baseline": calc_res.has_baseline,
            "has_time_series": calc_res.has_time_series,
            "quantity_stats": calc_res.quantity_stats,
            "financial_kpis": calc_res.financial_kpis,
            "product_rankings": calc_res.product_rankings,
            "missing_columns": calc_res.missing_columns,
            "dimension": calc_res.dimension,
            "top_driver": calc_res.top_driver,
            "driver_established": calc_res.driver_established,
        },
    }
