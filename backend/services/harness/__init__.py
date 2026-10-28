"""
AI Harness Package.
Provides Intent Analysis, OKF Knowledge Fusion, Central Orchestration, and Privacy Guard.
"""
from .intent import IntentType, IntentAnalysis, analyze_intent, resolve_followup_context
from .okf_engine import OKFEngine, OKFResult, default_okf, RetrievedChunk, ContradictionRecord
from .orchestrator import AIHarnessOrchestrator, default_harness, HarnessResponse
from .privacy_guard import PrivacyGuard, default_privacy_guard

__all__ = [
    "IntentType",
    "IntentAnalysis",
    "analyze_intent",
    "resolve_followup_context",
    "OKFEngine",
    "OKFResult",
    "default_okf",
    "RetrievedChunk",
    "ContradictionRecord",
    "AIHarnessOrchestrator",
    "default_harness",
    "HarnessResponse",
    "PrivacyGuard",
    "default_privacy_guard",
]
