import pytest
import asyncio
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document as LCDocument

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services import rag_engine, ollama_client


@pytest.mark.asyncio
async def test_no_duplicate_context_in_rag_stream():
    """Verify that document content is included exactly once in the prompt passed to Ollama in rag_stream."""
    doc_text = "Acme Corp generated $15 million in ARR in 2025."
    mock_doc = LCDocument(
        page_content=doc_text,
        metadata={"filename": "acme_report.pdf", "page_number": 1, "doc_id": 10}
    )

    captured_prompt = None

    async def fake_chat_stream(prompt, system="", context=None, model=None, temperature=None, max_tokens=None):
        nonlocal captured_prompt
        if context and context.strip() and context.strip() not in prompt:
            prompt = f"{context.strip()}\n\n{prompt}"
        captured_prompt = prompt
        yield "Acme Corp generated $15M."

    with patch("services.vector_store.search", return_value=[(mock_doc, 0.1)]), \
         patch("services.ollama_client.chat_stream", side_effect=fake_chat_stream):

        chunks = []
        async for c in rag_engine.rag_stream(
            question="What is the ARR?",
            workspace_id=1,
        ):
            chunks.append(c)

        assert captured_prompt is not None
        occurrences = captured_prompt.count(doc_text)
        assert occurrences == 1, f"Expected 1 occurrence of context, but found {occurrences}: {captured_prompt}"


class FakeStreamResponse:
    def __init__(self):
        self.status_code = 200

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        yield '{"message": {"role": "assistant", "content": "Done"}, "done": true}'


class FakeStreamContext:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self.resp

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.last_payload = None
        self.resp = FakeStreamResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def stream(self, method, url, **kwargs):
        FakeAsyncClient.last_payload = kwargs.get("json")
        return FakeStreamContext(self.resp)


@pytest.mark.asyncio
async def test_ollama_client_duplicate_guard():
    """Verify that ollama_client.chat_stream does not duplicate context if already in prompt."""
    context = "Unique context string 12345."
    prompt_with_context = f"Document content:\n{context}\n\nQuestion: Tell me about it."

    with patch("services.ollama_client.is_ollama_online", return_value=True), \
         patch("services.ollama_client.is_model_available", return_value=True), \
         patch("httpx.AsyncClient", FakeAsyncClient):

        async for _ in ollama_client.chat_stream(prompt=prompt_with_context, context=context):
            pass

        sent_payload = FakeAsyncClient.last_payload
        assert sent_payload is not None
        user_message_content = sent_payload["messages"][-1]["content"]

        count = user_message_content.count(context)
        assert count == 1, f"Context was duplicated in user message! Count: {count}"
