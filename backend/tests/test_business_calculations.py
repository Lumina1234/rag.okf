"""
Unit tests for Deterministic Business Calculation Engine and Business Explainer.
Validates exact arithmetic, zero-division guards, column resolution, and executive formatting.
"""
from pathlib import Path
import pandas as pd
import pytest

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.analytics.calculation_engine import (
    BusinessCalculationEngine,
    CalculationResult,
    default_calc_engine,
    resolve_column,
    safe_divide,
    format_currency_or_number,
)
from services.analytics.business_explainer import BusinessExplainer, default_explainer


@pytest.fixture
def sample_business_df():
    """Load or generate standard corporate dataset."""
    fixture_path = Path(__file__).parent / "fixtures" / "b8a425cc_business_analytics_10_samples.csv"
    csv_path = fixture_path if fixture_path.exists() else (Path(__file__).parent.parent / "uploads" / "16" / "b8a425cc_business_analytics_10_samples.csv")
    if csv_path.exists():
        return pd.read_csv(csv_path)
    # Synthetic fallback matching the exact schema
    return pd.DataFrame({
        "Order_ID": ["ORD-1", "ORD-2", "ORD-3"],
        "Order_Date": ["2026-01-01", "2026-02-01", "2026-03-01"],
        "Region": ["North", "South", "North"],
        "Revenue": [10000.0, 20000.0, 15000.0],
        "Cost": [6000.0, 12000.0, 9000.0],
        "Profit": [4000.0, 8000.0, 6000.0],
    })


def test_column_synonym_resolution(sample_business_df):
    """Verify fuzzy mapping from conversational terms to actual dataframe columns."""
    assert resolve_column(sample_business_df, "sales") == "Revenue"
    assert resolve_column(sample_business_df, "earnings") == "Profit"
    assert resolve_column(sample_business_df, "expenses") == "Cost"
    assert resolve_column(sample_business_df, "region") == "Region"


def test_zero_division_guard():
    """Verify division by zero safely returns None without throwing ZeroDivisionError."""
    assert safe_divide(100.0, 0.0) is None
    assert safe_divide(100.0, None) is None
    assert safe_divide(50.0, 2.0) == 25.0


def test_growth_and_variance():
    """Verify exact formula: Variance = Current - Baseline, % Change = (Variance / |Baseline|) * 100."""
    res = default_calc_engine.calculate_growth_and_variance(120.0, 100.0, "Revenue")
    assert res.variance == 20.0
    assert res.variance_pct == 20.0
    assert res.baseline_value == 100.0

    # Negative growth
    res_neg = default_calc_engine.calculate_growth_and_variance(80.0, 100.0, "Profit")
    assert res_neg.variance == -20.0
    assert res_neg.variance_pct == -20.0


def test_profit_margin_calculation(sample_business_df):
    """Verify exact Profit Margin: (Total Profit / Total Revenue) * 100."""
    res = default_calc_engine.calculate_profit_margin(sample_business_df)
    total_rev = sample_business_df["Revenue"].sum()
    total_profit = sample_business_df["Profit"].sum()
    expected_margin = round((total_profit / total_rev) * 100, 2)

    assert res.value == expected_margin
    assert "%" in res.formatted_value
    assert "Profit / Revenue" in res.formula or str(round(total_rev, 2)) in res.formula


def test_dimensional_aggregation(sample_business_df):
    """Verify group-by aggregation with descending sort and percentage share."""
    breakdown = default_calc_engine.aggregate_by_dimension(
        sample_business_df,
        dimension_col="Region",
        metric_col="Revenue",
    )
    assert len(breakdown) > 0
    # Top record has largest revenue
    assert breakdown[0]["Revenue"] >= breakdown[-1]["Revenue"]
    total_share = sum(item["share_pct"] for item in breakdown)
    assert pytest.approx(total_share, rel=1e-1) == 100.0


def test_business_explainer_formatting():
    """Verify markdown report generation contains executive summary and methodology."""
    calc_res = CalculationResult(
        metric_name="Total Revenue",
        value=48112.0,
        formatted_value="$48,112.00",
        formula="Sum(Revenue) across 10 records",
        baseline_value=40000.0,
        variance=8112.0,
        variance_pct=20.28,
        top_driver="Standing Desk generated $34,938.00 (72.6% of total)",
    )

    report = default_explainer.format_markdown_report(calc_res, "What was total revenue?")
    assert "### 📊 Executive Summary: Total Revenue" in report
    assert "$48,112.00" in report
    assert "8,112.00" in report
    assert "20.28%" in report
    assert "Methodology" in report
    assert "Standing Desk" in report


def test_moving_average_calculation(sample_business_df):
    """Verify rolling moving average computation."""
    ma = default_calc_engine.calculate_moving_average(
        sample_business_df,
        date_col="Order_Date",
        metric_col="Revenue",
        window=2,
    )
    assert len(ma) > 0
    assert "moving_avg" in ma[0]
    assert ma[0]["moving_avg"] > 0


def test_outlier_detection_and_data_quality(sample_business_df):
    """Verify IQR statistical outlier detection."""
    dq = default_calc_engine.detect_outliers_and_quality(sample_business_df, "Revenue")
    assert "outliers_found" in dq
    assert "iqr" in dq
    assert dq["clean_count"] == len(sample_business_df)
