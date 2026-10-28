"""
Unit and integration tests for AI Harness Orchestrator and Intent Understanding.
"""
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document as LCDocument

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.harness.intent import (
    analyze_intent,
    normalize_query,
    extract_retrieval_query,
    detect_chart_type,
    decompose_tasks,
    IntentType,
)
from services.harness.orchestrator import AIHarnessOrchestrator


def test_intent_classification():
    """Verify accurate intent detection across query variants."""
    # Factual QA
    i1 = analyze_intent("What is the refund policy for enterprise accounts?")
    assert i1.primary_intent == IntentType.FACTUAL_QA

    # Analytics calculation
    i2 = analyze_intent("Calculate total revenue and YoY growth for 2026")
    assert i2.primary_intent == IntentType.ANALYTICS_CALC
    assert i2.target_metric == "revenue"

    # Chart request
    i3 = analyze_intent("Show me a monthly revenue trend line chart")
    assert i3.primary_intent == IntentType.ANALYTICS_CHART
    assert i3.chart_type_hint == "line"

    # Donut / Pie chart
    i4 = analyze_intent("What is the sales breakdown by region pie chart?")
    assert i4.primary_intent == IntentType.ANALYTICS_CHART
    assert i4.chart_type_hint == "pie"

    # Summary
    i5 = analyze_intent("Summarize this document and give me an overview")
    assert i5.primary_intent == IntentType.SUMMARY

    # Comparison / Synthesis
    i6 = analyze_intent("Compare the policies across all documents and contrast differences")
    assert i6.primary_intent in (IntentType.SYNTHESIS, IntentType.COMPARISON)


def test_query_normalization_and_rewriting():
    """Verify acronym expansion and keyword distillation."""
    raw = "Can you please tell me what is the YoY revenue growth?"
    norm = normalize_query(raw)
    assert "year-over-year" in norm

    retrieval_q = extract_retrieval_query(raw)
    # Conversational preambles stripped
    assert not retrieval_q.lower().startswith("can you please")
    assert not retrieval_q.endswith("?")
    assert "revenue" in retrieval_q


def test_task_decomposition():
    """Verify decomposition of multi-part analytical questions."""
    query = "Calculate 2023 total revenue and compare to 2022 and also show monthly trend"
    sub_tasks = decompose_tasks(query)
    assert len(sub_tasks) >= 2


def test_conversation_followup_resolution():
    """Verify follow-up context resolution for pronouns and elliptical queries."""
    from services.harness.intent import resolve_followup_context

    history = [
        {"role": "user", "content": "What was the total revenue in 2025?"},
        {"role": "assistant", "content": "Total revenue was $15 million in 2025."},
    ]

    # Elliptical query
    resolved_1 = resolve_followup_context("What about 2024?", history)
    assert "2024" in resolved_1
    assert "revenue" in resolved_1.lower()

    # Pronoun query
    resolved_2 = resolve_followup_context("Why did it decrease?", history)
    assert "revenue" in resolved_2.lower()


@pytest.mark.asyncio
async def test_harness_orchestrator_execution():
    """Verify AI Harness end-to-end execution loop with mocked vector store and LLM."""
    harness = AIHarnessOrchestrator(max_retries=1)
    mock_doc = LCDocument(
        page_content="Global revenue reached $120 million in FY2025.",
        metadata={"filename": "annual_report.pdf", "page_number": 4}
    )

    with patch("services.vector_store.search", return_value=[(mock_doc, 0.15)]), \
         patch("services.ollama_client.chat_complete", return_value="Global revenue was $120M in FY2025."):

        resp = await harness.execute_complete(
            question="What was global revenue?",
            workspace_id=1,
            workspace_type="business",
        )

        assert resp.answer == "Global revenue was $120M in FY2025."
        assert len(resp.sources) == 1
        assert resp.sources[0]["document_name"] == "annual_report.pdf"
        assert resp.sources[0]["page_number"] == 4
        assert resp.okf_metrics["raw_chunks"] == 1
        assert resp.okf_metrics["fused_chunks"] == 1
