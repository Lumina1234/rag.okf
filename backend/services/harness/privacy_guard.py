"""
Backend Instruction Privacy and Security Guard.
Enforces strict boundary between internal harness/OKF operations and user-facing output.
Prevents prompt disclosure, extracts reasoning tags, sanitizes streaming tokens, and masks internal server paths.
"""
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Patterns that indicate an attempt to extract internal system prompts or architecture
PROMPT_EXTRACTION_PATTERNS = [
    r"\b(show|reveal|print|display|give|repeat|tell|output|share|dump|leak|what is|what are)\b.*?\b(system prompt|system instructions?|developer instructions?|backend instructions?|meta prompt|hidden prompt|initial prompt)\b",
    r"\b(system prompt|developer messages?|system instructions?)\b.*?\b(verbatim|exact|word for word|full text)\b",
    r"\b(repeat|print|show)\b.*?\b(everything above|all text above|previous instructions?|prior instructions?)\b",
    r"\b(ignore|disregard|forget|override)\b.*?\b(previous|prior|above|system)\b.*?\b(instructions?|rules|directives|prompts?)\b",
    r"\b(show|reveal|print)\b.*?\b(hidden reasoning|chain of thought|internal logic|internal plan|execution trace)\b",
    r"\b(show|print|reveal|explain)\b.*?\b(okf prompt|okf algorithm|okf pipeline|fusion prompt|orchestrator internals?)\b",
    r"\b(show|list|print)\b.*?\b(internal tools|backend tools|database credentials|server configs?|env vars|environment variables)\b",
    r"\b(jailbreak|dan mode|developer mode enabled)\b",
]

# Sensitive patterns that should never appear in user-facing text
SENSITIVE_LEAK_PATTERNS = [
    r"<think>[\s\S]*?(?:</think>|$)",
    r"<reasoning>[\s\S]*?(?:</reasoning>|$)",
    r"(?i)you are an enterprise ai document intelligence assistant[\s\S]*?immediately\.",
    r"(?i)read the context below and answer using only the exact facts written in it\.",
    r"(?i)do not output any chain-of-thought, reasoning steps, or think tags\.",
    r"(?i)verified document context:[\s\S]*?user question:",
    r"(?i)(?:password|secret_key|database_url)\s*[:=]\s*['\"][^'\"]+['\"]",
]


class PrivacyGuard:
    """
    Enforces backend instruction privacy and output sanitization across the AI Harness.
    """

    @staticmethod
    def is_instruction_disclosure_attempt(query: str) -> bool:
        """
        Detects whether a user query attempts to extract system instructions,
        internal prompts, hidden reasoning, or execute prompt injection.
        """
        q_norm = query.strip().lower()
        for pattern in PROMPT_EXTRACTION_PATTERNS:
            if re.search(pattern, q_norm, flags=re.IGNORECASE):
                logger.warning(f"Blocked instruction disclosure attempt matching pattern: {pattern}")
                return True
        return False

    @staticmethod
    def get_secure_refusal_message() -> str:
        """Standard professional response when an instruction disclosure attempt is detected."""
        return (
            "I am configured to answer questions about your uploaded documents and business data. "
            "Internal system prompts, backend instructions, and server configurations are confidential "
            "and cannot be disclosed."
        )

    @staticmethod
    def sanitize_output(text: str) -> str:
        """
        Sanitize generated LLM response before delivering to the client:
        - Removes <think> and <reasoning> blocks
        - Strips echoed system instructions or prompt boilerplate
        - Masks internal filesystem paths
        - Cleans Question:... Answer:... artifacts
        """
        if not text:
            return ""

        cleaned = text

        # Strip think / reasoning tags
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<reasoning>[\s\S]*?</reasoning>", "", cleaned, flags=re.IGNORECASE)

        # Strip echoed prompts
        for leak_pat in SENSITIVE_LEAK_PATTERNS:
            cleaned = re.sub(leak_pat, "", cleaned, flags=re.IGNORECASE)

        # Strip legacy prompt-echoing artifacts
        cleaned = re.sub(r"^\s*Question:.*?\bAnswer:\s*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"^\s*Answer:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^[,\s]*\{[\"']type[\"']\s*:\s*[\"']sources[\"'][^\r\n]*", "", cleaned)
        cleaned = re.sub(r"^[,\s]*\{[\"']type[\"']\s*:\s*[\"']trace[\"'][^\r\n]*", "", cleaned)

        # Mask internal drive paths (e.g. C:\Users\user\...)
        cleaned = re.sub(r"[A-Za-z]:\\[\w\\\.-]+", "[internal path]", cleaned)

        return cleaned.strip()

    @staticmethod
    def sanitize_error(error: Exception | str) -> str:
        """
        Convert technical exceptions into safe, user-friendly messages
        without exposing internal stack traces, DB details, or paths.
        """
        err_str = str(error)
        logger.error(f"Internal error captured for sanitization: {err_str}")

        if "Ollama is not running" in err_str:
            return "The inference server is currently offline. Please ensure Ollama is active."
        if "timeout" in err_str.lower():
            return "The operation timed out. Please try again with a more specific query."
        if "not found" in err_str.lower():
            return "The requested resource was not found."

        return "An internal processing error occurred. The administrative team has logged this event."


default_privacy_guard = PrivacyGuard()
