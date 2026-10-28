"""
Optimized Knowledge Fusion (OKF) Engine.
A deterministic, pre-generation knowledge compilation pipeline:
Raw Chunks -> Structural Normalization -> Semantic Deduplication ->
Fact Fusion & Contradiction Detection -> Relevance Ranking & Context Window Packing.
"""
from dataclasses import dataclass, field
import hashlib
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    metadata: dict[str, Any]
    score: float = 0.0  # L2 distance or similarity score
    source_id: str = ""

    def __post_init__(self):
        if not self.source_id:
            filename = self.metadata.get("filename", "unknown")
            page = self.metadata.get("page_number", "0")
            h = hashlib.md5(self.text.strip().encode("utf-8")).hexdigest()[:6]
            self.source_id = f"{filename}:p{page}:{h}"


@dataclass
class ContradictionRecord:
    entity_or_topic: str
    conflicting_statements: list[str]
    sources: list[str]
    description: str


@dataclass
class OKFResult:
    fused_context: str
    citations: list[dict[str, Any]]
    contradictions: list[ContradictionRecord] = field(default_factory=list)
    raw_chunk_count: int = 0
    fused_chunk_count: int = 0
    estimated_tokens: int = 0
    deduplication_ratio: float = 0.0


class OKFEngine:
    """
    Deterministic Knowledge Fusion Engine for RAG.
    Pre-processes and compiles noisy retrieved passages into compact,
    fact-dense, non-redundant, cited context for the LLM.
    """

    def __init__(
        self,
        dedup_threshold: float = 0.82,
        max_context_tokens: int = 2800,
        preserve_contradictions: bool = True,
    ):
        self.dedup_threshold = dedup_threshold
        self.max_context_tokens = max_context_tokens
        self.preserve_contradictions = preserve_contradictions

    # ── Stage A: Structural Normalization ─────────────────────────────────────
    def normalize_chunk_text(self, text: str) -> str:
        """
        Strip repeated page headers, footers, navigation artifacts, and noise,
        while preserving markdown tables, key-value pairs, headings, numbers, and bullets.
        """
        if not text:
            return ""

        # Normalize line endings
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove repetitive header/footer page patterns (e.g. "Page 1 of 12", "--- Page 3 ---")
        cleaned = re.sub(r"(?i)\bpage\s+\d+\s+of\s+\d+\b", "", cleaned)
        cleaned = re.sub(r"(?i)^\s*---*\s*(?:page\s*\d+)?\s*---*\s*$", "", cleaned, flags=re.MULTILINE)

        # Remove isolated page numbers on a single line
        cleaned = re.sub(r"^\s*\d{1,4}\s*$", "", cleaned, flags=re.MULTILINE)

        # Preserve markdown tables and bullet points, but collapse 3+ consecutive newlines
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        # Normalize horizontal tabs and non-breaking spaces
        cleaned = cleaned.replace("\u00a0", " ").replace("\t", "    ")

        # Strip dangling leading/trailing punctuation or isolated bullets
        cleaned = re.sub(r"^[•\-\*\s]+$", "", cleaned, flags=re.MULTILINE)

        return cleaned.strip()

    # ── Stage B: Semantic Deduplication ───────────────────────────────────────
    def _lexical_similarity(self, text_a: str, text_b: str) -> float:
        """
        Compute character and token-level Jaccard similarity between two texts.
        """
        words_a = set(re.findall(r"\w+", text_a.lower()))
        words_b = set(re.findall(r"\w+", text_b.lower()))
        if not words_a or not words_b:
            return 0.0

        intersection = words_a.intersection(words_b)
        union = words_a.union(words_b)
        return len(intersection) / len(union)

    def deduplicate(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """
        Remove exact and near-duplicate chunks.
        When two passages are near duplicates, retain the one with higher factual density.
        """
        unique_chunks: list[RetrievedChunk] = []
        seen_exact_hashes = set()

        for chunk in chunks:
            norm_text = self.normalize_chunk_text(chunk.text)
            if not norm_text or len(norm_text) < 15:
                continue

            # Check exact duplicate hash
            exact_hash = hashlib.sha256(norm_text.lower().encode("utf-8")).hexdigest()
            if exact_hash in seen_exact_hashes:
                continue

            # Check near-duplicates against already accepted chunks
            is_near_dup = False
            for idx, existing in enumerate(unique_chunks):
                sim = self._lexical_similarity(norm_text, existing.text)
                if sim >= self.dedup_threshold:
                    is_near_dup = True
                    # If current chunk has more content/information density (numbers/keywords), swap
                    if len(norm_text) > len(existing.text) * 1.25:
                        unique_chunks[idx] = RetrievedChunk(
                            text=norm_text,
                            metadata=chunk.metadata,
                            score=min(chunk.score, existing.score),
                            source_id=chunk.source_id,
                        )
                    break

            if not is_near_dup:
                seen_exact_hashes.add(exact_hash)
                unique_chunks.append(
                    RetrievedChunk(
                        text=norm_text,
                        metadata=chunk.metadata,
                        score=chunk.score,
                        source_id=chunk.source_id,
                    )
                )

        return unique_chunks

    # ── Stage C: Fact Fusion & Contradiction Detection ────────────────────────
    def detect_contradictions(
        self, chunks: list[RetrievedChunk], query: str
    ) -> list[ContradictionRecord]:
        """
        Detect conflicting statements, conflicting numbers, or opposing metrics
        across documents for the same subject/entity.
        """
        contradictions: list[ContradictionRecord] = []
        # Extract numerical assertions with surrounding context: e.g., "$10 million", "25%", "2024"
        pattern = r"(\b(?:revenue|sales|profit|margin|growth|total|cost|price|fee)\b[^.\n]{1,60}?[\$€₹]?\s*\d+(?:\.\d+)?(?:\s*(?:million|billion|thousand|%|percent))?)"

        fact_map: dict[str, list[tuple[str, str, str]]] = {}
        for chunk in chunks:
            fname = chunk.metadata.get("filename", "Doc")
            matches = re.findall(pattern, chunk.text, flags=re.IGNORECASE)
            for m in matches:
                m_str = m.strip()
                # Find the key metric word
                metric_key_match = re.search(r"\b(revenue|sales|profit|margin|growth|total|cost|price|fee)\b", m_str, flags=re.IGNORECASE)
                if metric_key_match:
                    metric = metric_key_match.group(1).lower()
                    fact_map.setdefault(metric, []).append((m_str, fname, chunk.source_id))

        # Check for divergent figures under the same metric
        for metric, occurrences in fact_map.items():
            if len(occurrences) > 1:
                # Group distinct values
                distinct_values = set()
                sources = []
                statements = []
                for stmt, src_file, src_id in occurrences:
                    num_match = re.search(r"[\$€₹]?\s*\d+(?:\.\d+)?(?:\s*(?:million|billion|thousand|%))?", stmt)
                    if num_match:
                        distinct_values.add(num_match.group(0).strip())
                        sources.append(src_file)
                        statements.append(f"[{src_file}]: \"{stmt}\"")

                if len(distinct_values) > 1:
                    contradictions.append(
                        ContradictionRecord(
                            entity_or_topic=metric,
                            conflicting_statements=list(dict.fromkeys(statements))[:3],
                            sources=list(dict.fromkeys(sources)),
                            description=f"Potential discrepancy found in '{metric}': differing values {list(distinct_values)}",
                        )
                    )

        return contradictions

    # ── Stage D: Relevance Ranking & Context Window Packing ───────────────────
    def _estimate_tokens(self, text: str) -> int:
        """Heuristic token estimation: ~4 chars per token for English."""
        return max(1, len(text) // 4)

    def pack_context(
        self,
        chunks: list[RetrievedChunk],
        query: str,
        contradictions: list[ContradictionRecord],
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Rank passages, incorporate contradiction alerts if any, and pack within token budget.
        """
        if not chunks:
            return "No relevant context found in documents.", []

        # Sort chunks: lower score = better in FAISS L2, or higher keyword match
        q_words = set(re.findall(r"\w+", query.lower()))
        def rank_key(c: RetrievedChunk):
            matches = sum(1 for w in q_words if w in c.text.lower())
            # Combined rank: FAISS score adjusted for keyword density
            return c.score - (0.2 * matches)

        sorted_chunks = sorted(chunks, key=rank_key)

        packed_sections = []
        citations = []
        seen_citations = set()
        current_tokens = 0

        # Prepend contradiction notices if detected so LLM can report them honestly
        if contradictions:
            contradiction_notes = ["### [OKF Note: Potential Document Discrepancy Detected]"]
            for c in contradictions:
                contradiction_notes.append(f"- **{c.entity_or_topic.title()}**: {c.description}")
                for stmt in c.conflicting_statements:
                    contradiction_notes.append(f"  * {stmt}")
            contr_text = "\n".join(contradiction_notes) + "\n\n"
            current_tokens += self._estimate_tokens(contr_text)
            packed_sections.append(contr_text)

        for chunk in sorted_chunks:
            fname = chunk.metadata.get("filename", "Unknown Document")
            page = chunk.metadata.get("page_number")
            source_tag = f"Source: {fname}" + (f" (Page {page})" if page is not None else "")

            section_text = f"[{source_tag}]\n{chunk.text}\n"
            sec_tokens = self._estimate_tokens(section_text)

            if current_tokens + sec_tokens > self.max_context_tokens:
                # If we have at least one chunk, break to respect budget
                if packed_sections:
                    break
                else:
                    # Truncate to fit
                    max_chars = self.max_context_tokens * 4
                    section_text = section_text[:max_chars] + "...\n"
                    packed_sections.append(section_text)
                    cite_key = (fname, page)
                    if cite_key not in seen_citations:
                        seen_citations.add(cite_key)
                        citations.append({"document_name": fname, **({"page_number": page} if page else {})})
                    break

            packed_sections.append(section_text)
            current_tokens += sec_tokens

            cite_key = (fname, page)
            if cite_key not in seen_citations:
                seen_citations.add(cite_key)
                citations.append({"document_name": fname, **({"page_number": page} if page else {})})

        fused_text = "\n---\n".join(packed_sections).strip()
        return fused_text, citations

    # ── Main OKF Fusion Interface ─────────────────────────────────────────────
    def fuse(
        self,
        query: str,
        retrieved_items: list[Any],
    ) -> OKFResult:
        """
        Execute full OKF pipeline on retrieved items.
        retrieved_items can be a list of (Document, score) tuples or Document objects.
        """
        raw_chunks: list[RetrievedChunk] = []
        for item in retrieved_items:
            if isinstance(item, tuple) and len(item) == 2:
                doc, score = item
                text = getattr(doc, "page_content", str(doc))
                meta = getattr(doc, "metadata", {})
                raw_chunks.append(RetrievedChunk(text=text, metadata=meta, score=float(score)))
            elif hasattr(item, "page_content"):
                raw_chunks.append(RetrievedChunk(text=item.page_content, metadata=item.metadata, score=0.0))
            elif isinstance(item, dict):
                raw_chunks.append(
                    RetrievedChunk(
                        text=item.get("text") or item.get("content", ""),
                        metadata=item.get("metadata", {}),
                        score=float(item.get("score", 0.0)),
                    )
                )

        raw_count = len(raw_chunks)
        if raw_count == 0:
            return OKFResult(
                fused_context="Not found in the uploaded documents.",
                citations=[],
                contradictions=[],
                raw_chunk_count=0,
                fused_chunk_count=0,
                estimated_tokens=0,
                deduplication_ratio=0.0,
            )

        # Stage A & B: Normalization & Deduplication
        deduped = self.deduplicate(raw_chunks)

        # Stage C: Contradiction Detection
        contradictions = []
        if self.preserve_contradictions:
            contradictions = self.detect_contradictions(deduped, query)

        # Stage D: Relevance Ranking & Packing
        fused_context, citations = self.pack_context(deduped, query, contradictions)

        est_tokens = self._estimate_tokens(fused_context)
        fused_count = len(deduped)
        ratio = (raw_count - fused_count) / raw_count if raw_count > 0 else 0.0

        return OKFResult(
            fused_context=fused_context,
            citations=citations,
            contradictions=contradictions,
            raw_chunk_count=raw_count,
            fused_chunk_count=fused_count,
            estimated_tokens=est_tokens,
            deduplication_ratio=round(ratio, 3),
        )


# Global default OKF instance
default_okf = OKFEngine()
