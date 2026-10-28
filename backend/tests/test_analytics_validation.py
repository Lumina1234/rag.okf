"""
Regression tests for Deterministic Analytics Pipeline and Validation Layer.
Verifies compliance with strict business intelligence rules:
  1. Missing baseline: reports 'Variance: Not calculated — baseline unavailable.' (never 0% variance)
  2. Unsupported stability claims: detected and corrected
  3. Metric units: quantity formatted with 'units' (never '$')
  4. Valid comparison: computes exact variance when baseline is provided
  5. Insufficient data & driver limitation explanations
  6. Acceptance criteria: 10 records with 151 units reports 'Total quantity: 151 units'
     and 'Variance: Not calculated — baseline unavailable.' with no 'Variance: 0%' or 'stable volume'.
  7. Backend privacy and prompt leakage sanitization.
"""
from pathlib import Path
import pandas as pd
import pytest

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.analytics import (
    BusinessCalculationEngine,
    CalculationResult,
    default_calc_engine,
    BusinessExplainer,
    default_explainer,
    AnalyticsResponseValidator,
    default_analytics_validator,
    format_metric_value,
)


@pytest.fixture
def ten_records_151_units_df():
    """Load or generate the 10-record dataset with total quantity of 151 units."""
    fixture_path = Path(__file__).parent / "fixtures" / "b8a425cc_business_analytics_10_samples.csv"
    csv_path = fixture_path if fixture_path.exists() else (Path(__file__).parent.parent / "uploads" / "16" / "b8a425cc_business_analytics_10_samples.csv")
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        if "Quantity" in df.columns and df["Quantity"].sum() == 151:
            return df
    # Synthetic fallback matching the exact schema
    return pd.DataFrame({
        "Order_ID": [f"ORD-{i}" for i in range(10)],
        "Product": ["Desk", "Headphones", "Desk", "Coffee", "Desk", "Headphones", "Desk", "Coffee", "Desk", "Monitor"],
        "Category": ["Furniture", "Electronics", "Furniture", "Appliances", "Furniture", "Electronics", "Furniture", "Appliances", "Furniture", "Electronics"],
        "Quantity": [2, 20, 8, 10, 21, 22, 14, 24, 22, 8],  # Sum = 151
        "Revenue": [100.0 * q for q in [2, 20, 8, 10, 21, 22, 14, 24, 22, 8]],
    })


def test_missing_baseline_variance_reported_as_unavailable():
    """
    Requirement 1: Never calculate or report zero variance without a valid baseline.
    If no baseline exists, return 'Baseline unavailable' and 'Variance: Not calculated — baseline unavailable.'
    """
    res = default_calc_engine.calculate_growth_and_variance(151.0, baseline=None, metric_label="Quantity")
    assert res.baseline_value is None
    assert res.variance is None
    assert res.variance_pct is None
    assert res.has_baseline is False
    assert res.variance_status == "Not calculated — baseline unavailable."
    assert "Baseline unavailable." in res.warnings

    report = default_explainer.format_markdown_report(res, "Analyze quantity")
    assert "Variance: Not calculated — baseline unavailable." in report
    assert "Variance: 0%" not in report
    assert "0% variance" not in report


def test_unsupported_stability_claims_detected_and_corrected(ten_records_151_units_df):
    """
    Requirement 2 & 7: Never describe a metric as stable or consistent over time
    unless time-series analysis was performed. Deterministic validator must detect and correct.
    """
    res = default_calc_engine.execute_analytical_query(ten_records_151_units_df, "Inventory & Volume Analysis")
    assert res.has_time_series is False

    # Simulate an LLM hallucination claiming stable volume and consistent trend
    hallucinated_text = (
        "### Executive Summary\n"
        "- Total quantity: 151 units\n"
        "- Baseline Comparison: The data shows 0% variance\n"
        "- Trends: The data indicates a stable volume across the analyzed periods.\n"
        "Performance reflects a stable volume over time."
    )

    sanitized, corrections = default_analytics_validator.validate_and_sanitize(hallucinated_text, res)

    # Must NOT contain stable volume or 0% variance
    assert "stable volume" not in sanitized
    assert "0% variance" not in sanitized
    assert "Variance: Not calculated — baseline unavailable." in sanitized
    assert "historical stability or trend cannot be established from standalone records" in sanitized
    assert len(corrections) > 0


def test_metric_unit_verification_quantity_vs_currency():
    """
    Requirement 6: Quantity must be formatted with 'units', never currency symbols ($).
    """
    assert format_metric_value(151.0, "Quantity") == "151 units"
    assert format_metric_value(151.0, "volume") == "151 units"
    assert format_metric_value(151.0, "revenue") == "$151.00"

    # Validator correction of mistyped currency unit in quantity
    calc_res = CalculationResult(
        metric_name="Total Quantity",
        value=151.0,
        formatted_value="151 units",
        formula="Sum(Quantity)",
        baseline_value=None,
        has_baseline=False,
    )
    raw_text = "- Total quantity: $151 units\n- Measured: $151.00 units"
    sanitized, _ = default_analytics_validator.validate_and_sanitize(raw_text, calc_res)
    assert "$151" not in sanitized
    assert "151 units" in sanitized


def test_valid_comparison_with_baseline():
    """
    Requirement 1 & 9: When a valid baseline exists, variance is calculated accurately.
    """
    res = default_calc_engine.calculate_growth_and_variance(120.0, baseline=100.0, metric_label="Revenue")
    assert res.has_baseline is True
    assert res.variance == 20.0
    assert res.variance_pct == 20.0
    assert res.baseline_value == 100.0
    assert "+20.00 (+20.00%)" in res.variance_status

    report = default_explainer.format_markdown_report(res, "Revenue comparison")
    assert "+20.00" in report
    assert "+20.00%" in report
    assert "against baseline `100.00`" in report


def test_insufficient_data_and_driver_limitation():
    """
    Requirement 5: If data cannot establish drivers (e.g. no categorical dimensions),
    explain that limitation rather than inventing drivers.
    """
    scalar_df = pd.DataFrame({"Quantity": [10, 20, 30]})
    res = default_calc_engine.execute_analytical_query(scalar_df, "Analyze quantity drivers")

    assert res.driver_established is False
    assert res.top_driver is None
    assert "Primary drivers cannot be established" in (res.driver_explanation or "")

    report = default_explainer.format_markdown_report(res, "Analyze quantity drivers")
    assert "Primary drivers cannot be established" in report


def test_quantity_questions_calculate_all_statistics(ten_records_151_units_df):
    """
    Requirement 4: For quantity questions, calculate total, average, minimum, maximum,
    and quantity grouped by relevant available dimensions.
    """
    res = default_calc_engine.execute_analytical_query(ten_records_151_units_df, "What is the total quantity and volume?")

    assert res.quantity_stats is not None
    stats = res.quantity_stats
    assert stats["total"] == 151.0
    assert stats["total_formatted"] == "151 units"
    assert stats["average"] == 15.1
    assert stats["min"] == 2.0
    assert stats["max"] == 24.0
    assert stats["count"] == 10

    # Dimensional grouping by product
    assert res.dimension is not None
    assert res.grouped_table is not None
    assert len(res.grouped_table) > 0
    assert res.driver_established is True
    assert "leads with" in (res.top_driver or "")


def test_acceptance_criteria_10_records_151_units(ten_records_151_units_df):
    """
    ACCEPTANCE TEST:
    Given 10 records with a total quantity of 151 units and no baseline:
    The response must report:
      - 'Total quantity: 151 units'
      - 'Variance: Not calculated — baseline unavailable.'
    It must not claim zero variance or stable volume without supporting analysis.
    """
    res = default_calc_engine.execute_analytical_query(ten_records_151_units_df, "Inventory & Volume Analysis")
    raw_report = default_explainer.format_markdown_report(res, "Inventory & Volume Analysis")
    sanitized_response, _ = default_analytics_validator.validate_and_sanitize(
        raw_report, res, query="Inventory & Volume Analysis"
    )

    # 1. Must report Total quantity: 151 units
    assert "Total quantity: 151 units" in sanitized_response or "Total quantity: `151 units`" in sanitized_response

    # 2. Must report Variance: Not calculated — baseline unavailable.
    assert "Variance: Not calculated — baseline unavailable." in sanitized_response

    # 3. Must NOT claim zero variance
    assert "Variance: 0%" not in sanitized_response
    assert "0% variance" not in sanitized_response
    assert "zero variance" not in sanitized_response
    assert "0.00% variance" not in sanitized_response

    # 4. Must NOT claim stable volume
    assert "stable volume" not in sanitized_response


def test_backend_privacy_sanitization():
    """
    Requirement 8: Internal prompts, system headers, and private traces must be stripped.
    """
    calc_res = CalculationResult(
        metric_name="Total Quantity",
        value=151.0,
        formatted_value="151 units",
        formula="Sum(Quantity)",
        has_baseline=False,
    )
    leaked_text = (
        "System Prompt: You are an expert CFO...\n\n"
        "<think>Thinking about inventory stability...</think>\n"
        "### Executive Summary\n"
        "- Total quantity: 151 units\n"
        "- Baseline Comparison: Variance: Not calculated — baseline unavailable.\n"
    )
    sanitized, _ = default_analytics_validator.validate_and_sanitize(leaked_text, calc_res)

    assert "System Prompt:" not in sanitized
    assert "<think>" not in sanitized
    assert "</think>" not in sanitized
    assert "Thinking about inventory stability" not in sanitized
    assert "Total quantity: 151 units" in sanitized


# =========================================================================
# Profitability Analysis & Schema Profiling Regression Tests (Request 10)
# =========================================================================

@pytest.fixture
def sample_profitability_df():
    """10 sample records with Product, Category, Revenue, Cost, Profit."""
    return pd.DataFrame({
        "Order_ID": [f"ORD-{i}" for i in range(1, 11)],
        "Product": [
            "Standing Desk", "Ergonomic Chair", "Noise-Cancelling Headphones",
            "Standing Desk", "Wireless Keyboard", "Ergonomic Chair",
            "Standing Desk", "Coffee Maker", "Standing Desk", "27-inch 4K Monitor"
        ],
        "Category": [
            "Furniture", "Furniture", "Electronics",
            "Furniture", "Electronics", "Furniture",
            "Furniture", "Appliances", "Furniture", "Electronics"
        ],
        "Revenue": [1200.0, 450.0, 300.0, 1500.0, 100.0, 900.0, 1800.0, 200.0, 1400.0, 600.0],
        "Cost": [800.0, 300.0, 180.0, 1000.0, 60.0, 600.0, 1200.0, 120.0, 950.0, 420.0],
        "Profit": [400.0, 150.0, 120.0, 500.0, 40.0, 300.0, 600.0, 80.0, 450.0, 180.0],
    })


def test_profitability_with_product_columns(sample_profitability_df):
    """
    Requirements 1, 2, 3, 4, 7, 8:
    - Inspect dataset schema and use Product to group metrics.
    - Calculate revenue, cost, profit, profit margin, record count by product.
    - Produce ranked product list.
    - Deterministic profit margin = (Total Profit / Total Revenue) * 100.
    - Reports 'Variance: Not calculated — baseline unavailable.'
    """
    from services.analytics.calculation_engine import inspect_dataset_schema
    schema = inspect_dataset_schema(sample_profitability_df)
    assert schema["preferred_dimension"] == "Product"
    assert schema["is_aggregate_only"] is False
    assert schema["revenue_col"] == "Revenue"
    assert schema["profit_col"] == "Profit"
    assert schema["cost_col"] == "Cost"

    res = default_calc_engine.calculate_profitability_analysis(sample_profitability_df)

    # 1. Total financial calculations
    assert res.financial_kpis is not None
    kpis = res.financial_kpis
    assert kpis["total_revenue"] == 8450.0
    assert kpis["total_cost"] == 5630.0
    assert kpis["total_profit"] == 2820.0
    expected_margin = round((2820.0 / 8450.0) * 100, 2)  # 33.37%
    assert kpis["profit_margin_pct"] == expected_margin
    assert kpis["record_count"] == 10

    # 2. Product rankings
    assert res.product_rankings is not None
    assert len(res.product_rankings) == 6  # 6 distinct products
    assert "#1 Standing Desk" in res.product_rankings[0]

    # 3. Verified breakdown table
    assert res.grouped_table is not None
    standing_desk = next(r for r in res.grouped_table if r["Product"] == "Standing Desk")
    assert standing_desk["Revenue"] == 5900.0  # 1200 + 1500 + 1800 + 1400
    assert standing_desk["Profit"] == 1950.0   # 400 + 500 + 600 + 450
    assert standing_desk["Record_Count"] == 4

    # 4. Baseline unavailable
    assert res.has_baseline is False
    assert res.variance_status == "Not calculated — baseline unavailable."

    # 5. Formatted BI report
    report = default_explainer.format_markdown_report(res, "Profitability Analysis")
    assert "### 📊 Executive Summary: Profitability Analysis" in report or "Profit" in report
    assert "Overall Profit Margin" in report
    assert "Product Rankings" in report
    assert "#1 Standing Desk" in report
    assert "Variance: Not calculated — baseline unavailable." in report


def test_profitability_without_product_columns():
    """
    Requirements 5, 8, 9:
    If dataset lacks Product/Category columns, state specifically that Product
    and Category fields are not present in this dataset instead of claiming
    that the entire dataset contains aggregate figures only.
    """
    df_no_prod = pd.DataFrame({
        "Transaction_ID": [1, 2, 3, 4],
        "Revenue": [1000.0, 2000.0, 1500.0, 2500.0],
        "Cost": [600.0, 1200.0, 900.0, 1500.0],
        "Profit": [400.0, 800.0, 600.0, 1000.0],
    })
    res = default_calc_engine.calculate_profitability_analysis(df_no_prod)

    assert res.grouped_table is None
    assert res.driver_established is False
    assert "does not contain Product, SKU, or Category" in (res.driver_explanation or "")

    report = default_explainer.format_markdown_report(res, "Profitability Analysis")
    assert "does not contain Product, SKU, or Category" in report or "Product and Category fields are not present" in report
    assert "Variance: Not calculated — baseline unavailable." in report


def test_missing_financial_columns():
    """
    Requirement 5: If a required column is genuinely missing, state exactly
    which column is unavailable instead of claiming that the entire dataset
    contains aggregate figures only.
    """
    df_missing_rev = pd.DataFrame({
        "Product": ["A", "B"],
        "Quantity": [10, 20],
        "Cost": [50.0, 100.0],
    })
    res = default_calc_engine.calculate_profitability_analysis(df_missing_rev)

    assert "Revenue" in res.missing_columns
    assert any("Revenue" in w for w in res.warnings)

    report = default_explainer.format_markdown_report(res, "Profitability Analysis")
    assert "Revenue" in report
    assert "Genuinely missing required column(s)" in report


def test_aggregate_only_dataset():
    """
    Requirement 1, 4, 12: Aggregate-only dataset handling and KPI card visual.
    """
    from services.analytics.calculation_engine import inspect_dataset_schema
    from services.chart_generator import build_powerbi_chart

    df_agg = pd.DataFrame({
        "Revenue": [50000.0],
        "Cost": [30000.0],
        "Profit": [20000.0],
    })
    schema = inspect_dataset_schema(df_agg)
    assert schema["is_aggregate_only"] is True

    chart = build_powerbi_chart(df_agg, "Profitability Analysis")
    assert chart is not None
    assert chart["chart_type"] == "kpi"
    assert "Total Revenue" in str(chart["plotly_json"])
    assert "Total Profit" in str(chart["plotly_json"])


def test_financial_total_consistency_and_double_counting(sample_profitability_df):
    """
    Requirement 6: Validate financial totals against source data and prevent double counting.
    The sum of grouped profit and revenue must exactly match aggregate totals.
    """
    res = default_calc_engine.calculate_profitability_analysis(sample_profitability_df)

    sum_grouped_rev = sum(r["Revenue"] for r in res.grouped_table)
    sum_grouped_cost = sum(r["Cost"] for r in res.grouped_table)
    sum_grouped_profit = sum(r["Profit"] for r in res.grouped_table)

    assert round(sum_grouped_rev, 2) == res.financial_kpis["total_revenue"]
    assert round(sum_grouped_cost, 2) == res.financial_kpis["total_cost"]
    assert round(sum_grouped_profit, 2) == res.financial_kpis["total_profit"]

    # Profit share percentages sum to 100%
    total_share = sum(r["Profit_Share_Pct"] for r in res.grouped_table)
    assert pytest.approx(total_share, rel=1e-2) == 100.0


def test_validator_strips_hallucinated_product_unavailability(sample_profitability_df):
    """
    Requirement 7 & Acceptance criteria:
    When dataset contains products and breakdown is calculated, if LLM falsely claims
    'product identifiers or categorical breakdowns are unavailable', validator strips
    and corrects the claim.
    """
    res = default_calc_engine.calculate_profitability_analysis(sample_profitability_df)
    assert res.grouped_table is not None

    hallucinated_answer = (
        "### Executive Summary\n"
        "- Overall Profit Margin: 33.37%\n"
        "- Product identifiers or categorical breakdowns are unavailable in this dataset.\n"
        "- The dataset contains aggregate figures only.\n"
        "- Baseline Comparison: Variance: Not calculated — baseline unavailable.\n"
    )

    sanitized, corrections = default_analytics_validator.validate_and_sanitize(
        hallucinated_answer, res, query="Profitability Analysis"
    )

    assert "product identifiers or categorical breakdowns are unavailable" not in sanitized.lower()
    assert "dataset contains aggregate figures only" not in sanitized.lower()
    assert "Standing Desk" in sanitized
    assert len(corrections) > 0
