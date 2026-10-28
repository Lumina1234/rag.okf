"""
Unit tests for Power BI-Style Charts and Plotly Generator.
"""
import pandas as pd
import pytest

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.chart_generator import (
    generate_bar_chart,
    generate_stacked_bar_chart,
    generate_line_chart,
    generate_area_chart,
    generate_pie_chart,
    generate_waterfall_chart,
    generate_scatter_chart,
    generate_kpi_cards,
    validate_plotly_json,
    build_powerbi_chart,
)


def test_chart_json_validation():
    """Verify validate_plotly_json rejects non-dicts or missing data arrays."""
    assert validate_plotly_json({"data": [], "layout": {}}) is True
    assert validate_plotly_json({"data": [{"x": [1], "y": [2]}]}) is True
    assert validate_plotly_json({}) is False
    assert validate_plotly_json("invalid") is False
    assert validate_plotly_json(None) is False


def test_bar_chart_generation():
    """Verify standard and horizontal bar chart creation."""
    chart = generate_bar_chart(x=["North", "South", "East"], y=[100, 200, 150], title="Regional Sales")
    assert validate_plotly_json(chart) is True
    assert chart["data"][0]["type"] == "bar"
    assert chart["layout"]["title"]["text"] == "Regional Sales"


def test_stacked_bar_chart_generation():
    """Verify stacked bar chart generation."""
    series = {"Product A": [10, 20], "Product B": [30, 40]}
    chart = generate_stacked_bar_chart(x=["Q1", "Q2"], series_dict=series, title="Quarterly Sales by Product")
    assert validate_plotly_json(chart) is True
    assert chart["layout"]["barmode"] == "stack"
    assert len(chart["data"]) == 2


def test_area_and_line_chart_generation():
    """Verify area and line chart structures."""
    line = generate_line_chart(x=["Jan", "Feb", "Mar"], y=[50, 75, 90], title="Growth")
    assert validate_plotly_json(line) is True
    assert line["data"][0]["mode"] == "lines+markers"

    area = generate_area_chart(x=["Jan", "Feb", "Mar"], y=[50, 75, 90], title="Cumulative Volume")
    assert validate_plotly_json(area) is True
    assert area["data"][0]["fill"] == "tozeroy"


def test_pie_chart_generation():
    """Verify donut/pie chart format."""
    pie = generate_pie_chart(labels=["Electronics", "Appliances"], values=[60, 40], title="Market Share")
    assert validate_plotly_json(pie) is True
    assert pie["data"][0]["type"] == "pie"
    assert pie["data"][0]["hole"] > 0


def test_waterfall_chart_generation():
    """Verify waterfall chart for variance bridges."""
    waterfall = generate_waterfall_chart(categories=["Base", "Volume", "Price", "Ending"], values=[100, 20, -10, 110])
    assert validate_plotly_json(waterfall) is True
    assert waterfall["data"][0]["type"] == "waterfall"


def test_kpi_cards_generation():
    """Verify KPI indicator card generation."""
    kpis = [
        {"label": "Total Revenue", "value": 48112.0, "delta": 8112.0, "unit": "$"},
        {"label": "Profit Margin", "value": 32.45, "unit": "%"},
    ]
    kpi_chart = generate_kpi_cards(kpis)
    assert validate_plotly_json(kpi_chart) is True
    assert len(kpi_chart["data"]) == 2
    assert kpi_chart["data"][0]["type"] == "indicator"


def test_build_powerbi_chart_from_dataframe():
    """Verify automated chart construction from pandas DataFrame based on user query."""
    df = pd.DataFrame({
        "Order_Date": ["2026-01-01", "2026-02-01", "2026-03-01"],
        "Region": ["North", "South", "East"],
        "Revenue": [1000.0, 2000.0, 1500.0],
        "Profit": [300.0, 700.0, 450.0],
    })

    # Line trend
    chart_res = build_powerbi_chart(df, query="Show monthly revenue trend")
    assert chart_res is not None
    assert chart_res["chart_type"] in ("line", "area")
    assert validate_plotly_json(chart_res["plotly_json"]) is True

    # Pie share
    chart_res_pie = build_powerbi_chart(df, query="Show sales share by region pie chart")
    assert chart_res_pie is not None
    assert chart_res_pie["chart_type"] == "pie"
    assert validate_plotly_json(chart_res_pie["plotly_json"]) is True
