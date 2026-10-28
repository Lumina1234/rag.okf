import pytest
import asyncio
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services import ollama_client
from core.config import settings


class FakeStreamResponse:
    def __init__(self):
        self.status_code = 200

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        yield '{"message": {"role": "assistant", "content": "Sample"}, "done": true}'


class FakeStreamContext:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self.resp

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class FakeAsyncClient:
    last_payload = None

    def __init__(self, *args, **kwargs):
        self.resp = FakeStreamResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def stream(self, method, url, **kwargs):
        FakeAsyncClient.last_payload = kwargs.get("json")
        return FakeStreamContext(self.resp)


@pytest.mark.asyncio
async def test_generation_limit_not_capped_at_256():
    """Verify that max_tokens > 256 is passed to num_predict without being clipped to 256."""
    with patch("services.ollama_client.is_ollama_online", return_value=True), \
         patch("services.ollama_client.is_model_available", return_value=True), \
         patch("httpx.AsyncClient", FakeAsyncClient):

        # Test with custom max_tokens = 1024
        async for _ in ollama_client.chat_stream(prompt="Test prompt", max_tokens=1024):
            pass

        sent_payload = FakeAsyncClient.last_payload
        assert sent_payload is not None
        assert sent_payload["options"]["num_predict"] == 1024, (
            f"Expected num_predict=1024, got {sent_payload['options']['num_predict']}"
        )


@pytest.mark.asyncio
async def test_generation_limit_defaults_and_validation():
    """Verify that invalid max_tokens fallback to settings.LLM_MAX_TOKENS."""
    with patch("services.ollama_client.is_ollama_online", return_value=True), \
         patch("services.ollama_client.is_model_available", return_value=True), \
         patch("httpx.AsyncClient", FakeAsyncClient):

        # Negative value
        async for _ in ollama_client.chat_stream(prompt="Test prompt", max_tokens=-10):
            pass

        sent_payload = FakeAsyncClient.last_payload
        assert sent_payload is not None
        assert sent_payload["options"]["num_predict"] == settings.LLM_MAX_TOKENS


@pytest.mark.asyncio
async def test_model_availability_check():
    """Verify that unknown model returns an informative warning without throwing unhandled exception."""
    with patch("services.ollama_client.is_ollama_online", return_value=True), \
         patch("services.ollama_client.list_models", return_value=["gemma4:12b"]):

        chunks = []
        async for token in ollama_client.chat_stream(prompt="Hi", model="nonexistent_model:xyz"):
            chunks.append(token)

        output = "".join(chunks)
        assert "not available in Ollama" in output
        assert "nonexistent_model:xyz" in output
