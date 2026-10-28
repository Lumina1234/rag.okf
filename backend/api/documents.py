"""
Document upload and management API routes.
POST   /documents/upload     - upload & process a document
GET    /documents/           - list documents in a workspace
DELETE /documents/{id}       - delete document + vectors
"""
import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from core.config import settings
from core.database import Document, Workspace
from core.deps import CurrentUser, DBSession
from models.schemas import DocumentResponse
from services import document_processor, vector_store

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "csv", "pptx", "ppt", "txt", "md"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


async def _process_document_bg(doc_id: int, file_path: Path, file_type: str,
                                 filename: str, workspace_id: int):
    """Background task: extract text, chunk, embed, index."""
    from core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            chunks = document_processor.process_document(
                file_path=file_path,
                file_type=file_type,
                doc_id=doc_id,
                filename=filename,
                workspace_id=workspace_id,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )
            added = vector_store.add_documents(workspace_id, chunks)

            # Update DB status
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalars().first()
            if doc:
                doc.status = "ready"
                doc.chunk_count = added
                await db.commit()
            logger.info(f"Document {doc_id} ready: {added} chunks")

        except Exception as e:
            logger.error(f"Document processing failed for doc {doc_id}: {e}")
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalars().first()
            if doc:
                doc.status = "failed"
                doc.error_message = str(e)[:500]
                await db.commit()


import re
import time
from typing import Dict, Tuple

# Upload rate limiter: user_id -> (count, window_reset)
_upload_limits: Dict[int, Tuple[int, float]] = {}
MAX_UPLOADS_PER_MINUTE = 10


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    workspace_id: int = Form(...),
):
    # Per-user upload rate limit
    now = time.time()
    count, reset_time = _upload_limits.get(current_user.id, (0, now + 60))
    if now > reset_time:
        count, reset_time = 0, now + 60
    if count >= MAX_UPLOADS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Upload rate limit exceeded. Try again later.")
    _upload_limits[current_user.id] = (count + 1, reset_time)

    # Validate workspace ownership
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Validate file extension
    original_name = file.filename or "unnamed"
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    # Read file
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 100 MB)")

    # Save to disk — sanitize filename to prevent path traversal
    safe_id = str(uuid.uuid4())[:8]
    safe_basename = re.sub(r"[^\w\.\-]", "_", original_name.replace(" ", "_"))
    stored_name = f"{safe_id}_{safe_basename}"
    ws_upload_dir = settings.UPLOAD_DIR / str(workspace_id)
    ws_upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = ws_upload_dir / stored_name
    file_path.write_bytes(content)

    # Create DB record
    doc = Document(
        filename=stored_name,
        original_filename=original_name,
        file_type=ext,
        file_size=len(content),
        workspace_id=workspace_id,
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Kick off background processing
    background_tasks.add_task(
        _process_document_bg,
        doc.id, file_path, ext, original_name, workspace_id,
    )

    logger.info(f"Uploaded {original_name} → doc_id={doc.id}, processing...")
    return doc


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(workspace_id: int, current_user: CurrentUser, db: DBSession):
    # Validate ownership
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=404, detail="Workspace not found")

    result = await db.execute(
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: int, current_user: CurrentUser, db: DBSession):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Check ownership via workspace
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == doc.workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=403, detail="Access denied")
    return doc


@router.get("/{doc_id}/download")
async def download_document(doc_id: int, current_user: CurrentUser, db: DBSession):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == doc.workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = (settings.UPLOAD_DIR / str(doc.workspace_id) / doc.filename).resolve()
    # Guard against path traversal
    if not str(file_path).startswith(str(settings.UPLOAD_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt": "text/plain",
        "md": "text/markdown",
    }.get(doc.file_type, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        filename=doc.original_filename,
        media_type=media_type,
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: int, current_user: CurrentUser, db: DBSession):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check ownership
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == doc.workspace_id, Workspace.owner_id == current_user.id)
    )
    if not ws_result.scalars().first():
        raise HTTPException(status_code=403, detail="Access denied")

    # Remove from FAISS
    vector_store.delete_document(doc.workspace_id, doc.id)

    # Remove file from disk
    file_path = settings.UPLOAD_DIR / str(doc.workspace_id) / doc.filename
    if file_path.exists():
        file_path.unlink()

    await db.delete(doc)
    await db.commit()
    logger.info(f"Deleted document {doc_id}")
