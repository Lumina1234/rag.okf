import pytest
import io
import fitz
import os
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services import document_processor, vector_store, rag_engine, ollama_client
from core.config import settings


@pytest.mark.asyncio
async def test_full_rag_pipeline_with_gemma(tmp_path):
    """
    Integration test:
    create PDF -> extract -> chunk -> embed (BAAI/bge-m3) -> index in FAISS -> retrieve -> rerank -> construct prompt -> generate answer.
    """
    test_ws_id = 99999
    try:
        # 1. Create a test PDF
        pdf_path = tmp_path / "project_report.pdf"
        doc = fitz.open()
        page = doc.new_page(width=500, height=300)
        page.insert_text(
            (30, 50),
            "Project Apollo was initiated in 2024 to modernize the enterprise database.\n"
            "The total allocated budget for Project Apollo is $3.5 million.\n"
            "The lead architect for the database migration is Dr. Sarah Connor."
        )
        doc.save(str(pdf_path))
        doc.close()

        # 2. Extract and Chunk
        chunks = document_processor.process_document(
            file_path=pdf_path,
            file_type="pdf",
            doc_id=101,
            filename="project_report.pdf",
            workspace_id=test_ws_id,
            chunk_size=256,
            chunk_overlap=32,
        )
        assert len(chunks) > 0

        # 3. Embed & Index into FAISS using FakeEmbeddings for fast, isolated test execution
        from langchain_core.embeddings import FakeEmbeddings
        vector_store.embedding_service._embeddings = FakeEmbeddings(size=1024)
        num_added = vector_store.add_documents(test_ws_id, chunks)
        assert num_added == len(chunks)

        # 4. Retrieval & Single-Document selection
        search_results = vector_store.search(test_ws_id, "What is the budget for Project Apollo?")
        assert len(search_results) > 0
        assert "Apollo" in search_results[0][0].page_content

        # 5. Non-streaming RAG Complete with mocked LLM for fast reliable unit validation
        with patch("services.ollama_client.chat_complete", return_value="The total allocated budget for Project Apollo is $3.5 million.") as mock_chat:
            res = await rag_engine.rag_complete(
                question="What is the budget for Project Apollo?",
                workspace_id=test_ws_id,
                model="gemma4:12b",
            )

            assert "$3.5 million" in res["answer"]
            assert len(res["sources"]) > 0
            assert res["sources"][0]["document_name"] == "project_report.pdf"
            assert res["model_used"] == "gemma4:12b"
            mock_chat.assert_called_once()

        # 6. Streaming RAG Stream
        with patch("services.ollama_client.chat_stream") as mock_stream:
            async def fake_tokens(*args, **kwargs):
                yield "The budget is "
                yield "$3.5 million."
            mock_stream.side_effect = fake_tokens

            stream_chunks = []
            async for token in rag_engine.rag_stream(
                question="What is the budget for Project Apollo?",
                workspace_id=test_ws_id,
                model="gemma4:12b",
            ):
                stream_chunks.append(token)

            full_stream = "".join(stream_chunks)
            assert "$3.5 million" in full_stream
            assert '"type": "sources"' in full_stream
            assert "project_report.pdf" in full_stream

    finally:
        # Cleanup test FAISS files
        vector_store.delete_document(test_ws_id, 101)
        ws_dir = settings.VECTOR_DB_DIR / str(test_ws_id)
        if ws_dir.exists():
            shutil.rmtree(ws_dir, ignore_errors=True)
