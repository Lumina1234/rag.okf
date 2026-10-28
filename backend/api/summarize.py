"""
Summarize API router.

POST /summarize — Universal summarization endpoint (streaming SSE).

Supports:
  - YouTube URLs (transcript extraction)
  - Web article URLs (content scraping)
  - Existing documents by document_id (reuses stored extracted text)
  - Plain pasted text

Response format (same as /chat/query):
  Line 1: {"type": "sources", "data": [...]}
  Lines 2+: plain text tokens
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from core.database import Document, Workspace
from core.deps import CurrentUser, DBSession
from core.config import settings
from models.schemas import SummarizeRequest
from services.summarization.source_detector import detect_source_type
from services.summarization.youtube_extractor import extract_youtube_transcript
from services.summarization.web_extractor import extract_web_article
from services.summarization.summarization_engine import summarize_stream
from services.document_processor import extract_text

router = APIRouter(prefix="/summarize", tags=["Summarize"])
logger = logging.getLogger(__name__)


@router.post("")
async def summarize(
    payload: SummarizeRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """
    Universal summarization endpoint (streaming SSE).

    Detects source type automatically and extracts content, then
    generates a structured summary using the local Ollama LLM.
    """
    detected = detect_source_type(
        content=payload.content,
        url=payload.url,
        document_id=payload.document_id,
        input_type=payload.input_type or "auto",
    )

    source_type = detected["source_type"]
    summary_type = payload.summary_type or "quick"

    async def event_stream():
        # ── Yield source metadata first (same as /chat/query) ──────────────
        source_meta = []

        # ── 1. YouTube ──────────────────────────────────────────────────────
        if source_type == "youtube":
            video_id = detected["video_id"]
            video_url = detected["url"] or payload.url or ""

            yield json.dumps({
                "type": "sources",
                "data": [{"document_name": f"YouTube: {video_url}", "source_type": "youtube"}],
            }) + "\n"
            yield "*Fetching YouTube transcript...*\n\n"

            result = extract_youtube_transcript(video_id)
            if not result["success"]:
                yield f"⚠️ **Could not retrieve transcript:**\n{result['error']}\n\n"
                yield "Please paste the video transcript manually and try again."
                return

            content = result["transcript"]
            source_label = result["title"]

            yield f"*Transcript extracted — {len(content)} characters. Generating summary...*\n\n"

            async for token in summarize_stream(
                content=content,
                summary_type=summary_type,
                source_label=source_label,
                source_type="youtube",
            ):
                yield token

        # ── 2. Web URL ──────────────────────────────────────────────────────
        elif source_type == "url":
            url = detected["url"]

            yield json.dumps({
                "type": "sources",
                "data": [{"document_name": url, "source_type": "article"}],
            }) + "\n"
            yield "*Downloading article...*\n\n"

            result = extract_web_article(url)
            if not result["success"]:
                yield f"⚠️ **Could not access the page:**\n{result['error']}\n\n"
                yield "Please paste the article text directly and try again."
                return

            content = result["content"]
            source_label = result["title"] or url
            yield f"*Article extracted — {len(content)} characters. Generating summary...*\n\n"

            async for token in summarize_stream(
                content=content,
                summary_type=summary_type,
                source_label=source_label,
                source_type="url",
            ):
                yield token

        # ── 3. Existing document ────────────────────────────────────────────
        elif source_type == "document":
            doc_id = detected["document_id"] or payload.document_id
            if doc_id is None:
                yield json.dumps({"type": "sources", "data": []}) + "\n"
                yield "⚠️ No document ID was provided."
                return

            doc_result = await db.execute(
                select(Document).where(Document.id == doc_id)
            )
            doc = doc_result.scalars().first()
            if not doc:
                yield json.dumps({"type": "sources", "data": []}) + "\n"
                yield f"⚠️ Document ID {doc_id} not found."
                return

            # Verify ownership via workspace
            ws_result = await db.execute(
                select(Workspace).where(
                    Workspace.id == doc.workspace_id,
                    Workspace.owner_id == current_user.id,
                )
            )
            # Allow admin to access any workspace
            if not ws_result.scalars().first() and current_user.role != "admin":
                yield json.dumps({"type": "sources", "data": []}) + "\n"
                yield "⚠️ You do not have access to this document."
                return

            yield json.dumps({
                "type": "sources",
                "data": [{"document_name": doc.original_filename, "source_type": "document"}],
            }) + "\n"
            yield f"*Reading document: {doc.original_filename}...*\n\n"

            # Locate the file on disk — stored under UPLOAD_DIR/{workspace_id}/{filename}
            upload_dir = settings.UPLOAD_DIR
            candidate_paths = [
                upload_dir / str(doc.workspace_id) / doc.filename,
                upload_dir / doc.filename,
            ]
            file_path = None
            for cp in candidate_paths:
                if cp.exists():
                    file_path = cp
                    break

            # If still not found, do a recursive search by filename
            if file_path is None:
                for p in upload_dir.rglob(doc.filename):
                    file_path = p
                    break

            if file_path is None:
                yield f"⚠️ The source file for '{doc.original_filename}' could not be found on disk.\n"
                yield "The file may have been deleted after upload."
                return

            try:
                content = extract_text(file_path, doc.file_type)
            except Exception as e:
                yield f"⚠️ Could not extract text from document: {str(e)}"
                return

            if not content.strip():
                yield "⚠️ The document appears to be empty or contains no extractable text."
                return

            yield f"*Document text extracted — {len(content)} characters. Generating summary...*\n\n"

            async for token in summarize_stream(
                content=content,
                summary_type=summary_type,
                source_label=doc.original_filename,
                source_type="document",
            ):
                yield token

        # ── 4. Plain text ───────────────────────────────────────────────────
        else:
            content = (payload.content or "").strip()
            if not content:
                yield json.dumps({"type": "sources", "data": []}) + "\n"
                yield "⚠️ No content was provided. Please paste text or provide a URL."
                return

            yield json.dumps({
                "type": "sources",
                "data": [{"document_name": "Pasted text", "source_type": "text"}],
            }) + "\n"
            yield f"*Processing {len(content)} characters of text...*\n\n"

            async for token in summarize_stream(
                content=content,
                summary_type=summary_type,
                source_label="Pasted text",
                source_type="text",
            ):
                yield token

    return StreamingResponse(event_stream(), media_type="text/event-stream")
