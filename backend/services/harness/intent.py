"""
Intent and Query Understanding Module.
Classifies user queries, rewrites queries for optimal retrieval,
extracts analytical dimensions/metrics, and decomposes multi-part tasks.
"""
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Optional


class IntentType(str, Enum):
    FACTUAL_QA = "factual_qa"
    SYNTHESIS = "synthesis"
    ANALYTICS_CALC = "analytics_calc"
    ANALYTICS_CHART = "analytics_chart"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    OUT_OF_DOMAIN = "out_of_domain"
    GENERAL = "general"


@dataclass
class IntentAnalysis:
    raw_query: str
    primary_intent: IntentType
    normalized_query: str
    retrieval_query: str
    chart_type_hint: Optional[str] = None
    target_metric: Optional[str] = None
    target_dimension: Optional[str] = None
    time_grain: Optional[str] = None  # e.g., 'yearly', 'quarterly', 'monthly'
    sub_tasks: list[str] = field(default_factory=list)
    confidence: float = 1.0


# Regex patterns for business analytics calculations
CALC_PATTERNS = [
    r"\b(calculate|sum|total|average|mean|median|growth rate|percentage change|increase|decrease|variance|profit margin|margin|ratio)\b",
    r"\b(yoy|year-over-year|year on year|mom|month-over-month|month on month|qoq|quarter-over-quarter)\b",
    r"\b(difference between|how much higher|how much lower|how much more|how much less)\b",
    r"\b(max|min|highest|lowest|top \d+|bottom \d+)\b",
]

# Chart request patterns (explicit chart types checked first)
CHART_PATTERNS = {
    "pie": [r"\b(pie chart|donut chart|pie|donut|share|market share|proportion|percentage of total|slice)\b"],
    "line": [r"\b(line chart|trend|over time|monthly|quarterly|yearly|progression|trajectory|time series)\b"],
    "stacked_bar": [r"\b(stacked bar|composition across|distribution by.*and)\b"],
    "area": [r"\b(area chart|cumulative|stacked area|volume over time)\b"],
    "waterfall": [r"\b(waterfall|bridge|step-by-step breakdown|variance bridge)\b"],
    "scatter": [r"\b(scatter plot|scatter|correlation|relationship between.*and)\b"],
    "kpi": [r"\b(kpi|metric card|summary card|key metrics|headline numbers)\b"],
    "bar": [r"\b(bar chart|bar graph|horizontal bar|comparison chart|ranking chart|bar)\b"],
}

# Summary patterns
SUMMARY_PATTERNS = [
    r"\b(summarize|summary|overview|briefing|executive summary|abstract|give me a breakdown of the doc)\b",
    r"\b(tell me about (the|this) (pdf|document|file)|what is this (pdf|document) about)\b",
]

# Synthesis / multi-doc comparison patterns
SYNTHESIS_PATTERNS = [
    r"\b(across all documents|compare documents|between modules|across modules|synthesize|combine insights)\b",
    r"\b(differences between|contrast.*with)\b",
]


def normalize_query(query: str) -> str:
    """Clean and normalize query string while preserving important numbers and operators."""
    q = query.strip()
    # Normalize common business acronyms
    q = re.sub(r"\byoy\b", "year-over-year", q, flags=re.IGNORECASE)
    q = re.sub(r"\bmom\b", "month-over-month", q, flags=re.IGNORECASE)
    q = re.sub(r"\bqoq\b", "quarter-over-quarter", q, flags=re.IGNORECASE)
    q = re.sub(r"\bcagr\b", "compound annual growth rate", q, flags=re.IGNORECASE)
    # Collapse multiple whitespaces
    q = re.sub(r"\s+", " ", q)
    return q


def extract_retrieval_query(query: str) -> str:
    """
    Transform conversational question into a clean keyword-dense query for vector search.
    Removes conversational preambles like 'Can you please tell me', 'I want to know', etc.
    """
    q = normalize_query(query)
    # Strip conversational conversational filler
    q = re.sub(
        r"^(can you please |please |tell me |could you tell me |what is |what are |explain |show me |find |give me )",
        "",
        q,
        flags=re.IGNORECASE,
    )
    q = re.sub(r"[?!.,]+$", "", q).strip()
    return q if q else query.strip()


def detect_chart_type(query: str) -> Optional[str]:
    """Detect specific chart type hint from the query."""
    q_lower = query.lower()
    for chart_type, patterns in CHART_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q_lower):
                return chart_type
    # Generic chart mention
    if re.search(r"\b(chart|graph|plot|visualize|dashboard)\b", q_lower):
        if re.search(r"\b(over time|trend|date|month|year)\b", q_lower):
            return "line"
        if re.search(r"\b(share|percentage|proportion|part of)\b", q_lower):
            return "pie"
        return "bar"
    return None


def decompose_tasks(query: str) -> list[str]:
    """
    Decompose composite queries into logical sequential steps.
    Example: 'What was 2023 sales and compare to 2022' -> ['Extract 2023 sales', 'Extract 2022 sales', 'Compare sales']
    """
    tasks = []
    q_norm = normalize_query(query)
    # Split on conjunctions like 'and compare', 'also show', 'then calculate'
    split_parts = re.split(r"\b(?:and compare to|and also show|and calculate|then show)\b", q_norm, flags=re.IGNORECASE)
    if len(split_parts) > 1:
        for p in split_parts:
            p_clean = p.strip()
            if p_clean:
                tasks.append(p_clean)
    else:
        tasks.append(q_norm)
    return tasks


def resolve_followup_context(query: str, history: Optional[list[dict]] = None) -> str:
    """
    Resolve elliptical or pronoun-heavy follow-up questions using recent conversation history.
    Example:
      History: 'What was total revenue in 2025?'
      Current: 'And what about 2024?'
      Resolved: 'What was total revenue in 2025? (comparing/focusing on: 2024)'
    """
    if not history or len(history) == 0:
        return query

    q_clean = query.strip()
    q_lower = q_clean.lower()

    # Elliptical patterns: 'what about X', 'how about X', 'and for X', 'why did it drop', 'compare it to X'
    is_elliptic = any(re.search(pat, q_lower) for pat in [
        r"^(and\s+)?(what|how)\s+about\b",
        r"^(and\s+)?(for|with)\s+\b",
        r"\b(it|they|this|that|the former|the latter|the same)\b",
        r"^(why|how)\s+did\s+(it|this|that)\b",
    ])

    if not is_elliptic:
        return query

    # Find the most recent user question from history
    last_user_msg = None
    for msg in reversed(history):
        if msg.get("role") == "user":
            last_user_msg = msg.get("content", "").strip()
            break

    if not last_user_msg:
        return query

    # If current question is 'what about <period/dimension>'
    m_what_about = re.search(r"^(?:and\s+)?(?:what|how)\s+about\s+(.+?)[\?\.]*$", q_clean, flags=re.IGNORECASE)
    if m_what_about:
        target = m_what_about.group(1).strip()
        return f"{last_user_msg} (focusing on: {target})"

    # If query contains 'it' or 'that'
    if re.search(r"\b(it|this|that)\b", q_lower):
        metric_match = re.search(r"\b(revenue|profit|sales|cost|margin|growth|standing desk|headphones|monitor)\b", last_user_msg, flags=re.IGNORECASE)
        if metric_match:
            return re.sub(r"\b(it|this|that)\b", f"the {metric_match.group(0)}", q_clean, flags=re.IGNORECASE)

    return query


def analyze_intent(query: str, history: Optional[list[dict]] = None) -> IntentAnalysis:
    """
    Complete intent classification and query understanding pipeline.
    Resolves follow-up conversation context when history is provided.
    """
    raw_query = resolve_followup_context(query.strip(), history)
    norm_query = normalize_query(raw_query)
    retrieval_q = extract_retrieval_query(raw_query)
    q_lower = norm_query.lower()

    # Detect chart request
    chart_hint = detect_chart_type(norm_query)

    # Check for analytical calculation intent
    is_calc = any(re.search(pat, q_lower) for pat in CALC_PATTERNS)

    # Check for summary intent
    is_summary = any(re.search(pat, q_lower) for pat in SUMMARY_PATTERNS)

    # Check for synthesis / multi-doc intent
    is_synthesis = any(re.search(pat, q_lower) for pat in SYNTHESIS_PATTERNS)

    # Determine primary intent
    if chart_hint:
        primary_intent = IntentType.ANALYTICS_CHART
    elif is_calc:
        primary_intent = IntentType.ANALYTICS_CALC
    elif is_synthesis:
        primary_intent = IntentType.SYNTHESIS
    elif is_summary:
        primary_intent = IntentType.SUMMARY
    elif re.search(r"\b(compare|versus|vs\.?|difference between)\b", q_lower):
        primary_intent = IntentType.COMPARISON
    else:
        primary_intent = IntentType.FACTUAL_QA

    # Detect potential metric names
    target_metric = None
    for metric_kw in ["revenue", "sales", "profit", "expenses", "cost", "margin", "income", "churn", "growth", "quantity", "volume", "units", "ebitda"]:
        if metric_kw in q_lower:
            target_metric = metric_kw
            break

    # Detect dimension
    target_dimension = None
    for dim_kw in ["region", "country", "city", "product", "category", "segment", "department", "customer", "quarter", "month", "year"]:
        if dim_kw in q_lower:
            target_dimension = dim_kw
            break

    # Detect time grain
    time_grain = None
    if re.search(r"\b(monthly|month|mom)\b", q_lower):
        time_grain = "monthly"
    elif re.search(r"\b(quarterly|quarter|qoq)\b", q_lower):
        time_grain = "quarterly"
    elif re.search(r"\b(yearly|annual|annually|year|yoy)\b", q_lower):
        time_grain = "yearly"

    sub_tasks = decompose_tasks(norm_query)

    return IntentAnalysis(
        raw_query=raw_query,
        primary_intent=primary_intent,
        normalized_query=norm_query,
        retrieval_query=retrieval_q,
        chart_type_hint=chart_hint,
        target_metric=target_metric,
        target_dimension=target_dimension,
        time_grain=time_grain,
        sub_tasks=sub_tasks,
        confidence=0.95,
    )
