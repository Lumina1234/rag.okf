import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services import rag_engine


@pytest.mark.asyncio
async def test_rag_stream_empty_results():
    """Test that rag_stream yields well-formed SSE traces and does not crash when vector search yields no chunks."""
    with patch("services.vector_store.search", return_value=[]):
        chunks = []
        async for chunk in rag_engine.rag_stream(
            question="What is the revenue?",
            workspace_id=999,
        ):
            chunks.append(chunk)

        full_output = "".join(chunks)
        assert "Not found in the uploaded documents." in full_output
        assert '"type": "sources", "data": []' in full_output
        assert '"step": "retrieving"' in full_output
        assert '"step": "citations"' in full_output


@pytest.mark.asyncio
async def test_rag_complete_empty_results():
    """Test that rag_complete returns clean response without calling LLM when results are empty."""
    with patch("services.vector_store.search", return_value=[]), \
         patch("services.ollama_client.chat_complete") as mock_chat:
        resp = await rag_engine.rag_complete(
            question="What is the revenue?",
            workspace_id=999,
        )

        assert resp["answer"] == "Not found in the uploaded documents."
        assert resp["sources"] == []
        assert resp["workspace_id"] == 999
        mock_chat.assert_not_called()
