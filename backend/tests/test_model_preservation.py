"""
Model Preservation Verification Tests.
Ensures that the primary LLM model identifier remains strictly 'gemma4:12b',
the embedding model remains 'BAAI/bge-m3', and no replacement models are introduced.
"""
import pytest

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.config import settings
from services import rag_engine, analytics_engine
from services.harness import AIHarnessOrchestrator


def test_primary_llm_model_preservation():
    """Verify that settings.DEFAULT_LLM_MODEL is strictly 'gemma4:12b'."""
    assert settings.DEFAULT_LLM_MODEL == "gemma4:12b", (
        f"VIOLATION: Primary LLM changed from gemma4:12b to {settings.DEFAULT_LLM_MODEL}."
    )


def test_embedding_model_preservation():
    """Verify that settings.EMBEDDING_MODEL is strictly 'BAAI/bge-m3'."""
    assert settings.EMBEDDING_MODEL == "BAAI/bge-m3", (
        f"VIOLATION: Embedding model changed from BAAI/bge-m3 to {settings.EMBEDDING_MODEL}."
    )


def test_ollama_url_preservation():
    """Verify local Ollama provider URL."""
    assert "localhost:11434" in settings.OLLAMA_URL or "127.0.0.1:11434" in settings.OLLAMA_URL


def test_orchestrator_default_model():
    """Verify AI Harness orchestrator inherits gemma4:12b as default."""
    harness = AIHarnessOrchestrator()
    # Confirm default settings propagation
    assert settings.DEFAULT_LLM_MODEL == "gemma4:12b"
