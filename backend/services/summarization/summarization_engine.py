"""
Core summarization engine for the Universal Summarization System.

Handles:
  - Six summary modes (quick, detailed, simple, study, executive, keypoints)
  - Map-reduce chunking for long content (critical for tinyllama's 2048-token window)
  - Hallucination-grounded system prompt
  - Streaming output via AsyncIterator

Context budget for tinyllama:
  - 2048 total tokens ≈ ~1600 words ≈ ~8000 characters
  - We use 1500-char content chunks to leave room for the prompt + output
"""
import logging
from typing import AsyncIterator, Optional

from services import ollama_client
from core.config import settings

logger = logging.getLogger(__name__)

# Safe content chunk size for tinyllama (characters, not tokens)
_CHUNK_SIZE = 1400

# Summarization system prompt — grounded, anti-hallucination
SUMMARIZE_SYSTEM_PROMPT = """You are a precise and factual summarization assistant.

STRICT RULES:
- Summarize ONLY the content that is explicitly provided to you.
- Do NOT invent facts, statistics, names, quotes, timestamps, or conclusions.
- Do NOT add information from your training data.
- If a piece of information is not in the provided content, say "Not available in the provided source."
- Preserve important facts, numbers, names, and key relationships from the source.
- Write in clear, student-friendly English.
- Use Markdown headings (##) and bullet points (-) for structure.
- Never repeat the same point more than once.
- Keep the output focused and well-organized."""

# Mode-specific instructions
_MODE_INSTRUCTIONS = {
    "quick": """Generate a QUICK SUMMARY with this exact structure:

## Overview
One or two sentences describing what this content is about.

## Key Points
- List 5 to 8 of the most important points as bullet points.
- Each point should be concise (one sentence).

## Takeaway
The single most important conclusion from this content.""",

    "detailed": """Generate a DETAILED SUMMARY with this exact structure:

## Overview
A paragraph explaining what this content covers.

## Key Points
5 to 10 important points as bullet points.

## Detailed Summary
A section-by-section explanation of the main ideas. Use ## subheadings for each major topic.

## Important Details
Important facts, numbers, names, examples, or findings from the content.

## Conclusion
The main conclusions or takeaways.""",

    "simple": """Generate a SIMPLE EXPLANATION suitable for a student or beginner.

## What is this about?
Explain in plain, simple English what this content is about.

## Main Ideas
Explain the 4 to 6 main ideas in simple language. Use everyday examples where possible.

## What did we learn?
The most important lesson from this content, in 2 to 3 sentences.""",

    "study": """Generate STUDY NOTES for exam preparation.

## Topic
State the main topic.

## Key Definitions
Define all important terms and concepts mentioned in the content.

## Important Concepts
List and briefly explain the most important concepts.

## Key Facts and Numbers
List any important facts, statistics, formulas, or numbers.

## Summary
3 to 5 exam-ready points that cover the most important ideas.""",

    "executive": """Generate an EXECUTIVE SUMMARY.

## Purpose
What is the purpose or subject of this content?

## Main Findings
The most important findings or information.

## Supporting Evidence
Key facts, data, or examples that support the findings.

## Conclusions
What conclusions are drawn?

## Recommendations
Any recommendations mentioned in the source (if none exist, write "No recommendations stated in source.")""",

    "keypoints": """Extract and list the KEY POINTS from this content.

## Key Points
- List every important point as a bullet.
- Each bullet should be one clear, complete sentence.
- Include important facts, numbers, and names.
- Do not include filler or general statements.
- Aim for 8 to 15 key points.""",
}


def _split_into_chunks(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks that fit within the LLM context window."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    overlap = 200  # chars of overlap to preserve context
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at a paragraph boundary
        if end < len(text):
            break_pos = text.rfind("\n\n", start, end)
            if break_pos == -1:
                break_pos = text.rfind("\n", start, end)
            if break_pos == -1:
                break_pos = text.rfind(". ", start, end)
            if break_pos != -1 and break_pos > start:
                end = break_pos

        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end

    return [c for c in chunks if c.strip()]


async def _summarize_chunk(
    chunk: str,
    chunk_num: int,
    total_chunks: int,
    mode: str,
    source_label: str,
) -> str:
    """Summarize a single chunk synchronously (non-streaming, for map step)."""
    if total_chunks == 1:
        instruction = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["quick"])
        prompt = f"""Source: {source_label}

Content:
{chunk}

{instruction}"""
    else:
        prompt = f"""Source: {source_label} (Part {chunk_num} of {total_chunks})

Content:
{chunk}

Extract the key facts, important points, and conclusions from this section.
Use bullet points. Be concise. Do not invent information."""

    result_tokens = []
    async for token in ollama_client.chat_stream(
        prompt=prompt,
        system=SUMMARIZE_SYSTEM_PROMPT,
        model=settings.DEFAULT_LLM_MODEL,
        max_tokens=400 if total_chunks > 1 else 512,
    ):
        result_tokens.append(token)

    return "".join(result_tokens).strip()


async def summarize_stream(
    content: str,
    summary_type: str = "quick",
    source_label: str = "Provided content",
    source_type: str = "text",
) -> AsyncIterator[str]:
    """
    Main summarization function — yields text tokens as they arrive.

    For short content (< _CHUNK_SIZE chars):
      → Single direct LLM call with the requested mode.

    For long content:
      → Map: Summarize each chunk independently (non-streaming).
      → Reduce: Combine chunk summaries and generate the final summary (streaming).
    """
    content = (content or "").strip()
    if not content:
        yield "⚠️ No content was provided to summarize."
        return

    summary_type = summary_type if summary_type in _MODE_INSTRUCTIONS else "quick"
    chunks = _split_into_chunks(content)
    total_chunks = len(chunks)

    logger.info(
        f"Summarizing {len(content)} chars in {total_chunks} chunk(s), "
        f"mode={summary_type}, source_type={source_type}"
    )

    if total_chunks == 1:
        # Short content — single streaming call
        instruction = _MODE_INSTRUCTIONS[summary_type]
        prompt = f"""Source: {source_label}

Content:
{chunks[0]}

{instruction}"""

        async for token in ollama_client.chat_stream(
            prompt=prompt,
            system=SUMMARIZE_SYSTEM_PROMPT,
            model=settings.DEFAULT_LLM_MODEL,
        ):
            yield token

    else:
        # Long content — Map-Reduce
        # Map phase: summarize each chunk (non-streaming, sequential)
        yield f"*Processing {total_chunks} sections...*\n\n"

        chunk_summaries = []
        for i, chunk in enumerate(chunks, 1):
            yield f"*Summarizing section {i}/{total_chunks}...*\n"
            chunk_summary = await _summarize_chunk(
                chunk=chunk,
                chunk_num=i,
                total_chunks=total_chunks,
                mode=summary_type,
                source_label=source_label,
            )
            chunk_summaries.append(chunk_summary)

        # Reduce phase: combine chunk summaries into final summary (streaming)
        yield "\n\n---\n\n"
        combined = "\n\n".join(
            f"[Section {i+1}]\n{s}" for i, s in enumerate(chunk_summaries)
        )

        instruction = _MODE_INSTRUCTIONS[summary_type]
        final_prompt = f"""Source: {source_label}

The following are summaries of {total_chunks} sections of the source content:

{combined}

Now create the final unified summary using ALL the section summaries above.
{instruction}"""

        async for token in ollama_client.chat_stream(
            prompt=final_prompt,
            system=SUMMARIZE_SYSTEM_PROMPT,
            model=settings.DEFAULT_LLM_MODEL,
        ):
            yield token
