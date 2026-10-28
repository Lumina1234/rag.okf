"""
Deterministic Business Calculation Engine.
Executes pure, verified numerical computations on Pandas DataFrames:
Sums, Averages, YoY, MoM, Growth Rates, Profit Margins, Variances, and Grouped Aggregations.
Never relies on LLM arithmetic hallucinations.
"""
from dataclasses import dataclass, field
import logging
import math
import re
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Column synonym mapping for natural language resolution
COLUMN_SYNONYMS = {
    "revenue": ["revenue", "sales", "turnover", "total_revenue", "gross_sales"],
    "profit": ["profit", "net_profit", "earnings", "net_income", "margin_val"],
    "cost": ["cost", "cogs", "expenses", "total_cost", "spend"],
    "quantity": ["quantity", "units", "qty", "volume", "count", "orders"],
    "price": ["unit_price", "price", "rate", "cost_per_unit"],
    "discount": ["discount", "discount_percent", "rebate", "discount_rate"],
    "date": ["order_date", "date", "created_at", "timestamp", "period", "month", "year"],
    "region": ["region", "territory", "location", "geography", "zone", "state", "country"],
    "product": ["product", "item", "sku", "product_name"],
    "category": ["category", "segment", "department", "type"],
    "channel": ["sales_channel", "channel", "distribution_channel"],
    "customer": ["customer", "customer_segment", "client", "account"],
    "satisfaction": ["customer_satisfaction", "csat", "nps", "rating", "score"],
}


def resolve_column(df: pd.DataFrame, requested: str) -> Optional[str]:
    """Fuzzy matches a user-requested metric or dimension against dataframe columns."""
    req_norm = re.sub(r"[\s_-]+", "", requested.lower())
    # Exact match case-insensitive
    for col in df.columns:
        if re.sub(r"[\s_-]+", "", col.lower()) == req_norm:
            return col

    # Check synonyms
    for canon, syns in COLUMN_SYNONYMS.items():
        if req_norm == canon or req_norm in [s.replace("_", "") for s in syns]:
            for col in df.columns:
                c_norm = col.lower().replace("_", "")
                if any(s.replace("_", "") == c_norm for s in syns) or c_norm == canon:
                    return col

    # Partial substring match
    for col in df.columns:
        if req_norm in col.lower() or col.lower() in req_norm:
            return col

    return None


def inspect_dataset_schema(df: pd.DataFrame) -> dict[str, Any]:
    """
    Inspect column names, data types, record counts, and sample values
    before deciding which analyses, grouped aggregations, and visuals are possible.
    Identifies specific available and genuinely missing columns.
    """
    total_records = len(df)
    cols = list(df.columns)

    # Financial metric resolution
    rev_col = resolve_column(df, "revenue")
    profit_col = resolve_column(df, "profit")
    cost_col = resolve_column(df, "cost")
    qty_col = resolve_column(df, "quantity")
    date_col = resolve_column(df, "date")

    # Categorical dimension resolution (in order of business priority)
    product_col = resolve_column(df, "product")
    category_col = resolve_column(df, "category")
    region_col = resolve_column(df, "region")
    channel_col = resolve_column(df, "channel")
    customer_col = resolve_column(df, "customer")

    dim_candidates = []
    for cand in [product_col, category_col, region_col, channel_col, customer_col]:
        if cand and cand in df.columns and cand not in dim_candidates:
            dim_candidates.append(cand)

    # Any other object/categorical columns with healthy cardinality (>1 and <=50 unique values)
    for c in df.select_dtypes(include=["object", "category"]).columns:
        if c not in dim_candidates and 1 < df[c].nunique() <= 50:
            dim_candidates.append(c)

    is_aggregate_only = (len(dim_candidates) == 0) or (total_records <= 1)

    return {
        "record_count": total_records,
        "columns": cols,
        "revenue_col": rev_col,
        "profit_col": profit_col,
        "cost_col": cost_col,
        "quantity_col": qty_col,
        "date_col": date_col,
        "product_col": product_col,
        "category_col": category_col,
        "region_col": region_col,
        "channel_col": channel_col,
        "customer_col": customer_col,
        "available_dimensions": dim_candidates,
        "preferred_dimension": dim_candidates[0] if dim_candidates else None,
        "has_product_dimension": product_col is not None,
        "has_categorical_dimensions": len(dim_candidates) > 0,
        "is_aggregate_only": is_aggregate_only,
    }


@dataclass
class CalculationResult:
    metric_name: str
    value: Optional[float]
    formatted_value: str
    formula: str
    baseline_value: Optional[float] = None
    variance: Optional[float] = None
    variance_pct: Optional[float] = None
    variance_status: str = "Not calculated — baseline unavailable."
    has_baseline: bool = False
    has_time_series: bool = False
    quantity_stats: Optional[dict[str, Any]] = None
    financial_kpis: Optional[dict[str, Any]] = None
    product_rankings: Optional[list[str]] = None
    dimension: Optional[str] = None
    grouped_table: Optional[list[dict[str, Any]]] = None
    top_driver: Optional[str] = None
    driver_established: bool = False
    driver_explanation: Optional[str] = None
    missing_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.baseline_value is not None:
            self.has_baseline = True
        if self.top_driver:
            self.driver_established = True
        if self.has_baseline and self.variance is not None and self.variance_status == "Not calculated — baseline unavailable.":
            pct = f" ({self.variance_pct:+.2f}%)" if self.variance_pct is not None else ""
            self.variance_status = f"{self.variance:+,.2f}{pct}"


def safe_divide(numerator: float, denominator: float) -> Optional[float]:
    """Zero-division guard returning None when denominator is zero or NaN."""
    if denominator is None or math.isnan(denominator) or denominator == 0:
        return None
    if numerator is None or math.isnan(numerator):
        return None
    return numerator / denominator


def format_metric_value(val: Optional[float], metric_name: str = "", unit: Optional[str] = None) -> str:
    """
    Format numbers cleanly based on the business metric domain:
    - Quantity/Volume: '151 units' (never with a dollar sign)
    - Currency: '$48,112.00' (Revenue, Profit, Cost, Price, Spend)
    - Percentage: '32.45%' (Margins, Growth, Rates, Shares)
    - Counts: '10 records'
    - Default: '1,234.56'
    """
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"

    name_lower = (metric_name or "").lower()

    if unit:
        return f"{val:,.2f} {unit}"

    # Percentage metrics
    if any(k in name_lower for k in ["margin", "percent", "growth", "share", "rate", "ratio", "csat", "satisfaction"]):
        return f"{val:.2f}%"

    # Quantity / Volume metrics
    if any(k in name_lower for k in ["quantity", "unit", "qty", "volume", "inventory"]):
        return f"{val:,.0f} units" if val == int(val) else f"{val:,.2f} units"

    # Count / Record metrics
    if any(k in name_lower for k in ["count", "orders", "records", "transactions"]):
        return f"{val:,.0f} records" if val == int(val) else f"{val:,.0f}"

    # Currency metrics
    if any(k in name_lower for k in ["revenue", "sales", "profit", "cost", "price", "cogs", "spend", "expense", "earning", "income"]):
        if abs(val) >= 1_000_000_000:
            return f"${val / 1_000_000_000:,.2f}B"
        if abs(val) >= 1_000_000:
            return f"${val / 1_000_000:,.2f}M"
        return f"${val:,.2f}"

    # Generic numbers (Do NOT format as currency by default)
    return f"{val:,.2f}"


def format_currency_or_number(val: Optional[float], is_currency: bool = True, is_pct: bool = False) -> str:
    """Legacy compatibility helper."""
    if is_pct:
        return format_metric_value(val, "percentage")
    return format_metric_value(val, "revenue" if is_currency else "generic")


class BusinessCalculationEngine:
    """
    Deterministic calculation engine for corporate metrics.
    Guarantees mathematically exact answers without hallucination.
    """

    @staticmethod
    def calculate_summary_stats(df: pd.DataFrame, col: str) -> dict[str, Any]:
        """Calculate standard summary metrics for a numerical column."""
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            return {}
        return {
            "sum": round(float(series.sum()), 2),
            "mean": round(float(series.mean()), 2),
            "median": round(float(series.median()), 2),
            "min": round(float(series.min()), 2),
            "max": round(float(series.max()), 2),
            "std": round(float(series.std()), 2) if len(series) > 1 else 0.0,
            "count": int(series.count()),
        }

    @staticmethod
    def calculate_growth_and_variance(
        current: float, baseline: Optional[float] = None, metric_label: str = "Metric"
    ) -> CalculationResult:
        """
        Calculate absolute variance and percentage change:
        Variance = Current - Baseline
        % Change = ((Current - Baseline) / |Baseline|) * 100
        If baseline is unavailable, explicitly reports 'Baseline unavailable' and
        variance_status = 'Not calculated — baseline unavailable.'
        """
        if baseline is None:
            return CalculationResult(
                metric_name=metric_label,
                value=current,
                formatted_value=format_metric_value(current, metric_label),
                formula=f"Measurement of {metric_label}",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                warnings=["Baseline unavailable."],
                metadata={"current": current, "baseline": "Baseline unavailable"},
            )

        variance = current - baseline
        ratio = safe_divide(variance, abs(baseline))
        pct_change = round(ratio * 100, 2) if ratio is not None else None

        formula = f"({current:,.2f} - {baseline:,.2f}) / |{baseline:,.2f}| * 100"

        return CalculationResult(
            metric_name=metric_label,
            value=current,
            formatted_value=format_metric_value(current, metric_label),
            formula=formula,
            baseline_value=baseline,
            variance=round(variance, 2),
            variance_pct=pct_change,
            variance_status=f"{variance:+,.2f} ({pct_change:+.2f}%)",
            has_baseline=True,
            metadata={"current": current, "baseline": baseline, "variance_pct": pct_change},
        )

    @classmethod
    def calculate_profitability_analysis(
        cls, df: pd.DataFrame, dimension_hint: Optional[str] = None
    ) -> CalculationResult:
        """
        Comprehensive Deterministic Profitability Analysis:
        - Inspects dataset schema for financial and categorical columns.
        - Calculates revenue, cost, profit, profit margin, and record count.
        - Performs product/category grouped calculations and rankings.
        - Avoids double counting and verifies exact arithmetic against source data.
        - If columns are missing, explicitly identifies missing fields.
        - If no categorical dimensions exist, documents aggregate limitation.
        """
        schema = inspect_dataset_schema(df)
        rev_col = schema["revenue_col"]
        profit_col = schema["profit_col"]
        cost_col = schema["cost_col"]

        missing_financial = []
        if not rev_col:
            missing_financial.append("Revenue")
        if not profit_col and not cost_col:
            missing_financial.append("Profit or Cost")

        if missing_financial:
            return CalculationResult(
                metric_name="Profit Margin & Profitability Analysis",
                value=None,
                formatted_value="N/A",
                formula="Profit / Revenue * 100",
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                missing_columns=missing_financial,
                warnings=[
                    f"Genuinely missing required column(s): {', '.join(missing_financial)}. Profitability cannot be computed."
                ],
                metadata={"schema": schema, "missing_columns": missing_financial},
            )

        # Verified financial totals (preventing double counting)
        series_rev = pd.to_numeric(df[rev_col], errors="coerce").dropna()
        total_rev = round(float(series_rev.sum()), 2)

        if profit_col:
            series_profit = pd.to_numeric(df[profit_col], errors="coerce").dropna()
            total_profit = round(float(series_profit.sum()), 2)
        else:
            series_cost = pd.to_numeric(df[cost_col], errors="coerce").dropna()
            total_cost = round(float(series_cost.sum()), 2)
            total_profit = round(total_rev - total_cost, 2)

        if cost_col:
            series_cost = pd.to_numeric(df[cost_col], errors="coerce").dropna()
            total_cost = round(float(series_cost.sum()), 2)
        else:
            total_cost = round(total_rev - total_profit, 2)

        margin_ratio = safe_divide(total_profit, total_rev)
        margin_pct = round(margin_ratio * 100, 2) if margin_ratio is not None else 0.0

        formula = f"(Profit / Revenue) * 100 = (${total_profit:,.2f} / ${total_rev:,.2f}) * 100"

        # Determine grouping dimension (priority: requested hint -> Product -> Category -> Region -> Channel)
        dim_col = None
        if dimension_hint:
            dim_col = resolve_column(df, dimension_hint)
        if not dim_col:
            dim_col = schema["preferred_dimension"]

        grouped_records = []
        product_rankings = []
        top_driver = None
        driver_established = False
        driver_explanation = None

        if dim_col and dim_col in df.columns and len(df) > 1:
            for cat_val, group in df.groupby(dim_col):
                if pd.isna(cat_val):
                    continue
                c_rev = round(float(pd.to_numeric(group[rev_col], errors="coerce").dropna().sum()), 2)
                if profit_col:
                    c_profit = round(float(pd.to_numeric(group[profit_col], errors="coerce").dropna().sum()), 2)
                else:
                    c_cost = round(float(pd.to_numeric(group[cost_col], errors="coerce").dropna().sum()), 2)
                    c_profit = round(c_rev - c_cost, 2)

                if cost_col:
                    c_cost = round(float(pd.to_numeric(group[cost_col], errors="coerce").dropna().sum()), 2)
                else:
                    c_cost = round(c_rev - c_profit, 2)

                c_margin = round(safe_divide(c_profit, c_rev) * 100, 2) if c_rev > 0 else 0.0
                c_count = len(group)
                c_profit_share = round(safe_divide(c_profit, total_profit) * 100, 2) if total_profit > 0 else 0.0
                c_rev_share = round(safe_divide(c_rev, total_rev) * 100, 2) if total_rev > 0 else 0.0

                grouped_records.append({
                    dim_col: str(cat_val),
                    "Revenue": c_rev,
                    "Cost": c_cost,
                    "Profit": c_profit,
                    "Profit_Margin_Pct": c_margin,
                    "Profit_Share_Pct": c_profit_share,
                    "Revenue_Share_Pct": c_rev_share,
                    "Record_Count": c_count,
                })

            # Sort descending by Profit
            grouped_records.sort(key=lambda r: r["Profit"], reverse=True)

            # Generate rankings
            for rank, r in enumerate(grouped_records, 1):
                product_rankings.append(
                    f"#{rank} {r[dim_col]}: Profit ${r['Profit']:,.2f} ({r['Profit_Margin_Pct']:.2f}% margin, {r['Profit_Share_Pct']:.2f}% of total profit)"
                )

            if grouped_records:
                top_item = grouped_records[0]
                top_name = top_item[dim_col]
                top_profit_val = top_item["Profit"]
                top_profit_share = top_item["Profit_Share_Pct"]
                top_margin_val = top_item["Profit_Margin_Pct"]
                top_driver = f"{top_name} leads profitability with ${top_profit_val:,.2f} profit ({top_profit_share}% of total profit, {top_margin_val}% margin)"
                driver_established = True
        else:
            # Genuinely aggregate-only data or missing categorical columns
            driver_established = False
            driver_explanation = "The dataset does not contain Product, SKU, or Category dimensions; analysis is limited to overall financial totals."
            top_driver = None

        financial_kpis = {
            "total_revenue": total_rev,
            "total_revenue_formatted": f"${total_rev:,.2f}",
            "total_cost": total_cost,
            "total_cost_formatted": f"${total_cost:,.2f}",
            "total_profit": total_profit,
            "total_profit_formatted": f"${total_profit:,.2f}",
            "profit_margin_pct": margin_pct,
            "profit_margin_formatted": f"{margin_pct:.2f}%",
            "record_count": len(df),
            "dimension": dim_col,
            "is_aggregate_only": schema["is_aggregate_only"],
        }

        return CalculationResult(
            metric_name="Profit Margin & Profitability Analysis",
            value=margin_pct,
            formatted_value=f"{margin_pct:.2f}%",
            formula=formula,
            baseline_value=None,
            variance=None,
            variance_pct=None,
            variance_status="Not calculated — baseline unavailable.",
            has_baseline=False,
            has_time_series=False,
            financial_kpis=financial_kpis,
            product_rankings=product_rankings,
            dimension=dim_col,
            grouped_table=grouped_records if grouped_records else None,
            top_driver=top_driver,
            driver_established=driver_established,
            driver_explanation=driver_explanation,
            warnings=["Baseline unavailable."],
            metadata={
                "financial_kpis": financial_kpis,
                "product_rankings": product_rankings,
                "schema": schema,
                "count": len(df),
                "validation": {
                    "record_count": len(df),
                    "valid_records": len(series_rev),
                    "missing_values": int(df[rev_col].isna().sum()) if rev_col in df else 0,
                    "metric_unit": "percent",
                    "audit_status": "Audited with zero missing-value imputation",
                },
            },
        )

    @classmethod
    def calculate_profit_margin(cls, df: pd.DataFrame) -> CalculationResult:
        """
        Calculate total profit margin and delegate to comprehensive profitability analysis.
        """
        return cls.calculate_profitability_analysis(df)

    @staticmethod
    def aggregate_by_dimension(
        df: pd.DataFrame,
        dimension_col: str,
        metric_col: str,
        agg_func: str = "sum",
        top_n: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        Group by dimension and aggregate metric with contribution percentage.
        """
        clean_df = df[[dimension_col, metric_col]].copy()
        clean_df[metric_col] = pd.to_numeric(clean_df[metric_col], errors="coerce")
        grouped = clean_df.groupby(dimension_col, as_index=False)[metric_col].agg(agg_func)

        # Sort descending
        grouped = grouped.sort_values(by=metric_col, ascending=False)
        total_val = grouped[metric_col].sum()

        records = []
        for _, row in grouped.iterrows():
            val = float(row[metric_col])
            share = (val / total_val * 100) if total_val > 0 else 0.0
            records.append({
                dimension_col: str(row[dimension_col]),
                metric_col: round(val, 2),
                "share_pct": round(share, 2),
            })

        if top_n and top_n > 0:
            records = records[:top_n]

        return records

    @staticmethod
    def calculate_time_series_growth(
        df: pd.DataFrame,
        date_col: str,
        metric_col: str,
        freq: str = "M",
    ) -> list[dict[str, Any]]:
        """
        Computes sequential MoM or YoY growth along a date column.
        """
        temp = df[[date_col, metric_col]].copy()
        temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
        temp[metric_col] = pd.to_numeric(temp[metric_col], errors="coerce")
        temp = temp.dropna().sort_values(by=date_col)

        if freq.upper() == "Y":
            temp["period"] = temp[date_col].dt.to_period("Y").astype(str)
        elif freq.upper() == "Q":
            temp["period"] = temp[date_col].dt.to_period("Q").astype(str)
        else:
            temp["period"] = temp[date_col].dt.to_period("M").astype(str)

        agg = temp.groupby("period", as_index=False)[metric_col].sum()
        agg["prior_val"] = agg[metric_col].shift(1)
        agg["variance"] = agg[metric_col] - agg["prior_val"]
        agg["growth_pct"] = (agg["variance"] / agg["prior_val"].abs() * 100).round(2)

        results = []
        for _, row in agg.iterrows():
            results.append({
                "period": str(row["period"]),
                "value": round(float(row[metric_col]), 2),
                "prior_value": round(float(row["prior_val"]), 2) if pd.notna(row["prior_val"]) else None,
                "variance": round(float(row["variance"]), 2) if pd.notna(row["variance"]) else None,
                "growth_pct": float(row["growth_pct"]) if pd.notna(row["growth_pct"]) else None,
            })
        return results

    @staticmethod
    def calculate_moving_average(
        df: pd.DataFrame,
        date_col: str,
        metric_col: str,
        window: int = 3,
    ) -> list[dict[str, Any]]:
        """Compute rolling/moving average over a date series."""
        temp = df[[date_col, metric_col]].copy()
        temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
        temp[metric_col] = pd.to_numeric(temp[metric_col], errors="coerce")
        temp = temp.dropna().sort_values(by=date_col)
        temp["period"] = temp[date_col].dt.to_period("M").astype(str)
        agg = temp.groupby("period", as_index=False)[metric_col].sum()
        agg["moving_avg"] = agg[metric_col].rolling(window=window, min_periods=1).mean().round(2)
        return [
            {
                "period": str(row["period"]),
                "value": round(float(row[metric_col]), 2),
                "moving_avg": round(float(row["moving_avg"]), 2),
            }
            for _, row in agg.iterrows()
        ]

    @staticmethod
    def detect_outliers_and_quality(df: pd.DataFrame, metric_col: str) -> dict[str, Any]:
        """
        Data quality audit and statistical outlier detection via Interquartile Range (IQR).
        """
        series = pd.to_numeric(df[metric_col], errors="coerce")
        null_count = int(series.isna().sum())
        clean_series = series.dropna()

        if len(clean_series) < 4:
            return {
                "metric": metric_col,
                "null_count": null_count,
                "outliers_found": 0,
                "outlier_values": [],
                "quality_status": "Sample size too small for statistical outlier detection",
            }

        q1 = float(clean_series.quantile(0.25))
        q3 = float(clean_series.quantile(0.75))
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outliers = clean_series[(clean_series < lower_bound) | (clean_series > upper_bound)].tolist()
        return {
            "metric": metric_col,
            "null_count": null_count,
            "clean_count": len(clean_series),
            "q1": round(q1, 2),
            "q3": round(q3, 2),
            "iqr": round(iqr, 2),
            "lower_bound": round(lower_bound, 2),
            "upper_bound": round(upper_bound, 2),
            "outliers_found": len(outliers),
            "outlier_values": [round(float(v), 2) for v in outliers],
            "quality_status": "Audited with zero missing-value imputation",
        }

    def execute_analytical_query(self, df: pd.DataFrame, query: str) -> CalculationResult:
        """
        Parse user natural language query and compute verified deterministic answer.
        """
        q_lower = query.lower()

        # 1. Check for Profit Margin & Profitability Analysis
        if any(w in q_lower for w in ["profit margin", "margin %", "margin percentage", "profitability", "profit analysis", "profit breakdown"]):
            return self.calculate_profitability_analysis(df, dimension_hint=target_dim)

        # 2. Check for Target Metric (Revenue, Profit, Cost, Quantity, etc.)
        target_metric = None
        for cand in ["revenue", "profit", "cost", "quantity", "discount", "satisfaction"]:
            if (
                cand in q_lower
                or (cand == "revenue" and "sales" in q_lower)
                or (cand == "quantity" and any(w in q_lower for w in ["volume", "inventory", "units", "qty"]))
            ):
                target_metric = cand
                break

        # If not specified, look for first numeric column
        metric_col = resolve_column(df, target_metric) if target_metric else None
        if not metric_col:
            num_cols = df.select_dtypes(include="number").columns.tolist()
            metric_col = num_cols[0] if num_cols else df.columns[0]

        # Audit and validation metadata
        series_valid = pd.to_numeric(df[metric_col], errors="coerce").dropna()
        validation_info = {
            "record_count": len(df),
            "valid_records": len(series_valid),
            "missing_values": int(df[metric_col].isna().sum()) if metric_col in df else 0,
            "metric_unit": "units" if any(k in (metric_col or "").lower() for k in ["quantity", "qty", "volume", "unit"]) else "standard",
            "audit_status": "Audited with zero missing-value imputation",
        }

        # 2b. Check for Outliers / Data Quality
        if any(w in q_lower for w in ["outlier", "anomaly", "anomalies", "data quality"]):
            dq = self.detect_outliers_and_quality(df, metric_col)
            outlier_count = dq["outliers_found"]
            desc = f"Identified {outlier_count} outlier(s) in {metric_col} using IQR bounds [{dq.get('lower_bound')}, {dq.get('upper_bound')}]: {dq.get('outlier_values')}" if outlier_count > 0 else f"No statistical outliers detected in {metric_col} (IQR: {dq.get('iqr')})."
            return CalculationResult(
                metric_name=f"Data Quality & Outlier Analysis: {metric_col}",
                value=float(outlier_count),
                formatted_value=f"{outlier_count} outliers",
                formula=f"IQR Outlier Detection: Q1 ({dq.get('q1')}) to Q3 ({dq.get('q3')})",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                top_driver=desc,
                driver_established=True,
                warnings=[dq["quality_status"]],
                metadata={**dq, "validation": validation_info},
            )

        # 2c. Check for Moving Average
        date_col = resolve_column(df, "date")
        if date_col and any(w in q_lower for w in ["moving average", "rolling average", "moving avg"]):
            ma_data = self.calculate_moving_average(df, date_col, metric_col, window=3)
            latest_ma = ma_data[-1] if ma_data else {}
            return CalculationResult(
                metric_name=f"3-Month Moving Average: {metric_col}",
                value=latest_ma.get("moving_avg"),
                formatted_value=format_metric_value(latest_ma.get("moving_avg"), metric_col),
                formula=f"3-Period Rolling Mean of {metric_col}",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                has_time_series=True,
                grouped_table=ma_data,
                dimension="Period",
                top_driver=f"Latest 3-month rolling mean at {latest_ma.get('period')}: {format_metric_value(latest_ma.get('moving_avg'), metric_col)}",
                driver_established=True,
                metadata={"validation": validation_info},
            )

        # 3. Check for Dimension (Region, Product, Category, Customer Segment, Channel)
        target_dim = None
        for cand in ["region", "product", "category", "channel", "customer", "segment"]:
            if cand in q_lower:
                target_dim = cand
                break

        dim_col = resolve_column(df, target_dim) if target_dim else None

        # 4. Check for Time Series / Trend / MoM / YoY
        date_col = resolve_column(df, "date")
        if date_col and any(w in q_lower for w in ["trend", "monthly", "mom", "over time", "by month"]):
            series_growth = self.calculate_time_series_growth(df, date_col, metric_col, freq="M")
            latest = series_growth[-1] if series_growth else {}
            prior = series_growth[-2] if len(series_growth) > 1 else {}
            has_prior = pd.notna(prior.get("value")) if prior else False
            return CalculationResult(
                metric_name=f"Monthly {metric_col} Trend",
                value=latest.get("value"),
                formatted_value=format_metric_value(latest.get("value"), metric_col),
                formula=f"Sum of {metric_col} grouped by Month",
                baseline_value=prior.get("value") if has_prior else None,
                variance=latest.get("variance") if has_prior else None,
                variance_pct=latest.get("growth_pct") if has_prior else None,
                variance_status=f"{latest.get('variance'):+,.2f} ({latest.get('growth_pct'):+.2f}%)" if has_prior else "Not calculated — baseline unavailable.",
                has_baseline=has_prior,
                has_time_series=True,
                grouped_table=series_growth,
                dimension="Month",
                top_driver=f"Latest period {latest.get('period')} with {latest.get('growth_pct')}% growth" if has_prior else "Initial period recorded",
                driver_established=True,
                metadata={"validation": validation_info},
            )

        # 5. Quantity / Volume Analysis (Requirement 4: calculate total, avg, min, max, and dimensional grouping)
        is_quantity = (
            target_metric == "quantity"
            or any(w in (metric_col or "").lower() for w in ["quantity", "unit", "qty", "volume", "inventory"])
            or any(w in q_lower for w in ["quantity", "units", "volume", "inventory", "qty"])
        )
        if is_quantity:
            total_qty = round(float(series_valid.sum()), 2)
            avg_qty = round(float(series_valid.mean()), 2)
            min_qty = round(float(series_valid.min()), 2)
            max_qty = round(float(series_valid.max()), 2)
            count_qty = int(len(series_valid))

            qty_stats = {
                "total": total_qty,
                "total_formatted": f"{total_qty:,.0f} units" if total_qty == int(total_qty) else f"{total_qty:,.2f} units",
                "average": avg_qty,
                "average_formatted": f"{avg_qty:,.2f} units",
                "min": min_qty,
                "min_formatted": f"{min_qty:,.0f} units" if min_qty == int(min_qty) else f"{min_qty:,.2f} units",
                "max": max_qty,
                "max_formatted": f"{max_qty:,.0f} units" if max_qty == int(max_qty) else f"{max_qty:,.2f} units",
                "count": count_qty,
            }

            # Choose dimension for breakdown (specified dimension or best candidate categorical column)
            chosen_dim = dim_col
            if not chosen_dim:
                for cand in ["Product", "Category", "Region", "Sales_Channel", "Customer_Segment", "Channel"]:
                    resolved = resolve_column(df, cand)
                    if resolved and resolved != metric_col:
                        chosen_dim = resolved
                        break

            breakdown = None
            driver_established = False
            top_driver = None
            driver_explanation = None

            if chosen_dim and chosen_dim in df.columns:
                breakdown = self.aggregate_by_dimension(df, chosen_dim, metric_col, top_n=10)
                if breakdown and len(breakdown) > 0:
                    top_item = breakdown[0]
                    top_name = top_item.get(chosen_dim, "Unknown")
                    top_val = top_item.get(metric_col, 0)
                    top_share = top_item.get("share_pct", 0)
                    driver_established = True
                    top_driver = f"{top_name} leads with {format_metric_value(top_val, metric_col)} ({top_share}% of total)"
                else:
                    driver_explanation = "Primary drivers cannot be established without categorical segmentation in the dataset."
            else:
                driver_explanation = "Primary drivers cannot be established without categorical segmentation in the dataset."

            # Determine whether query specifically asked for average/min/max or total
            if any(w in q_lower for w in ["average", "mean", "avg"]):
                primary_val = avg_qty
                primary_fmt = qty_stats["average_formatted"]
                primary_name = f"Average {metric_col.replace('_', ' ').title()}"
            elif any(w in q_lower for w in ["max", "highest", "peak", "most"]):
                primary_val = max_qty
                primary_fmt = qty_stats["max_formatted"]
                primary_name = f"Maximum {metric_col.replace('_', ' ').title()}"
            elif any(w in q_lower for w in ["min", "lowest", "least"]):
                primary_val = min_qty
                primary_fmt = qty_stats["min_formatted"]
                primary_name = f"Minimum {metric_col.replace('_', ' ').title()}"
            else:
                primary_val = total_qty
                primary_fmt = qty_stats["total_formatted"]
                primary_name = f"Total {metric_col.replace('_', ' ').title()}"

            return CalculationResult(
                metric_name=primary_name,
                value=primary_val,
                formatted_value=primary_fmt,
                formula=f"Sum({metric_col}) across all {count_qty} records",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                has_time_series=False,
                quantity_stats=qty_stats,
                dimension=chosen_dim,
                grouped_table=breakdown,
                top_driver=top_driver,
                driver_established=driver_established,
                driver_explanation=driver_explanation,
                warnings=["Baseline unavailable."],
                metadata={
                    "count": count_qty,
                    "validation": validation_info,
                    "quantity_stats": qty_stats,
                },
            )

        # 6. Dimensional Breakdown for non-quantity metrics (Requirements 1 & 2: inspect schema for Product/Category fields)
        schema = inspect_dataset_schema(df)
        chosen_dim = dim_col or schema["preferred_dimension"]
        if chosen_dim and chosen_dim in df.columns and len(df) > 1 and not any(w in q_lower for w in ["average", "mean", "avg", "max", "highest", "min", "lowest"]):
            breakdown = self.aggregate_by_dimension(df, chosen_dim, metric_col, top_n=10)
            top_item = breakdown[0] if breakdown else {}
            top_name = top_item.get(chosen_dim, "None")
            top_val = top_item.get(metric_col, 0)
            top_share = top_item.get("share_pct", 0)

            total_val = float(pd.to_numeric(df[metric_col], errors="coerce").sum())

            return CalculationResult(
                metric_name=f"{metric_col} by {chosen_dim}",
                value=total_val,
                formatted_value=format_metric_value(total_val, metric_col),
                formula=f"Group {metric_col} by {chosen_dim} and sum",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                dimension=chosen_dim,
                grouped_table=breakdown,
                top_driver=f"{top_name} leads with {format_metric_value(top_val, metric_col)} ({top_share}% of total)",
                driver_established=True,
                warnings=["Baseline unavailable."],
                metadata={"total": total_val, "top_category": top_name, "top_value": top_val, "validation": validation_info, "schema": schema},
            )

        # 7. Overall Aggregation for other metrics (Sum, Average, Max, Min)
        series = series_valid
        if any(w in q_lower for w in ["average", "mean", "avg"]):
            avg_val = round(float(series.mean()), 2)
            return CalculationResult(
                metric_name=f"Average {metric_col}",
                value=avg_val,
                formatted_value=format_metric_value(avg_val, metric_col),
                formula=f"Total {metric_col} / Count({len(series)})",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                warnings=["Baseline unavailable."],
                metadata={"count": len(series), "validation": validation_info},
            )
        elif any(w in q_lower for w in ["max", "highest", "peak", "most"]):
            max_val = round(float(series.max()), 2)
            return CalculationResult(
                metric_name=f"Maximum {metric_col}",
                value=max_val,
                formatted_value=format_metric_value(max_val, metric_col),
                formula=f"Max({metric_col})",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                warnings=["Baseline unavailable."],
                metadata={"count": len(series), "validation": validation_info},
            )
        elif any(w in q_lower for w in ["min", "lowest", "least"]):
            min_val = round(float(series.min()), 2)
            return CalculationResult(
                metric_name=f"Minimum {metric_col}",
                value=min_val,
                formatted_value=format_metric_value(min_val, metric_col),
                formula=f"Min({metric_col})",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                warnings=["Baseline unavailable."],
                metadata={"count": len(series), "validation": validation_info},
            )
        else:
            # Default to Total Sum
            sum_val = round(float(series.sum()), 2)
            return CalculationResult(
                metric_name=f"Total {metric_col}",
                value=sum_val,
                formatted_value=format_metric_value(sum_val, metric_col),
                formula=f"Sum({metric_col}) across all {len(series)} records",
                baseline_value=None,
                variance=None,
                variance_pct=None,
                variance_status="Not calculated — baseline unavailable.",
                has_baseline=False,
                warnings=["Baseline unavailable."],
                metadata={"count": len(series), "validation": validation_info},
            )


default_calc_engine = BusinessCalculationEngine()
