"""
Unit tests for Optimized Knowledge Fusion (OKF) Engine.
Tests all 4 stages:
Stage A: Structural Normalization
Stage B: Semantic Deduplication
Stage C: Fact Fusion & Contradiction Detection
Stage D: Relevance Ranking & Context Window Packing
"""
import pytest
from langchain_core.documents import Document as LCDocument

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.harness.okf_engine import OKFEngine, RetrievedChunk, default_okf


def test_okf_stage_a_structural_normalization():
    """Verify stripping of page headers/footers and noise while preserving tables and formatting."""
    okf = OKFEngine()
    noisy_text = """
    Page 1 of 10
    --- Page 2 ---
    12
    Acme Corp Financial Report
    
    | Metric | Value |
    | Revenue | $50M |
    
    • Key highlight 1
    • Key highlight 2
    
    Page 2 of 10
    """
    cleaned = okf.normalize_chunk_text(noisy_text)
    assert "Page 1 of 10" not in cleaned
    assert "--- Page 2 ---" not in cleaned
    assert "| Metric | Value |" in cleaned
    assert "Revenue" in cleaned
    assert "$50M" in cleaned
    assert "Key highlight 1" in cleaned


def test_okf_stage_b_semantic_deduplication():
    """Verify that exact and near-duplicate passages are eliminated without losing unique facts."""
    okf = OKFEngine(dedup_threshold=0.80)
    chunk1 = RetrievedChunk(
        text="The software platform supports Python, TypeScript, Java, and Go for backend microservices.",
        metadata={"filename": "doc1.pdf", "page_number": 1},
        score=0.1,
    )
    # Near duplicate with minor variation
    chunk2 = RetrievedChunk(
        text="The software platform supports Python, TypeScript, Java, and Go for cloud microservices.",
        metadata={"filename": "doc2.pdf", "page_number": 3},
        score=0.2,
    )
    # Distinct chunk
    chunk3 = RetrievedChunk(
        text="Database clustering is handled by PostgreSQL 16 with streaming replication.",
        metadata={"filename": "doc3.pdf", "page_number": 5},
        score=0.15,
    )

    deduped = okf.deduplicate([chunk1, chunk2, chunk3])
    # The near-duplicate should be collapsed
    assert len(deduped) == 2
    texts = [c.text for c in deduped]
    assert any("PostgreSQL 16" in t for t in texts)


def test_okf_stage_c_contradiction_detection():
    """Verify that conflicting numerical statements are detected and reported across documents."""
    okf = OKFEngine()
    chunk1 = RetrievedChunk(
        text="According to the initial audit, Q4 revenue was $15 million.",
        metadata={"filename": "initial_audit.pdf", "page_number": 2},
    )
    chunk2 = RetrievedChunk(
        text="The revised financial statement showed that Q4 revenue was $18 million.",
        metadata={"filename": "revised_audit.pdf", "page_number": 2},
    )

    contradictions = okf.detect_contradictions([chunk1, chunk2], "What was Q4 revenue?")
    assert len(contradictions) >= 1
    c = contradictions[0]
    assert c.entity_or_topic == "revenue"
    assert "initial_audit.pdf" in c.sources
    assert "revised_audit.pdf" in c.sources


def test_okf_stage_d_context_packing_and_citations():
    """Verify token budget enforcement and clean source citation preservation."""
    okf = OKFEngine(max_context_tokens=100)  # low token budget to test bound
    chunks = [
        LCDocument(page_content=f"Paragraph {i}: Detailed operational procedures for branch {i}.", metadata={"filename": f"branch_{i}.pdf", "page_number": i})
        for i in range(20)
    ]

    res = okf.fuse("What are the branch procedures?", chunks)
    assert res.estimated_tokens <= 150
    assert len(res.citations) > 0
    # Every citation must contain document_name
    for cite in res.citations:
        assert "document_name" in cite
        assert cite["document_name"].startswith("branch_")
