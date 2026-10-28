"""
Deterministic Post-Generation Analytics Validation and Correction Layer.
Enforces strict business intelligence standards on synthesized answers:
  1. Never calculate or report zero variance without a baseline.
  2. Never claim stability, steady trends, or lack of change without time-series data.
  3. Strictly separate verified calculations from analytical interpretations.
  4. Validate metric units (units vs currency).
  5. Enforce baseline unavailability phrasing and driver limitation explanations.
  6. Sanitize internal backend prompts and private reasoning traces.
"""
import logging
import re
from typing import Any, Optional

from .calculation_engine import CalculationResult

logger = logging.getLogger(__name__)


class AnalyticsResponseValidator:
    """
    Deterministic validator that programmatically inspects and sanitizes
    all analytics responses before delivery to frontend.
    """

    def validate_and_sanitize(
        self,
        response_text: str,
        calc_res: CalculationResult,
        query: str = "",
    ) -> tuple[str, list[str]]:
        """
        Inspect response_text against verified calc_res.
        Corrects unsupported claims and returns (sanitized_text, corrections_applied).
        """
        if not response_text:
            return "", []

        corrections: list[str] = []
        text = response_text

        # 0. Backend Privacy & Trace Sanitization
        text = self._sanitize_backend_traces(text, corrections)

        # 1. Unsupported Variance Checks (Requirement 1)
        if not calc_res.has_baseline or calc_res.baseline_value is None:
            text = self._correct_unsupported_variance(text, calc_res, corrections)

        # 2. Unsupported Stability & Trend Claims (Requirement 2 & 3)
        if not calc_res.has_time_series and not calc_res.has_baseline:
            text = self._correct_unsupported_stability(text, calc_res, corrections)

        # 3. Categorical & Product Limitation Validation (Requirements 1, 2, 4, 5)
        text = self._correct_unsupported_categorical_limitations(text, calc_res, corrections)

        # 4. Primary Driver Validation (Requirement 5)
        if not calc_res.driver_established:
            text = self._correct_unsupported_drivers(text, calc_res, corrections)

        # 5. Metric Unit Validation (Requirement 6)
        text = self._validate_metric_units(text, calc_res, corrections)

        # 6. Profitability Acceptance Criteria Enforcement
        if calc_res.financial_kpis:
            text = self._enforce_profitability_acceptance_format(text, calc_res, corrections)

        # 7. Quantity Acceptance Criteria Enforcement
        is_quantity = (
            calc_res.quantity_stats is not None
            or any(w in calc_res.metric_name.lower() for w in ["quantity", "qty", "volume", "units", "inventory"])
            or any(w in query.lower() for w in ["quantity", "volume", "inventory", "units"])
        )
        if is_quantity:
            text = self._enforce_quantity_acceptance_format(text, calc_res, corrections)

        # Final safety check: strictly guarantee no "Variance: 0%" and no "stable volume" without baseline
        if not calc_res.has_baseline:
            text = re.sub(
                r"(?i)\bvariance:\s*0(?:\.0+)?%?\b",
                "Variance: Not calculated — baseline unavailable.",
                text,
            )
            text = re.sub(
                r"(?i)(?<!not\s)(?<!not assumed\b)\b0(?:\.0+)?%\s*variance\b",
                "Variance: Not calculated — baseline unavailable.",
                text,
            )
            text = re.sub(
                r"(?i)(?<!not\s)(?<!not assumed\b)\bzero\s*variance\b",
                "Variance: Not calculated — baseline unavailable.",
                text,
            )
            text = re.sub(
                r"Variance:\s*Not calculated\s*—\s*baseline unavailable\.\s*%",
                "Variance: Not calculated — baseline unavailable.",
                text,
            )
        if not calc_res.has_time_series and not calc_res.has_baseline:
            text = re.sub(
                r"(?i)\bstable\s+volume\b",
                "volume (stability cannot be established without baseline)",
                text,
            )

        # Clean up double periods or trailing punctuation artifacts
        text = re.sub(r"\.\s*\.", ".", text)

        return text, corrections

    def _sanitize_backend_traces(self, text: str, corrections: list[str]) -> str:
        """Strip internal system prompts, thinking tags, and private execution traces."""
        original = text
        # Remove <think>...</think>
        text = re.sub(r"<think>[\s\S]*?</think>", "", text)
        # Remove internal prompt headers
        internal_headers = [
            r"System Prompt:[\s\S]*?\n\n",
            r"User Business Query:[\s\S]*?\n",
            r"Verified Calculation Data:[\s\S]*?\n\n",
            r"CRITICAL INSTRUCTIONS:[\s\S]*?\n",
            r"STRICT NON-NEGOTIABLE COMPLIANCE RULES:[\s\S]*?\n",
        ]
        for pattern in internal_headers:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        if text != original:
            corrections.append("Stripped internal backend instructions and reasoning traces.")
        return text

    def _correct_unsupported_variance(
        self, text: str, calc_res: CalculationResult, corrections: list[str]
    ) -> str:
        """
        Detects and removes/replaces any claim of zero variance or 0% variance
        when no baseline exists. Enforces 'Variance: Not calculated — baseline unavailable.'
        """
        original = text
        replacement = "Variance: Not calculated — baseline unavailable."

        # Patterns claiming 0% variance or zero variance
        variance_patterns = [
            r"(?i)\bvariance:\s*(?:0(?:\.0+)?%?|none|\$0|n/a)(?!\d)",
            r"(?i)(?<!not\s)(?<!not assumed\b)\b(?:0(?:\.0+)?%?)\s*variance\b",
            r"(?i)\bvariance\s*(?:of|is)\s*(?:0(?:\.0+)?%?|zero)(?!\d)",
            r"(?i)\b(?:measured|reported|exhibits?|shows?)\s+(?:zero|no)\s+variance\b",
            r"(?i)\bbaseline\s*comparison:\s*(?:variance:\s*)?(?:0(?:\.0+)?%?|zero\s*variance|no\s*variance)\b",
        ]

        for pat in variance_patterns:
            if re.search(pat, text):
                text = re.sub(pat, replacement, text)
                corrections.append(f"Corrected unsupported zero variance claim to '{replacement}'")

        # Clean trailing percent if matched from earlier sub
        text = re.sub(r"Variance:\s*Not calculated\s*—\s*baseline unavailable\.\s*%", replacement, text)

        # Standardize bolding on Variance label so 'Variance: Not calculated — baseline unavailable.' is an exact substring
        text = re.sub(r"\*\*Variance:?\*\*:?", "Variance:", text)

        # Ensure "Variance: Not calculated — baseline unavailable." is explicitly present
        if "Variance: Not calculated — baseline unavailable." not in text:
            # Replace generic "Baseline unavailable" with full required wording
            if re.search(r"(?i)- \*\*Baseline Comparison\*\*:\s*Baseline unavailable\.?", text):
                text = re.sub(
                    r"(?i)- \*\*Baseline Comparison\*\*:\s*Baseline unavailable\.?",
                    "- **Baseline Comparison**: Variance: Not calculated — baseline unavailable.",
                    text,
                )
                corrections.append("Standardized baseline comparison wording.")
            elif re.search(r"(?i)\bBaseline Comparison:\s*Baseline unavailable\.?", text):
                text = re.sub(
                    r"(?i)\bBaseline Comparison:\s*Baseline unavailable\.?",
                    "Baseline Comparison: Variance: Not calculated — baseline unavailable.",
                    text,
                )
                corrections.append("Standardized baseline comparison wording.")
            elif "- **Baseline Comparison**:" in text:
                text = re.sub(
                    r"- \*\*Baseline Comparison\*\*:[^\n]+",
                    "- **Baseline Comparison**: Variance: Not calculated — baseline unavailable.",
                    text,
                )
                corrections.append("Inserted mandatory variance status in baseline comparison.")

        return text

    def _correct_unsupported_stability(
        self, text: str, calc_res: CalculationResult, corrections: list[str]
    ) -> str:
        """
        Detects and replaces claims of stability or lack of change over time
        when no time-series analysis or baseline comparison was performed.
        """
        stability_disclaimer = (
            "Baseline unavailable — historical stability or trend cannot be established from standalone records."
        )

        stability_patterns = [
            r"(?i)\b(?:the\s+data\s+)?(?:indicates?|shows?|reflects?|demonstrates?|exhibits?)\s+(?:a\s+)?stable\s+volume(?:\s+across(?:\s+the)?\s+[^\n.,]+)?",
            r"(?i)\b(?:the\s+data\s+(?:shows|indicates)\s+a\s+)?stable\s+volume(?:\s+across(?:\s+the)?\s+(?:analyzed\s+)?periods?)?",
            r"(?i)\b(?:volume|quantity)\s+is\s+stable(?:\s+across(?:\s+the)?\s+(?:analyzed\s+)?periods?)?",
            r"(?i)\b(?:stable|consistent|steady|constant|unchanged)\s+volume(?:\s+across(?:\s+the)?\s+(?:analyzed\s+)?periods?)?",
            r"(?i)\b(?:consistent|stable)\s+over\s+time\b",
            r"(?i)\bshowing\s+no\s+(?:change|variance)\b",
            r"(?i)\bconsistent\s+reporting\s+across\s+\d+\s+(?:instances|records|transactions)\b",
        ]

        for pat in stability_patterns:
            if re.search(pat, text):
                text = re.sub(pat, stability_disclaimer, text)
                corrections.append("Replaced unsupported stability claim with baseline limitation explanation.")

        # Ensure stability disclaimer is present in Strategic / Analytical Interpretations
        if "historical stability or trend cannot be established" not in text.lower():
            if "#### 💡 Strategic Takeaways" in text or "#### 💡 Analytical Interpretations" in text:
                header = "#### 💡 Strategic Takeaways" if "#### 💡 Strategic Takeaways" in text else "#### 💡 Analytical Interpretations"
                text = text.replace(
                    header,
                    f"{header}\n- **Baseline Assessment**: {stability_disclaimer}",
                )
                corrections.append("Added stability assessment disclaimer to analytical takeaways.")

        return text

    def _correct_unsupported_drivers(
        self, text: str, calc_res: CalculationResult, corrections: list[str]
    ) -> str:
        """
        Ensures that if no categorical driver was established, the limitation
        is clearly stated rather than fabricating a primary driver.
        """
        driver_limit = (
            calc_res.driver_explanation
            or "Primary drivers cannot be established without categorical segmentation or multi-dimensional data."
        )
        if re.search(r"(?i)- \*\*Key Driver\*\*:\s*None\.?", text):
            text = re.sub(r"(?i)- \*\*Key Driver\*\*:\s*None\.?", f"- **Key Driver**: {driver_limit}", text)
            corrections.append("Replaced 'None' key driver with clear limitation explanation.")
        return text

    def _validate_metric_units(
        self, text: str, calc_res: CalculationResult, corrections: list[str]
    ) -> str:
        """
        Validates and fixes metric units (e.g. quantity formatted with $ sign).
        """
        is_quantity = (
            calc_res.quantity_stats is not None
            or any(w in calc_res.metric_name.lower() for w in ["quantity", "qty", "volume", "units"])
        )
        if is_quantity:
            # Fix patterns like "$151 units" -> "151 units"
            if re.search(r"\$\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*units?", text):
                text = re.sub(r"\$\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*units?", r"\1 units", text)
                corrections.append("Removed incorrect dollar currency symbol from quantity metric.")
            # Fix patterns like "Total quantity: $151" -> "Total quantity: 151 units"
            if re.search(r"(?i)Total\s+quantity:\s*\$\s*(\d+(?:,\d+)*(?:\.\d+)?)", text):
                text = re.sub(r"(?i)Total\s+quantity:\s*\$\s*(\d+(?:,\d+)*(?:\.\d+)?)", r"Total quantity: \1 units", text)
                corrections.append("Corrected Total quantity currency symbol to units.")
        return text

    def _enforce_quantity_acceptance_format(
        self, text: str, calc_res: CalculationResult, corrections: list[str]
    ) -> str:
        """
        Guarantees strict acceptance criteria for quantity queries:
        - Must report 'Total quantity: <value> units'
        - Must report 'Variance: Not calculated — baseline unavailable.' (when baseline missing)
        - Must not claim zero variance or stable volume.
        """
        raw_qty = (
            calc_res.quantity_stats["total_formatted"]
            if calc_res.quantity_stats and "total_formatted" in calc_res.quantity_stats
            else calc_res.formatted_value
        )
        expected_qty_str = raw_qty.replace("`", "").strip()

        # 1. Enforce "Total quantity: <value>" exact substring
        target_phrase = f"Total quantity: {expected_qty_str}"
        if target_phrase not in text:
            # Check if bold or styled variant exists
            if re.search(r"(?i)\*\*total\s+quantity\*\*:\s*`?" + re.escape(expected_qty_str) + r"`?", text):
                text = re.sub(
                    r"(?i)\*\*total\s+quantity\*\*:\s*`?" + re.escape(expected_qty_str) + r"`?",
                    f"**{target_phrase}**",
                    text,
                )
                corrections.append(f"Standardized bold styling to contain '{target_phrase}'.")
            elif re.search(r"(?i)\*\*measured result\*\*:\s*`?" + re.escape(expected_qty_str) + r"`?", text):
                text = re.sub(
                    r"(?i)\*\*measured result\*\*:\s*`?" + re.escape(expected_qty_str) + r"`?",
                    f"**{target_phrase}**",
                    text,
                )
                corrections.append(f"Standardized Measured Result to '{target_phrase}'.")
            elif re.search(r"(###\s+.*Executive Summary[^\n]*\n)", text):
                text = re.sub(
                    r"(###\s+.*Executive Summary[^\n]*\n)",
                    r"\1- **" + target_phrase + r"**\n",
                    text,
                    count=1,
                )
                corrections.append(f"Inserted required '{target_phrase}' in Executive Summary.")
            else:
                text = f"- **{target_phrase}**\n" + text
                corrections.append(f"Prepended required '{target_phrase}'.")

        # 2. Enforce "Variance: Not calculated — baseline unavailable."
        if not calc_res.has_baseline:
            if "Variance: Not calculated — baseline unavailable." not in text:
                if "- **Baseline Comparison**:" in text:
                    text = re.sub(
                        r"- \*\*Baseline Comparison\*\*:[^\n]+",
                        "- **Baseline Comparison**: Variance: Not calculated — baseline unavailable.",
                        text,
                    )
                else:
                    text = text + "\n- **Variance**: Not calculated — baseline unavailable."
                corrections.append("Enforced mandatory 'Variance: Not calculated — baseline unavailable.'")

        return text

    def _correct_unsupported_categorical_limitations(
        self, text: str, calc_res: CalculationResult, corrections: list[str]
    ) -> str:
        """
        Detects and corrects false claims about product identifiers, categories, or aggregate-only data:
        1. If categorical dimensions exist in calc_res, strip claims that product identifiers or categorical breakdowns are unavailable.
        2. If columns are genuinely missing, ensure specific missing columns are reported rather than claiming aggregate-only data.
        3. If dataset is truly aggregate-only, ensure specific statement:
           'Product and Category fields are not present in this dataset; analysis is limited to overall financial totals.'
        """
        # Case 1: Categorical dimension IS present
        if calc_res.grouped_table and calc_res.dimension:
            false_limit_patterns = [
                r"(?i)\b(?:product\s+identifiers|categorical\s+breakdowns?|chart\s+data)\s+(?:are|is)\s+unavailable\b",
                r"(?i)\b(?:the\s+)?dataset\s+contains\s+aggregate\s+figures\s+only\b",
                r"(?i)\bno\s+product\s+(?:identifiers|breakdown|categories)\s+are\s+available\b",
                r"(?i)\blimited\s+to\s+aggregate\s+figures\b",
                r"(?i)\blacks\s+product\s+identifiers\b",
            ]
            replacement = (
                f"Categorical breakdown by {calc_res.dimension} is verified. "
                f"Top driver: {calc_res.top_driver or (calc_res.product_rankings[0] if calc_res.product_rankings else 'Identified in verified table')}"
            )
            for pat in false_limit_patterns:
                if re.search(pat, text):
                    text = re.sub(pat, replacement, text)
                    corrections.append(f"Corrected false claim that {calc_res.dimension} breakdown is unavailable.")

        # Case 2: Genuinely missing financial columns
        if calc_res.missing_columns:
            missing_str = ", ".join(calc_res.missing_columns)
            missing_notice = f"Genuinely missing required column(s): {missing_str}. Profitability cannot be computed without these fields."
            generic_agg_pat = r"(?i)\b(?:the\s+)?dataset\s+contains\s+aggregate\s+figures\s+only\b"
            if re.search(generic_agg_pat, text):
                text = re.sub(generic_agg_pat, missing_notice, text)
                corrections.append("Replaced generic aggregate claim with specific missing column limitation.")
            elif missing_str not in text:
                text += f"\n\n- **Column Limitations**: {missing_notice}"
                corrections.append(f"Appended specific missing column limitation for {missing_str}.")

        # Case 3: Aggregate-only dataset (no categorical dimensions)
        elif not calc_res.grouped_table and not calc_res.driver_established:
            target_limit = "Product and Category fields are not present in this dataset; analysis is limited to overall financial totals."
            generic_pats = [
                r"(?i)\bthe\s+entire\s+dataset\s+contains\s+aggregate\s+figures\s+only\b",
                r"(?i)\bdataset\s+contains\s+aggregate\s+figures\s+only\b",
            ]
            for pat in generic_pats:
                if re.search(pat, text):
                    text = re.sub(pat, target_limit, text)
                    corrections.append("Clarified aggregate-only limitation with specific missing fields explanation.")

        return text

    def _enforce_profitability_acceptance_format(
        self, text: str, calc_res: CalculationResult, corrections: list[str]
    ) -> str:
        """
        Enforce profitability analysis acceptance criteria:
        - Must report validated Profit Margin percentage
        - Must report 'Variance: Not calculated — baseline unavailable.' when baseline missing
        - If products are present, ensure top driver / ranking is presented
        """
        if not calc_res.financial_kpis:
            return text

        margin_str = calc_res.financial_kpis["profit_margin_formatted"]
        # Ensure profit margin value is present
        if margin_str not in text and (calc_res.value is not None and f"{calc_res.value:.2f}%" not in text):
            text = f"- **Overall Profit Margin**: {margin_str}\n" + text
            corrections.append(f"Inserted validated profit margin {margin_str}.")

        # If product rankings exist, ensure top product is mentioned
        if calc_res.product_rankings and calc_res.grouped_table:
            top_prod = calc_res.grouped_table[0].get(calc_res.dimension or "Product", "")
            if top_prod and str(top_prod).lower() not in text.lower():
                text = text + f"\n- **Top Product Driver**: {calc_res.product_rankings[0]}"
                corrections.append(f"Appended top product ranking for {top_prod}.")

        return text


default_analytics_validator = AnalyticsResponseValidator()
