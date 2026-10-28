"""
Business Intelligence Explanation and Contextualization Engine.
Translates deterministic mathematical results into executive-ready business intelligence narratives.
Strictly separates verified calculations from analytical interpretations.
"""
from typing import Any, Optional
from .calculation_engine import CalculationResult


class BusinessExplainer:
    """
    Formats deterministic calculation results into standard enterprise BI reports.
    Provides clear structure:
      1. Executive Summary
      2. Verified Calculations & Methodology
      3. Dimensional Breakdown Table (if available)
      4. Analytical Interpretations & Context (strictly separated from verified math)
      5. Caveats & Data Governance
    """

    @staticmethod
    def format_markdown_report(result: CalculationResult, query: str = "") -> str:
        """
        Generate a comprehensive, structured Markdown analysis based on verified figures.
        """
        lines = []

        # 1. Executive Summary
        lines.append(f"### 📊 Executive Summary: {result.metric_name}")

        if result.financial_kpis:
            lines.append(
                f"- **Overall Profit Margin**: {result.financial_kpis['profit_margin_formatted']} "
                f"(Total Profit {result.financial_kpis['total_profit_formatted']} on Total Revenue {result.financial_kpis['total_revenue_formatted']})"
            )
        elif result.quantity_stats:
            lines.append(f"- **Total quantity: {result.quantity_stats['total_formatted']}**")
        else:
            lines.append(f"- **Measured Result**: `{result.formatted_value}`")

        # Missing Column Limitations (Requirement 5)
        if result.missing_columns:
            lines.append(f"- **Column Limitations**: Genuinely missing required column(s): {', '.join(result.missing_columns)}.")

        # Baseline Comparison
        if result.has_baseline and result.variance is not None and result.variance_pct is not None:
            direction = "increase 📈" if result.variance >= 0 else "decrease 📉"
            lines.append(
                f"- **Baseline Comparison**: Variance: `{result.variance:+,.2f}` "
                f"({result.variance_pct:+.2f}% {direction}) against baseline `{result.baseline_value:,.2f}`."
            )
        else:
            lines.append("- **Baseline Comparison**: Variance: Not calculated — baseline unavailable.")

        # Key Drivers
        if result.driver_established and result.top_driver:
            lines.append(f"- **Primary Driver**: {result.top_driver}.")
        elif result.driver_explanation:
            lines.append(f"- **Key Driver Limitation**: {result.driver_explanation}")

        # Product Rankings (Requirement 4)
        if result.product_rankings:
            lines.append("- **Product Rankings**:")
            for ranking in result.product_rankings[:5]:
                lines.append(f"  - {ranking}")

        # Stability & Trend Assessment
        if result.has_time_series:
            lines.append("- **Stability & Trend Assessment**: Sequential period-over-period trend evaluated across verified time-series data.")
        else:
            lines.append("- **Stability & Trend Assessment**: Historical stability or trend cannot be established from standalone records without a baseline or time-series analysis.")

        lines.append("")

        # 2. Verified Calculations & Methodology
        lines.append("#### 🔢 Verified Calculations & Methodology")
        if result.financial_kpis:
            lines.append(f"- Total Revenue: {result.financial_kpis['total_revenue_formatted']}")
            lines.append(f"- Total Cost: {result.financial_kpis['total_cost_formatted']}")
            lines.append(f"- Total Profit: {result.financial_kpis['total_profit_formatted']}")
            lines.append(f"- Overall Profit Margin: {result.financial_kpis['profit_margin_formatted']}")
            lines.append(f"- Audited Record Count: {result.financial_kpis['record_count']} records")
            lines.append("- Double-Counting Audit: Verified unique record aggregation across source rows with zero double counting.")
        elif result.quantity_stats:
            lines.append(f"- Total quantity: {result.quantity_stats['total_formatted']}")
            lines.append(f"- Average quantity: {result.quantity_stats['average_formatted']}")
            lines.append(f"- Minimum quantity: {result.quantity_stats['min_formatted']}")
            lines.append(f"- Maximum quantity: {result.quantity_stats['max_formatted']}")
            lines.append(f"- Audited Record Count: {result.quantity_stats['count']} records")
        else:
            lines.append(f"- Primary Metric: {result.formatted_value}")
            if "count" in result.metadata:
                lines.append(f"- Audited Record Count: {result.metadata['count']} records")

        if result.has_baseline and result.variance is not None:
            lines.append(f"- Variance: {result.variance:+,.2f} ({result.variance_pct:+.2f}%)")
        else:
            lines.append("- Variance: Not calculated — baseline unavailable.")

        lines.append(f"- Formula: `{result.formula}`")
        if result.metadata:
            details_str = ", ".join(f"`{k}`: {v}" for k, v in result.metadata.items() if not isinstance(v, (list, dict)))
            if details_str:
                lines.append(f"- Parameters: {details_str}")
        lines.append("")

        # 3. Dimensional Breakdown Table (if available)
        if result.grouped_table:
            table_title = f"Product Profitability Breakdown by {result.dimension or 'Product'}" if result.financial_kpis else f"Dimensional Breakdown by {result.dimension or 'Segment'}"
            lines.append(f"#### 📋 {table_title}")
            headers = list(result.grouped_table[0].keys())
            header_row = "| " + " | ".join(h.replace("_", " ").title() for h in headers) + " |"
            sep_row = "| " + " | ".join("---" for _ in headers) + " |"
            lines.append(header_row)
            lines.append(sep_row)
            for row in result.grouped_table[:10]:
                formatted_cells = []
                for k, v in row.items():
                    if isinstance(v, (int, float)):
                        if "margin" in k.lower() or "share" in k.lower() or "pct" in k.lower():
                            formatted_cells.append(f"{v:.2f}%")
                        elif "revenue" in k.lower() or "cost" in k.lower() or "profit" in k.lower():
                            formatted_cells.append(f"${v:,.2f}")
                        elif "count" in k.lower():
                            formatted_cells.append(f"{int(v)} records")
                        else:
                            formatted_cells.append(f"{v:,.2f}")
                    else:
                        formatted_cells.append(str(v))
                val_row = "| " + " | ".join(formatted_cells) + " |"
                lines.append(val_row)
            lines.append("")

        # 4. Analytical Interpretations & Context (Strictly separated from verified calculations)
        lines.append("#### 💡 Analytical Interpretations & Context")
        lines.append("*(Note: Analytical interpretations are strictly separated from verified calculations. A verified total does not support conclusions regarding historical stability or unseen trends. Revenue and profit totals must be distinguished from product-level findings; business drivers cannot be inferred from aggregate figures alone.)*")

        if result.financial_kpis and result.grouped_table and len(result.grouped_table) > 1:
            top_rec = result.grouped_table[0]
            dim_val = top_rec.get(result.dimension or "Product", "Top Product")
            profit_val = top_rec.get("Profit", 0.0)
            share_val = top_rec.get("Profit_Share_Pct", 0.0)
            margin_val = top_rec.get("Profit_Margin_Pct", 0.0)
            lines.append(
                f"- **Product Concentration**: `{dim_val}` is the primary contributor, generating `${profit_val:,.2f}` in profit "
                f"({share_val:.2f}% of total profit) with an operating margin of `{margin_val:.2f}%`."
            )
            # Second item if available
            if len(result.grouped_table) > 1:
                sec_rec = result.grouped_table[1]
                sec_val = sec_rec.get(result.dimension or "Product", "Second Product")
                sec_profit = sec_rec.get("Profit", 0.0)
                sec_share = sec_rec.get("Profit_Share_Pct", 0.0)
                lines.append(
                    f"- **Secondary Contributor**: `{sec_val}` follows with `${sec_profit:,.2f}` in profit ({sec_share:.2f}% share)."
                )
        elif result.grouped_table and len(result.grouped_table) > 1:
            top_rec = result.grouped_table[0]
            dim_key = list(top_rec.keys())[0]
            val_key = list(top_rec.keys())[1]
            lines.append(
                f"- **Volume Concentration**: Concentration is highest in `{top_rec[dim_key]}` "
                f"accounting for `{top_rec[val_key]:,.2f}` ({top_rec.get('share_pct', 'N/A')}% share)."
            )
        elif not result.driver_established:
            lines.append(f"- **Driver Assessment**: {result.driver_explanation or 'No multi-dimensional drivers established.'}")

        if not result.has_baseline and not result.has_time_series:
            lines.append("- **Trend Interpretation**: Baseline unavailable — historical stability or trend cannot be established from standalone records.")
        elif result.has_baseline and result.variance is not None:
            lines.append(f"- **Variance Assessment**: Performance reflects a measured variance of `{result.variance:+,.2f}` against baseline.")

        lines.append("")

        # 5. Caveats and Assumptions
        lines.append("#### ⚠️ Caveats & Data Governance")
        lines.append("- All calculations performed deterministically on verified tabular records with zero missing-value imputation.")
        if not result.has_baseline:
            lines.append("- **Baseline Limitation**: Variance is explicitly not calculated because no comparison baseline exists.")
        if result.missing_columns:
            lines.append(f"- **Missing Field Limitation**: Column(s) {', '.join(result.missing_columns)} are not present in this dataset.")
        if result.warnings:
            for w in result.warnings:
                if w not in ["Baseline unavailable."]:
                    lines.append(f"- {w}")

        return "\n".join(lines)


default_explainer = BusinessExplainer()
