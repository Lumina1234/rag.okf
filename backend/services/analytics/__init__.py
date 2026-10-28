"""
Analytics Package.
Provides deterministic calculation engine, business explainer, and analytics response validator.
"""
from .calculation_engine import (
    BusinessCalculationEngine,
    CalculationResult,
    default_calc_engine,
    resolve_column,
    format_currency_or_number,
    format_metric_value,
)
from .business_explainer import BusinessExplainer, default_explainer
from .analytics_validator import AnalyticsResponseValidator, default_analytics_validator

__all__ = [
    "BusinessCalculationEngine",
    "CalculationResult",
    "default_calc_engine",
    "resolve_column",
    "format_currency_or_number",
    "format_metric_value",
    "BusinessExplainer",
    "default_explainer",
    "AnalyticsResponseValidator",
    "default_analytics_validator",
]
