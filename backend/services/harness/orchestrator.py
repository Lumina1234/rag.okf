"""
AI Harness Orchestrator.
Central execution coordinator for Enterprise RAG, OKF Knowledge Fusion,
Deterministic Business Calculations, Model-Preserving LLM Generation,
and Strict Backend Instruction Privacy.
"""
import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import Any, AsyncIterator, Optional

from core.config import settings
from services import vector_store, ollama_client
from .intent import analyze_intent, IntentType, IntentAnalysis
from .okf_engine import default_okf, OKFResult
from .privacy_guard import default_privacy_guard

logger = logging.getLogger(__name__)


@dataclass
class HarnessResponse:
    answer: str
    sources: list[dict[str, Any]]
    model_used: str
    intent: str
    okf_metrics: dict[str, Any]
    retries_used: int = 0


class AIHarnessOrchestrator:
    """
    Production-grade AI Harness Orchestrator.
    Coordinates Query Understanding -> Retrieval -> OKF Fusion -> LLM -> Privacy Guard -> Response.
    Preserves gemma4:12b and shields internal backend instructions.
    """

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self.okf = default_okf
        self.privacy = default_privacy_guard

    def build_system_prompt(self, workspace_type: str = "business", intent: IntentType = IntentType.FACTUAL_QA) -> str:
        """Construct a crisp, unambiguous system prompt with zero hallucination allowances."""
        base = (
            "You are an enterprise AI document intelligence assistant. "
            "Read the provided verified context and answer using ONLY the exact facts and figures contained within it. "
            "Never fabricate information, statistics, dates, or citations. "
            "If the answer cannot be determined from the context, state clearly: 'Not found in the uploaded documents.' "
            "Do not output any chain-of-thought, reasoning steps, or think tags. Output the final answer immediately."
        )
        if intent == IntentType.SUMMARY:
            return (
                "You are an enterprise document summarizer. "
                "Produce a structured, comprehensive executive summary covering all primary sections, "
                "key metrics, and conclusions present in the context. "
                "Do not invent facts or output reasoning tags. Output the structured summary immediately."
            )
        elif intent == IntentType.SYNTHESIS or intent == IntentType.COMPARISON:
            return (
                "You are an enterprise document analyst. "
                "Synthesize and compare facts across the provided sources. "
                "Highlight key agreements, differences, and any document discrepancies noted in the context. "
                "Do not invent facts. Output the direct comparative synthesis immediately."
            )
        return base

    def build_user_prompt(self, question: str, fused_context: str) -> str:
        """Format user prompt strictly isolating evidence and instruction."""
        return f"""Verified Document Context:
{fused_context}

User Question:
{question}

Provide a direct, factual answer based strictly on the context above:"""

    async def execute_stream(
        self,
        question: str,
        workspace_id: int | list[int],
        workspace_type: str = "business",
        model: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Full streaming execution loop:
        Privacy Check -> Intent -> Search -> OKF Fusion -> gemma4:12b Generation -> Sanitization -> Citations.
        Yields JSON trace events and sanitized plain-text tokens.
        """
        active_model = model or settings.DEFAULT_LLM_MODEL
        retrieval_k = top_k or settings.TOP_K_RETRIEVAL

        # 0. Backend Instruction Privacy Guard Check
        if self.privacy.is_instruction_disclosure_attempt(question):
            refusal = self.privacy.get_secure_refusal_message()
            yield json.dumps({
                "type": "trace",
                "step": "understanding",
                "message": "Question understood",
            }) + "\n"
            yield json.dumps({
                "type": "trace",
                "step": "answering",
                "message": "Answer generation completed",
            }) + "\n"
            yield refusal + "\n"
            yield json.dumps({"type": "sources", "data": []}) + "\n"
            yield json.dumps({
                "type": "trace",
                "step": "citations",
                "message": "No citations applicable",
            }) + "\n"
            return

        # 1. Intent & Query Understanding
        yield json.dumps({
            "type": "trace",
            "step": "understanding",
            "message": "Question understood",
        }) + "\n"

        intent_res: IntentAnalysis = analyze_intent(question)
        logger.info(f"Harness Intent: {intent_res.primary_intent.value} | Query: {intent_res.normalized_query}")

        yield json.dumps({
            "type": "trace",
            "step": "planning",
            "message": f"Task plan: {intent_res.primary_intent.value.replace('_', ' ').title()}",
        }) + "\n"

        # 2. Knowledge Retrieval (Workspace-isolated FAISS)
        yield json.dumps({
            "type": "trace",
            "step": "retrieving",
            "message": "Retrieving relevant evidence from workspace...",
        }) + "\n"

        raw_results = vector_store.search(workspace_id, intent_res.retrieval_query, top_k=retrieval_k * 2)

        if not raw_results:
            yield json.dumps({
                "type": "trace",
                "step": "retrieving",
                "message": "No relevant documents found",
            }) + "\n"
            yield json.dumps({
                "type": "trace",
                "step": "assembling",
                "message": "Context assembled",
            }) + "\n"
            yield json.dumps({
                "type": "trace",
                "step": "answering",
                "message": "Answer generation completed",
            }) + "\n"
            yield "Not found in the uploaded documents.\n"
            yield json.dumps({"type": "sources", "data": []}) + "\n"
            yield json.dumps({
                "type": "trace",
                "step": "citations",
                "message": "No citations available",
            }) + "\n"
            return

        # 3. Optimized Knowledge Fusion (OKF)
        yield json.dumps({
            "type": "trace",
            "step": "fusing",
            "message": f"Fusing context via OKF ({len(raw_results)} passages evaluated)...",
        }) + "\n"

        okf_res: OKFResult = self.okf.fuse(intent_res.normalized_query, raw_results)

        yield json.dumps({
            "type": "trace",
            "step": "assembling",
            "message": f"Context assembled ({okf_res.estimated_tokens} tokens)",
        }) + "\n"

        # 4. Prompt Assembly & Model Call
        system_prompt = self.build_system_prompt(workspace_type, intent_res.primary_intent)
        user_prompt = self.build_user_prompt(question, okf_res.fused_context)

        yield json.dumps({
            "type": "trace",
            "step": "answering",
            "message": "Answer generation started",
        }) + "\n"

        # Bounded streaming generation with retry
        full_tokens = []
        retries = 0
        in_think_block = False

        while retries <= self.max_retries:
            full_tokens.clear()
            async for token in ollama_client.chat_stream(
                prompt=user_prompt,
                system=system_prompt,
                model=active_model,
            ):
                # Filter out think block tokens on the fly
                if "<think>" in token:
                    in_think_block = True
                if in_think_block:
                    if "</think>" in token:
                        in_think_block = False
                        token = token.split("</think>")[-1]
                    else:
                        continue

                clean_token = self.privacy.sanitize_output(token) if token else ""
                if clean_token:
                    full_tokens.append(clean_token)
                    yield clean_token

            answer_str = "".join(full_tokens).strip()
            if answer_str and not answer_str.startswith("⚠️ **LLM Error:"):
                break

            retries += 1
            if retries <= self.max_retries:
                logger.warning(f"Generation attempt {retries} produced empty/error result. Retrying...")
                await asyncio.sleep(1.0)

        yield "\n"

        # 5. Output Validation & Citations
        final_answer = "".join(full_tokens).strip()
        is_not_found = "not found" in final_answer.lower() or not final_answer

        final_sources = [] if is_not_found else okf_res.citations
        yield json.dumps({"type": "sources", "data": final_sources}) + "\n"

        yield json.dumps({
            "type": "trace",
            "step": "citations",
            "message": f"Verified {len(final_sources)} citation(s)",
        }) + "\n"

    async def execute_complete(
        self,
        question: str,
        workspace_id: int | list[int],
        workspace_type: str = "business",
        model: Optional[str] = None,
    ) -> HarnessResponse:
        """Non-streaming execution loop with privacy guard."""
        active_model = model or settings.DEFAULT_LLM_MODEL

        # 0. Privacy Guard Check
        if self.privacy.is_instruction_disclosure_attempt(question):
            return HarnessResponse(
                answer=self.privacy.get_secure_refusal_message(),
                sources=[],
                model_used=active_model,
                intent="security_refusal",
                okf_metrics={},
            )

        intent_res = analyze_intent(question)
        raw_results = vector_store.search(workspace_id, intent_res.retrieval_query, top_k=settings.TOP_K_RETRIEVAL * 2)

        if not raw_results:
            return HarnessResponse(
                answer="Not found in the uploaded documents.",
                sources=[],
                model_used=active_model,
                intent=intent_res.primary_intent.value,
                okf_metrics={},
            )

        okf_res = self.okf.fuse(intent_res.normalized_query, raw_results)
        system_prompt = self.build_system_prompt(workspace_type, intent_res.primary_intent)
        user_prompt = self.build_user_prompt(question, okf_res.fused_context)

        answer = await ollama_client.chat_complete(
            prompt=user_prompt,
            system=system_prompt,
            model=active_model,
        )

        sanitized_ans = self.privacy.sanitize_output(answer)
        is_not_found = "not found" in sanitized_ans.lower()
        sources = [] if is_not_found else okf_res.citations

        return HarnessResponse(
            answer=sanitized_ans,
            sources=sources,
            model_used=active_model,
            intent=intent_res.primary_intent.value,
            okf_metrics={
                "raw_chunks": okf_res.raw_chunk_count,
                "fused_chunks": okf_res.fused_chunk_count,
                "dedup_ratio": okf_res.deduplication_ratio,
                "contradictions": len(okf_res.contradictions),
            },
        )


default_harness = AIHarnessOrchestrator()
