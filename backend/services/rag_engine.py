"""
RAG (Retrieval-Augmented Generation) engine powered by AI Harness and OKF.
Orchestrates: query understanding → FAISS retrieval → OKF Knowledge Fusion → prompt assembly → LLM streaming.
"""
from collections import defaultdict
import json
import logging
import re
from typing import AsyncIterator, Optional

from core.config import settings
from services import vector_store, ollama_client
from services.harness import default_okf, analyze_intent, IntentType, default_privacy_guard

logger = logging.getLogger(__name__)


# ── System prompts ────────────────────────────────────────────────────────────

BUSINESS_SYSTEM_PROMPT = (
    "Read the context below and answer using ONLY the exact facts written in it. "
    "Do NOT add any URLs, website links, or information not present in the context. "
    "If the answer is not in the context, say: Not found in the uploaded documents."
)

ACADEMIC_SYSTEM_PROMPT = (
    "Read the context below and answer using ONLY the exact facts written in it. "
    "Do NOT add any URLs, website links, or information not present in the context. "
    "If the answer is not in the context, say: Not found in the uploaded documents."
)

STUDENT_SYSTEM_PROMPT = ACADEMIC_SYSTEM_PROMPT

ANALYTICS_SYSTEM_PROMPT = (
    "Read the context below and answer using ONLY the exact facts written in it. "
    "Be precise with numbers. Do NOT add any URLs or information not in the context. "
    "If the answer is not in the context, say: Not found in the uploaded documents."
)

STOPWORDS = {
    'is', 'the', 'a', 'an', 'what', 'how', 'why', 'when', 'where', 'which',
    'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do',
    'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can',
    'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from', 'and', 'but',
    'or', 'not', 'it', 'its', 'this', 'that', 'these', 'those', 'i', 'me',
    'you', 'your', 'he', 'she', 'we', 'they', 'their', 'us', 'tell', 'give',
    'explain', 'define', 'describe', 'list', 'about',
}


def _keyword_rerank(results: list, question: str, faiss_weight: float = 0.7, keyword_weight: float = 0.3) -> list:
    """
    Re-rank FAISS results using combined FAISS score + keyword overlap.
    Boosts chunks whose text directly contains the question's exact key terms.
    Returns sorted list, lower combined score = better match.
    """
    q_words = set(re.sub(r'[^\w\s]', '', question.lower()).split()) - STOPWORDS
    if not q_words:
        return results

    reranked = []
    for doc, faiss_score in results:
        text_lower = doc.page_content.lower()
        matches = sum(1 for w in q_words if re.search(rf'\b{re.escape(w)}\b', text_lower))
        keyword_score = matches / len(q_words)
        norm_faiss = min(faiss_score / 2.0, 1.0)
        combined = (faiss_weight * norm_faiss) - (keyword_weight * keyword_score)
        reranked.append((doc, combined))

    reranked.sort(key=lambda x: x[1])
    return reranked


def _build_rag_prompt(
    question: str,
    context_chunks: list,
    workspace_type: str = "business",
) -> tuple[str, str, str]:
    """
    Build (system_prompt, assistant_context, user_prompt) from retrieved chunks.
    Uses OKF fusion for structural normalization and deduplication.
    """
    q_lower = question.lower().strip()

    is_summary = bool(re.search(
        r'\b(tell me about|summarize|summary|overview|about the pdf|about this pdf|give me details about|describe the pdf|describe this)\b',
        q_lower
    ))
    is_specific_field = bool(re.search(
        r'\b(education|certificate|skill|experience|project|contact|address|email|phone|language|achievement|declaration|objective|profile)\b',
        q_lower
    ))

    system = BUSINESS_SYSTEM_PROMPT if workspace_type == "business" else STUDENT_SYSTEM_PROMPT

    if not context_chunks:
        context_text = "No relevant documents found in the knowledge base."
    else:
        # Fuse via OKF to eliminate duplicates and normalize text
        okf_res = default_okf.fuse(question, context_chunks)
        context_text = okf_res.fused_context

    assistant_context = context_text

    if is_summary:
        system = (
            "You are a helpful assistant. Read the document content below and write a clear, "
            "structured summary. Include all important sections like skills, education, experience, "
            "projects, certifications, and achievements if present. Be thorough. "
            "Do not output any chain-of-thought, reasoning steps, or think tags. Output the final answer immediately."
        )
        user_prompt = f"""Document content:
{assistant_context}

Write a structured summary of the above document covering all key sections."""

    elif is_specific_field:
        system = (
            "You are a helpful assistant. Extract and list ONLY the information directly asked about. "
            "Do not add information from other sections. Be complete - list all items in that section. "
            "Do not output any chain-of-thought, reasoning steps, or think tags. Output the final answer immediately."
        )
        user_prompt = f"""Document content:
{assistant_context}

Question: {question}

Answer by listing only the relevant information asked. Be complete and include all items."""

    else:
        system = (
            f"{system} Answer the question directly using only the facts in the document. "
            "Do not copy raw document text. Do not echo or repeat the question. Never output 'Question:' or 'Answer:'. "
            "Do not output any chain-of-thought, reasoning steps, or think tags. Output the direct answer immediately."
        )
        user_prompt = f"""Document content:
{assistant_context}

Question: {question}

Direct answer:"""

    return system, assistant_context, user_prompt


async def rag_stream(
    question: str,
    workspace_id: int | list[int],
    workspace_type: str = "business",
    model: Optional[str] = None,
    top_k: Optional[int] = None,
    chat_history: Optional[list[dict]] = None,
) -> AsyncIterator[str]:
    """
    Full AI Harness + OKF RAG pipeline with streaming output.
    Yields JSON events for UI trace progress and sanitized plain-text LLM tokens.
    """
    top_k = top_k or settings.TOP_K_RETRIEVAL

    # 0. Privacy Guard Check
    if default_privacy_guard.is_instruction_disclosure_attempt(question):
        refusal = default_privacy_guard.get_secure_refusal_message()
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
            "message": "No citations available",
        }) + "\n"
        return

    # 1. Intent Analysis with follow-up context resolution
    intent_analysis = analyze_intent(question, history=chat_history)
    yield json.dumps({
        "type": "trace",
        "step": "understanding",
        "message": f"Question understood: {intent_analysis.primary_intent.value.replace('_', ' ').title()}",
    }) + "\n"

    # 2. Retrieval with normalized query
    search_q = intent_analysis.retrieval_query or question
    results = vector_store.search(workspace_id, search_q, top_k=top_k * 2)
    results = _keyword_rerank(results, question)
    results = results[:top_k]

    yield json.dumps({
        "type": "trace",
        "step": "searching",
        "message": "RAG search started",
    }) + "\n"

    if not results:
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
    okf_res = default_okf.fuse(question, results)

    yield json.dumps({
        "type": "trace",
        "step": "retrieving",
        "message": f"Retrieved and fused {len(okf_res.citations)} relevant document source(s)",
    }) + "\n"

    system, assistant_context, user_prompt = _build_rag_prompt(question, results, workspace_type)

    yield json.dumps({
        "type": "trace",
        "step": "assembling",
        "message": f"Context assembled with OKF ({okf_res.estimated_tokens} tokens)",
    }) + "\n"

    yield json.dumps({
        "type": "trace",
        "step": "answering",
        "message": f"Answer generation started ({model or settings.DEFAULT_LLM_MODEL})",
    }) + "\n"

    full_answer = ""
    async for token in ollama_client.chat_stream(
        prompt=user_prompt,
        system=system,
        context=None,
        model=model or settings.DEFAULT_LLM_MODEL,
    ):
        full_answer += token
        yield token

    yield "\n"

    # Only emit sources if not a "not found" response
    not_found = "not found" in full_answer.lower()
    final_sources = [] if not_found else okf_res.citations

    yield json.dumps({"type": "sources", "data": final_sources}) + "\n"

    yield json.dumps({
        "type": "trace",
        "step": "citations",
        "message": f"Verified {len(final_sources)} citation(s)",
    }) + "\n"


async def rag_complete(
    question: str,
    workspace_id: int | list[int],
    workspace_type: str = "business",
    model: Optional[str] = None,
) -> dict:
    """
    Non-streaming RAG with OKF Knowledge Fusion and Privacy Guard. Returns answer + sources dict.
    """
    if default_privacy_guard.is_instruction_disclosure_attempt(question):
        return {
            "answer": default_privacy_guard.get_secure_refusal_message(),
            "sources": [],
            "model_used": model or settings.DEFAULT_LLM_MODEL,
            "workspace_id": workspace_id,
        }

    top_k = settings.TOP_K_RETRIEVAL
    intent_analysis = analyze_intent(question)
    search_q = intent_analysis.retrieval_query or question
    results = vector_store.search(workspace_id, search_q, top_k=top_k)

    if not results:
        return {
            "answer": "Not found in the uploaded documents.",
            "sources": [],
            "model_used": model or settings.DEFAULT_LLM_MODEL,
            "workspace_id": workspace_id,
        }

    okf_res = default_okf.fuse(question, results)
    system, assistant_context, user_prompt = _build_rag_prompt(question, results, workspace_type)

    answer = await ollama_client.chat_complete(
        prompt=user_prompt,
        system=system,
        context=None,
        model=model or settings.DEFAULT_LLM_MODEL,
    )

    not_found = "not found" in answer.lower()
    sources = [] if not_found else okf_res.citations

    return {
        "answer": answer,
        "sources": sources,
        "model_used": model or settings.DEFAULT_LLM_MODEL,
        "workspace_id": workspace_id,
        "okf_metrics": {
            "raw_chunks": okf_res.raw_chunk_count,
            "fused_chunks": okf_res.fused_chunk_count,
            "dedup_ratio": okf_res.deduplication_ratio,
        },
    }
